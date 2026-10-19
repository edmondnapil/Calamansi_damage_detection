"""Administrator features, password change and default-admin provisioning (real Supabase).

Uses throw-away accounts that are deleted afterwards and a temporary local
detection store. Run: python -m pytest tests/test_admin.py -v
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import admin  # noqa: E402
import auth  # noqa: E402
import create_admin  # noqa: E402
from fastapi import Depends, FastAPI  # noqa: E402
from helpers import PASSWORD, BrowserLikeClient, created, delete_test_accounts, signed_in, unique  # noqa: E402
from storage import LocalRepository  # noqa: E402

pytestmark = pytest.mark.skipif(not auth.AUTH_ENABLED, reason="Supabase is not configured")
NEW_PASSWORD = "Admin-Panel#2026"

store = LocalRepository(Path(tempfile.mkdtemp(prefix="calamansi_admin_test_")))


def make_app() -> FastAPI:
    app = FastAPI()
    app.middleware("http")(auth.csrf_middleware)
    app.include_router(auth.router)
    app.include_router(admin.router)

    @app.get("/api/protected")
    def protected(user: auth.CurrentUser = Depends(auth.current_user)):
        return {"id": user.id}

    return app


APP = make_app()


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    # Set here, not at import time: importing main (test_api.py) installs the app's own store.
    admin.set_repository_provider(lambda: store)
    yield
    delete_test_accounts()


def login(email: str, password: str) -> tuple[BrowserLikeClient, int]:
    c = BrowserLikeClient(APP)
    c.get("/api/auth/csrf")
    return c, c.post("/api/auth/login", json={"email": email, "password": password}).status_code


def email_of(user_id: str) -> str:
    return next(e for i, e in created if i == user_id)


def test_admin_endpoints_require_an_administrator():
    anon = BrowserLikeClient(APP)
    assert anon.get("/api/admin/overview").status_code == 401
    user, _ = signed_in(APP, "plain")
    for path in ("/api/admin/overview", "/api/admin/users", "/api/admin/activity"):
        assert user.get(path).status_code == 403, path
    assert user.delete(f"/api/admin/users/{'0' * 8}-0000-0000-0000-{'0' * 12}").status_code == 403


def test_overview_counts_come_from_the_database():
    adm, _ = signed_in(APP, "ovadm", admin=True)
    ov = adm.get("/api/admin/overview").json()
    profiles = auth.gotrue().call("GET", "/profiles", params={"select": "id,account_status"}, rest=True).json()
    assert ov["users"]["total"] == len(profiles)
    assert ov["users"]["active"] == sum(p["account_status"] == "active" for p in profiles)
    assert len(ov["registrations_daily"]) == ov["days"] == 14
    assert ov["detections"]["total"] == store.count(owner=None)


def test_search_edit_suspend_and_delete_users():
    adm, admin_id = signed_in(APP, "mgr", admin=True)
    victim, victim_id = signed_in(APP, "managed")
    username = next(u for u in auth.gotrue().call("GET", "/profiles", params={"id": f"eq.{victim_id}", "select": "username"},
                                                  rest=True).json())["username"]
    found = adm.get("/api/admin/users", params={"q": username}).json()
    assert found["total"] == 1 and found["items"][0]["id"] == victim_id and found["items"][0]["email"]
    detail = adm.get(f"/api/admin/users/{victim_id}").json()
    assert detail["detections"]["total"] == 0 and detail["role"] == "user"

    r = adm.patch(f"/api/admin/users/{victim_id}", json={"full_name": "Renamed User", "username": username + "x"[:30 - len(username)]})
    assert r.status_code == 200, r.text
    other_username = auth.gotrue().call("GET", "/profiles", params={"id": f"eq.{admin_id}", "select": "username"}, rest=True).json()[0]["username"]
    assert adm.patch(f"/api/admin/users/{victim_id}", json={"username": other_username}).json()["detail"]["code"] == "username_taken"
    assert adm.patch(f"/api/admin/users/{victim_id}", json={"role": "admin"}).json().get("message") == "Nothing to change."  # role is not editable

    assert adm.patch(f"/api/admin/users/{victim_id}", json={"account_status": "suspended"}).status_code == 200
    # Supabase Auth rejects the suspended user's session at once (401 -> the app returns to sign-in) ...
    assert victim.get("/api/protected").status_code in (401, 403)
    # ... and sign-in gives the generic error: Supabase checks the ban before the password, so a
    # "suspended" message would reveal to anyone that the account exists.
    c, code = login(email_of(victim_id), PASSWORD)
    assert code == 401
    assert adm.patch(f"/api/admin/users/{victim_id}", json={"account_status": "active"}).status_code == 200
    assert login(email_of(victim_id), PASSWORD)[1] == 200

    assert adm.patch(f"/api/admin/users/{admin_id}", json={"account_status": "suspended"}).json()["detail"]["code"] == "self_change"
    assert adm.delete(f"/api/admin/users/{admin_id}").json()["detail"]["code"] == "self_change"
    other_admin, other_admin_id = signed_in(APP, "admin2", admin=True)
    assert adm.delete(f"/api/admin/users/{other_admin_id}").json()["detail"]["code"] == "cannot_delete_admin"

    store.insert({"predicted_class": "Healthy", "confidence": 0.9, "prob_healthy": 0.9, "prob_damaged": 0.1,
                  "image_path": None, "original_filename": "t.jpg", "model_version": "test", "user_id": victim_id})
    r = adm.delete(f"/api/admin/users/{victim_id}")
    assert r.status_code == 200 and "1 detection" in r.json()["message"]
    assert auth.gotrue().call("GET", f"/admin/users/{victim_id}").status_code == 404
    assert store.count(owner=victim_id) == 0


def test_activity_log_hides_hashes():
    adm, _ = signed_in(APP, "actadm", admin=True)
    items = adm.get("/api/admin/activity", params={"page_size": 10}).json()["items"]
    assert items, "activity should contain the test sign-ups"
    assert all("email_hash" not in i and "ip_hash" not in i for i in items)


def test_change_password_signs_out_other_sessions_but_not_this_one():
    me, user_id = signed_in(APP, "chpw")
    email = email_of(user_id)
    other, code = login(email, PASSWORD)
    assert code == 200
    bad = me.post("/api/auth/change-password", json={"current_password": "Wrong#Pass1", "new_password": NEW_PASSWORD})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "wrong_current_password"
    weak = me.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"})
    assert weak.status_code == 422
    ok = me.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200, ok.text
    auth._invalidate_cache()
    assert me.get("/api/protected").status_code == 200       # this browser stays signed in
    assert other.get("/api/protected").status_code == 401    # the other device is signed out
    assert login(email, PASSWORD)[1] == 401 and login(email, NEW_PASSWORD)[1] == 200


def test_default_admin_provisioning_is_idempotent_and_forces_a_password_change():
    g = auth.gotrue()
    real_admins = [a for a in g.call("GET", "/profiles", params={"select": "id", "role": "eq.admin"}, rest=True).json()
                   if a["id"] not in {i for i, _ in created}]
    if real_admins:
        result = create_admin.provision("someone.else@example.com", "X", "someone_else", None, False)
        assert result["status"] == "exists"  # an existing administrator is never replaced
        return
    # Hide this run's test admins so the "no administrator yet" path can be exercised, then restore them.
    test_admins = [i for i, _ in created if g.call("GET", "/profiles", params={"id": f"eq.{i}", "role": "eq.admin"}, rest=True).json()]
    for i in test_admins:
        g.call("PATCH", "/profiles", params={"id": f"eq.{i}"}, json={"role": "user"}, rest=True)
    try:
        email, username = unique("dflt")
        res = create_admin.provision(email, "Default Admin", username, None, False)
        assert res["status"] == "created" and res["password"]
        created.append((res["user_id"], email))
        temp_password = res["password"]
        again = create_admin.provision("another." + email, "X", "another_" + username[:20], None, False)
        assert again["status"] == "exists"  # second run: nothing created, nothing reset
        c, code = login(email, temp_password)
        assert code == 200  # the original temporary password still works
        me = c.get("/api/auth/me").json()["user"]
        assert me["role"] == "admin" and me["must_change_password"] is True
        assert c.get("/api/protected").json()["detail"]["code"] == "password_change_required"
        assert c.get("/api/admin/overview").json()["detail"]["code"] == "password_change_required"
        assert c.post("/api/auth/change-password", json={"current_password": temp_password, "new_password": NEW_PASSWORD}).status_code == 200
        auth._invalidate_cache()
        assert c.get("/api/auth/me").json()["user"]["must_change_password"] is False
        assert c.get("/api/admin/overview").status_code == 200
    finally:
        for i in test_admins:
            g.call("PATCH", "/profiles", params={"id": f"eq.{i}"}, json={"role": "admin"}, rest=True)
