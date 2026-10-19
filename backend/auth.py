"""Accounts, sessions and access control (Supabase Auth behind the FastAPI backend).

Who does what
-------------
* Supabase Auth (GoTrue) stores e-mails and password hashes, sends the 6-digit
  e-mail codes through the SMTP server configured in the Supabase dashboard,
  stores the codes hashed, expires them, makes them single-use and replaces
  them when a new one is sent.
* This module (server side only) adds what Supabase Auth does not do for us:
  input validation, duplicate checks, login lockout, code-attempt limits,
  resend cooldowns, role/status checks, audit logging, and sessions in
  HttpOnly cookies protected against CSRF.

The browser never sees a Supabase key or a token: it only holds HttpOnly
cookies (access + refresh token) and a CSRF token.

Session cookies
---------------
  cl_at    access token  (HttpOnly, SameSite=Lax,    path /,         ~1 h)
  cl_rt    refresh token (HttpOnly, SameSite=Strict, path /api/auth, AUTH_SESSION_DAYS)
  cl_csrf  CSRF token    (readable by the page, sent back in X-CSRF-Token on every
           state-changing request; double-submit check in csrf_middleware)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config  # noqa: F401  (loads backend/.env before the settings below are read)

log = logging.getLogger("calamansi.auth")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
AUTH_ENABLED = bool(SUPABASE_URL and SERVICE_KEY and "YOUR-" not in SUPABASE_URL + SERVICE_KEY)

COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() in ("1", "true", "yes")  # true behind HTTPS
SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "7"))
OTP_RESEND_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_SENDS_PER_HOUR = int(os.getenv("OTP_MAX_SENDS_PER_HOUR", "5"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
IP_MAX_FAILURES = int(os.getenv("IP_MAX_FAILURES_PER_15_MIN", "30"))
# Keyed hashes in the audit log; derived from the service key unless set explicitly.
_HASH_KEY = (os.getenv("AUTH_HASH_SECRET") or hashlib.sha256(("audit:" + SERVICE_KEY).encode()).hexdigest()).encode()

AT, RT, CSRF = "cl_at", "cl_rt", "cl_csrf"
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")
GENERIC_LOGIN_ERROR = "Incorrect email or password."

router = APIRouter(prefix="/api/auth", tags=["auth"])


# --------------------------------------------------------------------------- helpers
class AuthError(HTTPException):
    def __init__(self, status: int, message: str, code: str, **extra: Any):
        super().__init__(status, {"code": code, "message": message, **extra})


def _norm_email(email: str) -> str:
    return email.strip().lower()


def _hash(value: str | None) -> str | None:
    return hmac.new(_HASH_KEY, value.encode(), hashlib.sha256).hexdigest()[:40] if value else None


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def password_problems(password: str, email: str = "", username: str = "") -> list[str]:
    problems = []
    if len(password) < 8:
        problems.append("at least 8 characters")
    if len(password) > 72:
        problems.append("at most 72 characters")
    if not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if not re.search(r"\d", password):
        problems.append("a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")
    low = password.lower()
    local = email.split("@")[0].lower()
    if (len(local) >= 4 and local in low) or (len(username) >= 4 and username.lower() in low):
        problems.append("not your email or username")
    return problems


def _require_strong(password: str, email: str = "", username: str = "") -> None:
    problems = password_problems(password, email, username)
    if problems:
        raise AuthError(422, "Password must contain " + ", ".join(problems) + ".", "weak_password", problems=problems)


# --------------------------------------------------------------------------- Supabase Auth client
class GoTrue:
    """Minimal stateless client for the Supabase Auth REST API (one shared HTTP/1.1 pool)."""

    def __init__(self):
        self.http = httpx.Client(base_url=f"{SUPABASE_URL}/auth/v1", timeout=httpx.Timeout(20.0, connect=10.0),
                                 limits=httpx.Limits(max_connections=20, keepalive_expiry=20.0))
        self.rest = httpx.Client(base_url=f"{SUPABASE_URL}/rest/v1", timeout=httpx.Timeout(20.0, connect=10.0),
                                 limits=httpx.Limits(max_connections=20, keepalive_expiry=20.0))

    def _headers(self, token: str | None = None) -> dict:
        return {"apikey": SERVICE_KEY, "Authorization": f"Bearer {token or SERVICE_KEY}"}

    def call(self, method: str, path: str, *, token: str | None = None, json: Any = None, params: Any = None,
             rest: bool = False) -> httpx.Response:
        client = self.rest if rest else self.http
        for attempt in range(3):
            try:
                return client.request(method, path, headers=self._headers(token), json=json, params=params)
            except httpx.TransportError:
                if attempt == 2:
                    raise HTTPException(503, "The account service is temporarily unreachable. Please try again.")
                time.sleep(0.3 * (attempt + 1))
        raise AssertionError("unreachable")


_gotrue: GoTrue | None = None


def gotrue() -> GoTrue:
    global _gotrue
    if not AUTH_ENABLED:
        raise HTTPException(503, "Accounts are not available: Supabase is not configured on the server.")
    if _gotrue is None:
        _gotrue = GoTrue()
    return _gotrue


def _err(resp: httpx.Response) -> tuple[str, str]:
    """(error_code, message) from a Supabase Auth error response."""
    try:
        body = resp.json()
    except ValueError:
        return "unknown", resp.text[:200]
    code = body.get("error_code") or body.get("code") or body.get("error") or "unknown"
    msg = body.get("msg") or body.get("message") or body.get("error_description") or ""
    return str(code), str(msg)


# --------------------------------------------------------------------------- audit log + limits
def audit(event_type: str, status: Literal["success", "failure", "blocked"], *, email: str | None = None,
          user_id: str | None = None, request: Request | None = None, **metadata: Any) -> None:
    """Record a security event. Never pass passwords, codes or tokens in metadata."""
    row = {"event_type": event_type, "event_status": status, "email_hash": _hash(_norm_email(email) if email else None),
           "ip_hash": _hash(_client_ip(request)) if request else None, "user_id": user_id,
           "metadata": {k: v for k, v in metadata.items() if v is not None}}
    try:
        r = gotrue().call("POST", "/security_audit_logs", json=row, rest=True)
        if r.status_code >= 300:
            log.warning("audit insert failed: %s", r.text[:200])
    except HTTPException:
        log.warning("audit insert failed: auth service unreachable")


def _count(event_types: list[str], status: str, since: datetime, *, email: str | None = None,
           ip: str | None = None) -> tuple[int, datetime | None]:
    """(number of matching audit events since `since`, time of the newest one). status may be "a,b"."""
    params = [("select", "created_at"), ("event_status", f"in.({status})"),
              ("event_type", f"in.({','.join(event_types)})"), ("created_at", f"gte.{since.isoformat()}"),
              ("order", "created_at.desc"), ("limit", "200")]
    if email:
        params.append(("email_hash", f"eq.{_hash(_norm_email(email))}"))
    if ip:
        params.append(("ip_hash", f"eq.{_hash(ip)}"))
    r = gotrue().call("GET", "/security_audit_logs", params=params, rest=True)
    if r.status_code >= 300:
        raise HTTPException(503, "Security checks are unavailable. Has supabase/migrations/002_auth_profiles.sql been run?")
    rows = r.json()
    newest = datetime.fromisoformat(rows[0]["created_at"].replace("Z", "+00:00")) if rows else None
    return len(rows), newest


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_send_allowed(email: str, purpose: str) -> None:
    """Resend cooldown and hourly cap for e-mails with codes (per e-mail address).

    Requests for addresses without an account ("blocked") and failed sends count too,
    so the cooldown behaves identically and does not reveal which accounts exist.
    """
    n, newest = _count([f"{purpose}_code_sent"], "success,blocked,failure", _now() - timedelta(hours=1), email=email)
    if newest and (_now() - newest).total_seconds() < OTP_RESEND_SECONDS:
        wait = int(OTP_RESEND_SECONDS - (_now() - newest).total_seconds()) + 1
        raise AuthError(429, f"Please wait {wait} seconds before requesting another code.", "resend_cooldown",
                        retry_after=wait)
    if n >= OTP_MAX_SENDS_PER_HOUR:
        raise AuthError(429, "Too many codes requested. Please try again in an hour.", "too_many_codes")


def _check_attempts_allowed(email: str, purpose: str) -> None:
    """At most OTP_MAX_ATTEMPTS wrong codes per sent code; then a new code is required."""
    _, last_sent = _count([f"{purpose}_code_sent"], "success", _now() - timedelta(hours=2), email=email)
    since = last_sent or (_now() - timedelta(hours=2))
    fails, _ = _count([f"{purpose}_verify"], "failure", since, email=email)
    if fails >= OTP_MAX_ATTEMPTS:
        raise AuthError(429, "Too many incorrect codes. Please request a new code.", "too_many_attempts")


def _check_login_allowed(email: str, request: Request) -> None:
    since = _now() - timedelta(minutes=LOGIN_LOCK_MINUTES)
    fails, _ = _count(["login"], "failure", since, email=email)
    ip_fails, _ = _count(["login"], "failure", _now() - timedelta(minutes=15), ip=_client_ip(request))
    if fails >= LOGIN_MAX_FAILURES or ip_fails >= IP_MAX_FAILURES:
        audit("login", "blocked", email=email, request=request)
        raise AuthError(429, f"Too many failed sign-in attempts. Please try again in {LOGIN_LOCK_MINUTES} minutes.",
                        "login_locked")


# --------------------------------------------------------------------------- cookies / sessions
def _set_session(response: Response, session: dict) -> None:
    response.set_cookie(AT, session["access_token"], max_age=int(session.get("expires_in", 3600)), httponly=True,
                        secure=COOKIE_SECURE, samesite="lax", path="/")
    response.set_cookie(RT, session["refresh_token"], max_age=SESSION_DAYS * 86400, httponly=True,
                        secure=COOKIE_SECURE, samesite="strict", path="/api/auth")
    _set_csrf(response, secrets.token_urlsafe(32))


def _set_csrf(response: Response, token: str) -> None:
    response.set_cookie(CSRF, token, max_age=SESSION_DAYS * 86400, httponly=False, secure=COOKIE_SECURE,
                        samesite="strict", path="/")


def _clear_session(response: Response) -> None:
    response.delete_cookie(AT, path="/")
    response.delete_cookie(RT, path="/api/auth")
    _invalidate_cache()


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def csrf_middleware(request: Request, call_next):
    """Double-submit CSRF check for every state-changing /api request (incl. login)."""
    if request.method not in SAFE_METHODS and request.url.path.startswith("/api/"):
        cookie = request.cookies.get(CSRF, "")
        header = request.headers.get("x-csrf-token", "")
        if not cookie or not hmac.compare_digest(cookie, header):
            return JSONResponse({"detail": {"code": "csrf_failed",
                                            "message": "Security check failed. Please reload the page and try again."}},
                                status_code=403)
    return await call_next(request)


# --------------------------------------------------------------------------- current user
@dataclass
class CurrentUser:
    id: str
    email: str
    full_name: str
    username: str
    role: str
    account_status: str
    email_verified: bool
    must_change_password: bool = False  # set for provisioned accounts (create_admin.py); cleared on change

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "full_name": self.full_name, "username": self.username,
                "role": self.role, "account_status": self.account_status, "email_verified": self.email_verified,
                "must_change_password": self.must_change_password}


_cache: dict[str, tuple[float, CurrentUser]] = {}
CACHE_SECONDS = 30


def _invalidate_cache() -> None:
    _cache.clear()


def _load_profile(user: dict) -> CurrentUser:
    r = gotrue().call("GET", "/profiles", params={"id": f"eq.{user['id']}", "select": "*"}, rest=True)
    if r.status_code >= 300:
        raise HTTPException(503, "Account data is unavailable. Has supabase/migrations/002_auth_profiles.sql been run?")
    rows = r.json()
    p = rows[0] if rows else {"full_name": user.get("email", ""), "username": "", "role": "user",
                              "account_status": "active"}
    return CurrentUser(id=user["id"], email=user.get("email", ""), full_name=p["full_name"], username=p["username"],
                       role=p["role"], account_status=p["account_status"],
                       email_verified=bool(user.get("email_confirmed_at")),
                       # app_metadata can only be written with the service role, never by the user
                       must_change_password=bool((user.get("app_metadata") or {}).get("must_change_password")))


def user_from_token(token: str) -> CurrentUser | None:
    """Validate an access token with Supabase Auth (also rejects tokens of signed-out sessions)."""
    key = hashlib.sha256(token.encode()).hexdigest()
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    r = gotrue().call("GET", "/user", token=token)
    if r.status_code != 200:
        _cache.pop(key, None)
        return None
    user = _load_profile(r.json())
    _cache[key] = (time.monotonic() + CACHE_SECONDS, user)
    if len(_cache) > 2000:
        _cache.clear()
    return user


def signed_in_user(request: Request) -> CurrentUser:
    """Signed in, e-mail verified and active (may still have to change the initial password)."""
    token = request.cookies.get(AT)
    user = user_from_token(token) if token else None
    if not user:
        raise AuthError(401, "Please sign in to continue.", "not_authenticated")
    if not user.email_verified:
        raise AuthError(403, "Please verify your email address first.", "email_not_verified", email=user.email)
    if user.account_status != "active":
        raise AuthError(403, "This account has been suspended. Contact the administrator.", "account_suspended")
    return user


def current_user(user: CurrentUser = Depends(signed_in_user)) -> CurrentUser:
    """Dependency for every protected endpoint. Accounts created with a temporary password
    (create_admin.py) can do nothing else until they have changed it."""
    if user.must_change_password:
        raise AuthError(403, "Please change your temporary password first.", "password_change_required")
    return user


def admin_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise AuthError(403, "Administrator access is required.", "forbidden")
    return user


# --------------------------------------------------------------------------- request models
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=30)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class VerifyIn(EmailIn):
    code: str = Field(min_length=6, max_length=10)


class LoginIn(EmailIn):
    password: str = Field(min_length=1, max_length=200)


class ResetIn(VerifyIn):
    password: str = Field(min_length=1, max_length=200)


def _valid_email(email: str) -> str:
    email = _norm_email(email)
    if not EMAIL_RE.match(email):
        raise AuthError(422, "Please enter a valid email address.", "invalid_email")
    return email


def _valid_code(code: str) -> str:
    code = code.strip().replace(" ", "")
    if not re.fullmatch(r"\d{6,10}", code):
        raise AuthError(422, "Enter the 6-digit code from the email.", "invalid_code_format")
    return code


def _email_status(email: str) -> str:
    r = gotrue().call("POST", "/rpc/auth_email_status", json={"p_email": email}, rest=True)
    if r.status_code >= 300:
        raise HTTPException(503, "Account checks are unavailable. Has supabase/migrations/002_auth_profiles.sql been run?")
    return r.json()


# --------------------------------------------------------------------------- endpoints
@router.get("/csrf")
def get_csrf(request: Request, response: Response):
    """Issues the CSRF cookie the page must echo back in X-CSRF-Token."""
    token = request.cookies.get(CSRF) or secrets.token_urlsafe(32)
    _set_csrf(response, token)
    return {"csrf_token": token}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request):
    email = _valid_email(body.email)
    username = body.username.strip().lower()
    full_name = " ".join(body.full_name.split())
    if not USERNAME_RE.match(username):
        raise AuthError(422, "Username must be 3-30 characters: lowercase letters, numbers or _.", "invalid_username")
    if not full_name:
        raise AuthError(422, "Please enter your full name.", "invalid_name")
    _require_strong(body.password, email, username)

    status = _email_status(email)
    if status == "verified":
        audit("register", "failure", email=email, request=request, reason="duplicate_email")
        raise AuthError(409, "An account with this email already exists. Sign in instead.", "email_taken")
    r = gotrue().call("GET", "/profiles", params={"username": f"eq.{username}", "select": "id"}, rest=True)
    if r.status_code == 200 and r.json():
        audit("register", "failure", email=email, request=request, reason="duplicate_username")
        raise AuthError(409, "This username is already taken.", "username_taken")
    if status == "unverified":
        # Registered before but never verified: send a fresh code instead of a second account.
        _check_send_allowed(email, "signup")
        rr = gotrue().call("POST", "/resend", json={"type": "signup", "email": email})
        if rr.status_code >= 300:
            code, msg = _err(rr)
            log.warning("resend after re-register failed: %s %s", code, msg)
            raise AuthError(502, "We could not send the verification email. Please try again later.", "email_send_failed")
        audit("signup_code_sent", "success", email=email, request=request, via="register")
        return {"message": "This email is already registered but not verified. We sent a new verification code.",
                "email": email, "resend_after": OTP_RESEND_SECONDS}

    _check_send_allowed(email, "signup")
    r = gotrue().call("POST", "/signup", json={"email": email, "password": body.password,
                                               "data": {"full_name": full_name, "username": username}})
    if r.status_code >= 300:
        code, msg = _err(r)
        audit("register", "failure", email=email, request=request, reason=code)
        if code in ("weak_password",):
            raise AuthError(422, msg or "Password is too weak.", "weak_password")
        if "rate" in code or r.status_code == 429:
            raise AuthError(429, "Too many registrations right now. Please try again later.", "rate_limited")
        if "email" in msg.lower() and "send" in msg.lower():
            raise AuthError(502, "Your account was not created because the verification email could not be sent. "
                                 "Please try again later.", "email_send_failed")
        log.warning("signup failed: %s %s", code, msg)
        raise AuthError(400, "Registration failed. Please check your details and try again.", "register_failed")
    user = r.json().get("user") or r.json()
    audit("register", "success", email=email, user_id=user.get("id"), request=request)
    audit("signup_code_sent", "success", email=email, user_id=user.get("id"), request=request, via="register")
    return {"message": "Account created. Enter the 6-digit code we sent to your email.", "email": email,
            "resend_after": OTP_RESEND_SECONDS}


@router.post("/verify-email")
def verify_email(body: VerifyIn, request: Request, response: Response):
    email, code = _valid_email(body.email), _valid_code(body.code)
    _check_attempts_allowed(email, "signup")
    r = gotrue().call("POST", "/verify", json={"type": "signup", "email": email, "token": code})
    if r.status_code != 200:
        audit("signup_verify", "failure", email=email, request=request)
        raise AuthError(400, "The code is incorrect or has expired. Check the code or request a new one.",
                        "invalid_or_expired_code")
    session = r.json()
    audit("signup_verify", "success", email=email, user_id=session.get("user", {}).get("id"), request=request)
    _set_session(response, session)
    return {"message": "Email verified. Welcome!", "user": _load_profile(session["user"]).public()}


@router.post("/resend-code")
def resend_code(body: EmailIn, request: Request):
    email = _valid_email(body.email)
    _check_send_allowed(email, "signup")
    generic = {"message": "If this email has an unverified account, a new code has been sent.",
               "resend_after": OTP_RESEND_SECONDS}
    if _email_status(email) != "unverified":
        audit("signup_code_sent", "blocked", email=email, request=request)
        return generic
    r = gotrue().call("POST", "/resend", json={"type": "signup", "email": email})
    if r.status_code >= 300:
        code, msg = _err(r)
        log.warning("resend failed: %s %s", code, msg)
        if r.status_code == 429:
            raise AuthError(429, "Please wait a moment before requesting another code.", "resend_cooldown",
                            retry_after=OTP_RESEND_SECONDS)
        raise AuthError(502, "We could not send the email. Please try again later.", "email_send_failed")
    audit("signup_code_sent", "success", email=email, request=request, via="resend")
    return generic


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response):
    email = _norm_email(body.email)
    if not EMAIL_RE.match(email):
        raise AuthError(401, GENERIC_LOGIN_ERROR, "invalid_credentials")
    _check_login_allowed(email, request)
    r = gotrue().call("POST", "/token", params={"grant_type": "password"},
                      json={"email": email, "password": body.password})
    if r.status_code != 200:
        code, _ = _err(r)
        if code == "email_not_confirmed":
            # Correct password, unverified e-mail: safe to say, since the password proved ownership.
            audit("login", "failure", email=email, request=request, reason="email_not_verified")
            raise AuthError(403, "Please verify your email address first. We can send you a new code.",
                            "email_not_verified", email=email)
        audit("login", "failure", email=email, request=request)
        raise AuthError(401, GENERIC_LOGIN_ERROR, "invalid_credentials")
    session = r.json()
    user = _load_profile(session["user"])
    if user.account_status != "active":
        gotrue().call("POST", "/logout", token=session["access_token"], params={"scope": "local"})
        audit("login", "blocked", email=email, user_id=user.id, request=request, reason="suspended")
        raise AuthError(403, "This account has been suspended. Contact the administrator.", "account_suspended")
    audit("login", "success", email=email, user_id=user.id, request=request)
    _set_session(response, session)
    return {"user": user.public()}  # includes role, so the page can open the right dashboard


@router.post("/refresh")
def refresh(request: Request, response: Response):
    token = request.cookies.get(RT)
    if not token:
        raise AuthError(401, "Please sign in to continue.", "not_authenticated")
    r = gotrue().call("POST", "/token", params={"grant_type": "refresh_token"}, json={"refresh_token": token})
    if r.status_code != 200:
        _clear_session(response)
        raise AuthError(401, "Your session has ended. Please sign in again.", "session_expired")
    _set_session(response, r.json())
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(AT)
    user = user_from_token(token) if token else None
    if not user and request.cookies.get(RT):  # access token expired: refresh once so the session can be revoked
        rr = gotrue().call("POST", "/token", params={"grant_type": "refresh_token"},
                           json={"refresh_token": request.cookies[RT]})
        if rr.status_code == 200:
            token = rr.json()["access_token"]
            user = user_from_token(token)
    if token:
        gotrue().call("POST", "/logout", token=token, params={"scope": "local"})  # revokes this session's refresh token
    if user:
        audit("logout", "success", email=user.email, user_id=user.id, request=request)
    _clear_session(response)
    return {"message": "Signed out."}


@router.get("/me")
def me(user: CurrentUser = Depends(signed_in_user)):
    return {"user": user.public()}


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser = Depends(signed_in_user)):
    """Change the password of the signed-in account (also clears a temporary-password flag)."""
    _require_strong(body.new_password, user.email, user.username)
    if body.new_password == body.current_password:
        raise AuthError(422, "Choose a password different from your current one.", "same_password")
    _check_login_allowed(user.email, request)  # wrong current passwords count toward the lockout
    r = gotrue().call("POST", "/token", params={"grant_type": "password"},
                      json={"email": user.email, "password": body.current_password})
    if r.status_code != 200:
        audit("login", "failure", email=user.email, user_id=user.id, request=request, via="change_password")
        raise AuthError(400, "Your current password is incorrect.", "wrong_current_password")
    # The check created a session of its own: end it right away.
    gotrue().call("POST", "/logout", token=r.json()["access_token"], params={"scope": "local"})
    browser = request.cookies[AT]
    u = gotrue().call("PUT", "/user", token=browser, json={"password": body.new_password})
    if u.status_code != 200:
        code, msg = _err(u)
        raise AuthError(400, msg or "The password could not be changed.", code or "change_failed")
    if user.must_change_password:
        gotrue().call("PUT", f"/admin/users/{user.id}", json={"app_metadata": {"must_change_password": False}})
    # Keep this browser signed in, sign out every other session of the account.
    gotrue().call("POST", "/logout", token=browser, params={"scope": "others"})
    _invalidate_cache()
    audit("password_change", "success", email=user.email, user_id=user.id, request=request)
    return {"message": "Your password has been changed. Other devices have been signed out."}


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request):
    email = _valid_email(body.email)
    generic = {"message": "If an account exists for this email, we sent a 6-digit reset code.",
               "resend_after": OTP_RESEND_SECONDS}
    _check_send_allowed(email, "recovery")
    if _email_status(email) != "verified":
        audit("recovery_code_sent", "blocked", email=email, request=request)  # counts toward the cooldown too
        return generic
    r = gotrue().call("POST", "/recover", json={"email": email})
    if r.status_code >= 300:
        code, msg = _err(r)
        log.warning("recover failed: %s %s", code, msg)
        audit("recovery_code_sent", "failure", email=email, request=request, reason=code)
        return generic  # never reveal whether the account exists
    audit("recovery_code_sent", "success", email=email, request=request)
    return generic


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request, response: Response):
    email, code = _valid_email(body.email), _valid_code(body.code)
    _require_strong(body.password, email)
    _check_attempts_allowed(email, "recovery")
    r = gotrue().call("POST", "/verify", json={"type": "recovery", "email": email, "token": code})
    if r.status_code != 200:
        audit("recovery_verify", "failure", email=email, request=request)
        raise AuthError(400, "The code is incorrect or has expired. Request a new code.", "invalid_or_expired_code")
    session = r.json()
    user_id = session.get("user", {}).get("id")
    audit("recovery_verify", "success", email=email, user_id=user_id, request=request)
    u = gotrue().call("PUT", "/user", token=session["access_token"], json={"password": body.password})
    if u.status_code != 200:
        code_, msg = _err(u)
        audit("password_reset", "failure", email=email, user_id=user_id, request=request, reason=code_)
        if code_ == "same_password":
            raise AuthError(422, "Choose a password different from your old one.", "same_password")
        raise AuthError(400, msg or "The password could not be changed.", "reset_failed")
    # Sign out every session of this account (including the one-time recovery session).
    gotrue().call("POST", "/logout", token=session["access_token"], params={"scope": "global"})
    audit("password_reset", "success", email=email, user_id=user_id, request=request)
    _clear_session(response)
    return {"message": "Your password has been changed. Please sign in with your new password."}
