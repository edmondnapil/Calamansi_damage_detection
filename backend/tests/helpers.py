"""Shared helpers: throw-away Supabase test accounts and a browser-like test client."""
from __future__ import annotations

import secrets
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auth  # noqa: E402

PASSWORD = "Calamansi#2026"

created: list[tuple[str, str]] = []  # (user id, email) of every test account


class BrowserLikeClient(TestClient):
    """Sends the current CSRF cookie in X-CSRF-Token, like frontend/src/lib/api.ts does."""

    def request(self, *args, **kwargs):
        token = self.cookies.get("cl_csrf")
        if token:
            self.headers["X-CSRF-Token"] = token
        return super().request(*args, **kwargs)


def unique(prefix: str) -> tuple[str, str]:
    tag = secrets.token_hex(4)
    return f"cltest.{prefix}.{tag}@example.com", f"t_{prefix}_{tag}"[:30]


def admin_signup(email: str, username: str) -> tuple[str, str]:
    """Unverified account + its signup code, created with the admin API (no e-mail is sent)."""
    r = auth.gotrue().call("POST", "/admin/generate_link", json={
        "type": "signup", "email": email, "password": PASSWORD,
        "data": {"full_name": "Test User", "username": username}})
    assert r.status_code == 200, r.text
    body = r.json()
    user_id = body.get("id") or body.get("user", {}).get("id")
    created.append((user_id, email))
    return user_id, body.get("email_otp") or body["properties"]["email_otp"]


def admin_recovery_code(email: str) -> str:
    r = auth.gotrue().call("POST", "/admin/generate_link", json={"type": "recovery", "email": email})
    assert r.status_code == 200, r.text
    body = r.json()
    return body.get("email_otp") or body["properties"]["email_otp"]


def signed_in(app, prefix: str, admin: bool = False) -> tuple[BrowserLikeClient, str]:
    """A client signed in as a new verified (optionally admin) test user."""
    email, username = unique(prefix)
    user_id, code = admin_signup(email, username)
    c = BrowserLikeClient(app)
    c.get("/api/auth/csrf")
    assert c.post("/api/auth/verify-email", json={"email": email, "code": code}).status_code == 200
    if admin:
        r = auth.gotrue().call("PATCH", "/profiles", params={"id": f"eq.{user_id}"}, json={"role": "admin"}, rest=True)
        assert r.status_code < 300, r.text
        auth._invalidate_cache()
    return c, user_id


def delete_test_accounts() -> None:
    g = auth.gotrue()
    for user_id, email in created:
        g.call("DELETE", "/security_audit_logs", params={"email_hash": f"eq.{auth._hash(email)}"}, rest=True)
        if user_id:
            g.call("DELETE", "/security_audit_logs", params={"user_id": f"eq.{user_id}"}, rest=True)
            g.call("DELETE", f"/admin/users/{user_id}")
    created.clear()
