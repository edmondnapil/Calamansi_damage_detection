"""Integration tests for accounts and sessions against the real Supabase project.

They create throw-away users with the Supabase admin API (which returns the
one-time e-mail code directly, so no e-mail has to be delivered), exercise the
real endpoints, and delete the users and their audit rows afterwards.

Only the account part of the app is loaded (no ML models). Requires the
Supabase settings in backend/.env and migration 002. Run:
    python -m pytest tests/test_auth.py -v
"""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import admin  # noqa: E402
import auth  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from helpers import (  # noqa: E402
    PASSWORD, BrowserLikeClient, admin_recovery_code, admin_signup, delete_test_accounts, unique,
)

pytestmark = pytest.mark.skipif(not auth.AUTH_ENABLED, reason="Supabase is not configured")

NEW_PASSWORD = "Leaf-Check#2027"


def make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth.csrf_middleware)
    app.include_router(auth.router)
    app.include_router(admin.router)

    @app.get("/api/protected")
    def protected(user: auth.CurrentUser = Depends(auth.current_user)):
        return {"id": user.id}

    return app


def new_client() -> TestClient:
    c = BrowserLikeClient(make_app())
    c.get("/api/auth/csrf")
    return c


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    delete_test_accounts()


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"


# ----------------------------------------------------------------------------- tests
def test_csrf_required_for_state_changing_requests():
    c = TestClient(make_app())
    r = c.post("/api/auth/login", json={"email": "a@example.com", "password": "x"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "csrf_failed"


def test_registration_validation():
    c = new_client()
    base = {"full_name": "Test", "username": "valid_name", "email": "x@example.com", "password": PASSWORD}
    assert c.post("/api/auth/register", json={**base, "email": "not-an-email"}).json()["detail"]["code"] == "invalid_email"
    assert c.post("/api/auth/register", json={**base, "username": "Bad Name!"}).json()["detail"]["code"] == "invalid_username"
    weak = c.post("/api/auth/register", json={**base, "password": "password1"})
    assert weak.status_code == 422 and weak.json()["detail"]["code"] == "weak_password"


def test_unverified_account_cannot_sign_in_or_use_protected_endpoints():
    email, username = unique("unver")
    admin_signup(email, username)
    c = new_client()
    r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "email_not_verified"
    assert c.get("/api/protected").status_code == 401
    assert c.get("/api/auth/me").status_code == 401


def test_verification_code_rules_and_session_lifecycle():
    email, username = unique("main")
    _, code = admin_signup(email, username)
    c = new_client()
    # invalid code
    r = c.post("/api/auth/verify-email", json={"email": email, "code": wrong(code)})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "invalid_or_expired_code"
    # valid code -> verified and signed in
    r = c.post("/api/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is True and r.json()["user"]["role"] == "user"
    assert c.get("/api/protected").status_code == 200
    # a used code cannot be reused
    c2 = new_client()
    assert c2.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 400
    # duplicates are rejected
    dup = {"full_name": "X", "username": username, "email": email, "password": PASSWORD}
    assert c2.post("/api/auth/register", json=dup).json()["detail"]["code"] == "email_taken"
    other_email, _ = unique("dupname")
    r = c2.post("/api/auth/register", json={**dup, "email": other_email})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "username_taken"
    # refresh + logout invalidate the session
    assert c.post("/api/auth/refresh").status_code == 200
    assert c.get("/api/auth/me").json()["user"]["email"] == email
    old_refresh = c.cookies.get("cl_rt")
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/protected").status_code == 401
    c3 = new_client()
    c3.cookies.set("cl_rt", old_refresh, path="/api/auth")
    assert c3.post("/api/auth/refresh").status_code == 401  # revoked refresh token


def test_too_many_wrong_codes_blocks_even_the_right_one():
    email, username = unique("attempts")
    _, code = admin_signup(email, username)
    c = new_client()
    for _ in range(auth.OTP_MAX_ATTEMPTS):
        assert c.post("/api/auth/verify-email", json={"email": email, "code": wrong(code)}).status_code == 400
    r = c.post("/api/auth/verify-email", json={"email": email, "code": code})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"


def test_login_errors_are_generic_and_lockout_applies():
    email, username = unique("lock")
    _, code = admin_signup(email, username)
    c = new_client()
    assert c.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    c = new_client()
    unknown = c.post("/api/auth/login", json={"email": "no.such.user." + secrets.token_hex(3) + "@example.com",
                                              "password": PASSWORD})
    bad = c.post("/api/auth/login", json={"email": email, "password": "Wrong#Pass1"})
    assert unknown.status_code == bad.status_code == 401
    assert unknown.json()["detail"]["message"] == bad.json()["detail"]["message"]  # does not reveal existence
    for _ in range(auth.LOGIN_MAX_FAILURES - 1):
        c.post("/api/auth/login", json={"email": email, "password": "Wrong#Pass1"})
    locked = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})  # correct, but locked
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "login_locked"


def test_forgot_password_is_generic_and_reset_revokes_sessions():
    email, username = unique("reset")
    _, code = admin_signup(email, username)
    session = new_client()
    assert session.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    assert session.get("/api/protected").status_code == 200

    c = new_client()
    unknown = c.post("/api/auth/forgot-password", json={"email": "nobody." + secrets.token_hex(3) + "@example.com"})
    known = c.post("/api/auth/forgot-password", json={"email": email})
    assert unknown.status_code == known.status_code == 200
    assert unknown.json()["message"] == known.json()["message"]
    again = c.post("/api/auth/forgot-password", json={"email": email})  # cooldown
    assert again.status_code == 429 and again.json()["detail"]["code"] == "resend_cooldown"

    rcode = admin_recovery_code(email)
    weak = c.post("/api/auth/reset-password", json={"email": email, "code": rcode, "password": "short"})
    assert weak.status_code == 422
    bad = c.post("/api/auth/reset-password", json={"email": email, "code": wrong(rcode), "password": NEW_PASSWORD})
    assert bad.status_code == 400
    ok = c.post("/api/auth/reset-password", json={"email": email, "code": rcode, "password": NEW_PASSWORD})
    assert ok.status_code == 200, ok.text
    auth._invalidate_cache()
    assert session.get("/api/protected").status_code == 401  # old session revoked
    assert c.post("/api/auth/reset-password", json={"email": email, "code": rcode,
                                                    "password": NEW_PASSWORD + "x"}).status_code == 400  # code used
    c = new_client()
    assert c.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code == 401
    assert c.post("/api/auth/login", json={"email": email, "password": NEW_PASSWORD}).status_code == 200


def test_suspended_account_and_admin_only_endpoints():
    email, username = unique("susp")
    user_id, code = admin_signup(email, username)
    c = new_client()
    assert c.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    assert c.get("/api/admin/users").status_code == 403  # ordinary users are not administrators
    r = auth.gotrue().call("PATCH", "/profiles", params={"id": f"eq.{user_id}"}, json={"account_status": "suspended"},
                           rest=True)
    assert r.status_code < 300, r.text
    auth._invalidate_cache()
    assert c.get("/api/protected").json()["detail"]["code"] == "account_suspended"
    c2 = new_client()
    r = c2.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "account_suspended"
