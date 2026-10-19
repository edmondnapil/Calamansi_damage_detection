"""Administrator API: overview statistics, user management and security activity.

Every endpoint requires an active, verified account whose profiles.role is
'admin' (auth.admin_user). Roles themselves are never changed here: an
administrator is provisioned with create_admin.py or SQL, so a compromised
admin session cannot create further administrators.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import USERNAME_RE, AuthError, CurrentUser, _invalidate_cache, admin_user, audit, gotrue
from storage import APP_TZ, Repository, daily_series

router = APIRouter(prefix="/api/admin", tags=["admin"])

_repo_provider: Callable[[], Repository] | None = None


def set_repository_provider(fn: Callable[[], Repository]) -> None:
    """main.py passes its detection-store accessor (avoids a circular import)."""
    global _repo_provider
    _repo_provider = fn


def _repo() -> Repository:
    if _repo_provider is None:
        raise HTTPException(503, "Detection storage is not available.")
    return _repo_provider()


# --------------------------------------------------------------------------- data access helpers
def _profiles(params: dict | None = None) -> list[dict]:
    r = gotrue().call("GET", "/profiles", params={"select": "*", "order": "created_at.desc", "limit": "5000",
                                                 **(params or {})}, rest=True)
    if r.status_code >= 300:
        raise HTTPException(503, "Could not load accounts.")
    return r.json()


def _auth_users() -> dict[str, dict]:
    """id -> Supabase Auth user (e-mail, last sign-in). Paged so it also works for >1000 users."""
    out, page = {}, 1
    while True:
        r = gotrue().call("GET", "/admin/users", params={"page": page, "per_page": 1000})
        if r.status_code >= 300:
            raise HTTPException(503, "Could not load accounts.")
        users = r.json().get("users", [])
        out.update({u["id"]: u for u in users})
        if len(users) < 1000:
            return out
        page += 1


def _account(p: dict, u: dict | None) -> dict:
    u = u or {}
    return {"id": p["id"], "full_name": p["full_name"], "username": p["username"], "role": p["role"],
            "account_status": p["account_status"], "email": u.get("email"),
            "email_verified_at": p.get("email_verified_at"), "created_at": p["created_at"],
            "updated_at": p.get("updated_at"), "last_sign_in_at": u.get("last_sign_in_at"),
            "must_change_password": bool((u.get("app_metadata") or {}).get("must_change_password"))}


def _local_day(ts: str) -> date:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(APP_TZ).date()


def _get_profile(user_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
        raise HTTPException(404, "User not found.")
    rows = _profiles({"id": f"eq.{user_id}"})
    if not rows:
        raise HTTPException(404, "User not found.")
    return rows[0]


# --------------------------------------------------------------------------- overview
@router.get("/overview")
def overview(days: int = Query(14, ge=7, le=90), _: CurrentUser = Depends(admin_user)):
    """Live statistics for the administrator dashboard (accounts, detections, activity)."""
    profiles = _profiles()
    users = _auth_users()
    today = datetime.now(APP_TZ).date()
    since = today - timedelta(days=days - 1)
    week_ago = today - timedelta(days=6)

    reg_by_day = Counter(_local_day(p["created_at"]) for p in profiles)
    registrations = [{"date": (since + timedelta(days=i)).isoformat(), "count": reg_by_day.get(since + timedelta(days=i), 0)}
                     for i in range(days)]
    store = _repo()
    rows = store.rows_between(since, today, owner=None)
    recent_logs = gotrue().call("GET", "/security_audit_logs", params={
        "select": "event_type,event_status,user_id,created_at", "order": "created_at.desc", "limit": "12"}, rest=True)
    names = {p["id"]: p["full_name"] for p in profiles}
    activity = [{**a, "user_name": names.get(a.get("user_id"))} for a in (recent_logs.json() if recent_logs.status_code < 300 else [])]
    signed_in_7d = sum(1 for u in users.values() if u.get("last_sign_in_at") and _local_day(u["last_sign_in_at"]) >= week_ago)

    return {
        "users": {
            "total": len(profiles),
            "active": sum(p["account_status"] == "active" for p in profiles),
            "suspended": sum(p["account_status"] == "suspended" for p in profiles),
            "verified": sum(bool(p.get("email_verified_at")) for p in profiles),
            "unverified": sum(not p.get("email_verified_at") for p in profiles),
            "admins": sum(p["role"] == "admin" for p in profiles),
            "new_last_7_days": sum(_local_day(p["created_at"]) >= week_ago for p in profiles),
            "signed_in_last_7_days": signed_in_7d,
        },
        "detections": {
            "total": store.count(owner=None),
            "healthy": store.count("Healthy", owner=None),
            "damaged": store.count("Damaged", owner=None),
            "in_period": len(rows),
        },
        "days": days,
        "registrations_daily": registrations,
        "detections_daily": daily_series(rows, since, today),
        "recent_registrations": [_account(p, users.get(p["id"])) for p in profiles[:6]],
        "recent_activity": activity,
    }


# --------------------------------------------------------------------------- users
@router.get("/users")
def list_users(q: str | None = Query(None, max_length=100),
               status: Literal["active", "suspended"] | None = None,
               role: Literal["user", "admin"] | None = None,
               verified: bool | None = None,
               page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
               _: CurrentUser = Depends(admin_user)):
    users = _auth_users()
    items = [_account(p, users.get(p["id"])) for p in _profiles()]
    if q:
        needle = q.strip().lower()
        items = [i for i in items if needle in i["full_name"].lower() or needle in i["username"].lower()
                 or needle in (i["email"] or "").lower()]
    if status:
        items = [i for i in items if i["account_status"] == status]
    if role:
        items = [i for i in items if i["role"] == role]
    if verified is not None:
        items = [i for i in items if bool(i["email_verified_at"]) == verified]
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size,
            "pages": max(1, -(-total // page_size))}


@router.get("/users/{user_id}")
def user_detail(user_id: str, _: CurrentUser = Depends(admin_user)):
    p = _get_profile(user_id)
    u = gotrue().call("GET", f"/admin/users/{user_id}")
    store = _repo()
    recent, total = store.list(search=None, predicted_class=None, date_from=None, date_to=None, offset=0, limit=5,
                               owner=user_id)
    return {**_account(p, u.json() if u.status_code == 200 else None),
            "detections": {"total": total, "healthy": store.count("Healthy", owner=user_id),
                           "damaged": store.count("Damaged", owner=user_id),
                           "recent": [{k: r.get(k) for k in ("id", "predicted_class", "confidence", "created_at",
                                                             "original_filename")} for r in recent]}}


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=100)
    username: str | None = Field(None, min_length=3, max_length=30)
    account_status: Literal["active", "suspended"] | None = None


@router.patch("/users/{user_id}")
def update_user(user_id: str, body: UserUpdate, request: Request, admin: CurrentUser = Depends(admin_user)):
    p = _get_profile(user_id)
    changes: dict = {}
    if body.full_name is not None:
        name = " ".join(body.full_name.split())
        if not name:
            raise AuthError(422, "The full name cannot be empty.", "invalid_name")
        if name != p["full_name"]:
            changes["full_name"] = name
    if body.username is not None:
        username = body.username.strip().lower()
        if not USERNAME_RE.match(username):
            raise AuthError(422, "Username must be 3-30 characters: lowercase letters, numbers or _.", "invalid_username")
        if username != p["username"]:
            if _profiles({"username": f"eq.{username}"}):
                raise AuthError(409, "This username is already taken.", "username_taken")
            changes["username"] = username
    if body.account_status is not None and body.account_status != p["account_status"]:
        if user_id == admin.id:
            raise AuthError(400, "You cannot suspend your own account.", "self_change")
        changes["account_status"] = body.account_status
    if not changes:
        return {"message": "Nothing to change.", "user": _account(p, None)}

    r = gotrue().call("PATCH", "/profiles", params={"id": f"eq.{user_id}"}, json=changes, rest=True)
    if r.status_code >= 300:
        raise HTTPException(400, "The account could not be updated.")
    if "account_status" in changes:
        # Also block/unblock sign-in in Supabase Auth; a suspended user's sessions stop on the next request.
        gotrue().call("PUT", f"/admin/users/{user_id}",
                      json={"ban_duration": "876000h" if changes["account_status"] == "suspended" else "none"})
    _invalidate_cache()
    audit("admin_user_update", "success", user_id=user_id, request=request, by=admin.id, fields=sorted(changes))
    return {"message": "The account has been updated.", "user": _account({**p, **changes}, None)}


@router.delete("/users/{user_id}")
def delete_user(user_id: str, request: Request, admin: CurrentUser = Depends(admin_user)):
    """Delete an ordinary account together with its detections and stored images."""
    p = _get_profile(user_id)
    if user_id == admin.id:
        raise AuthError(400, "You cannot delete your own account.", "self_change")
    if p["role"] == "admin":
        raise AuthError(400, "Administrator accounts cannot be deleted here. Change the role with SQL first.",
                        "cannot_delete_admin")
    removed = _repo().delete_owner_records(user_id)
    r = gotrue().call("DELETE", f"/admin/users/{user_id}")  # profiles row is removed by ON DELETE CASCADE
    if r.status_code >= 300:
        raise HTTPException(400, "The account could not be deleted.")
    _invalidate_cache()
    audit("admin_user_delete", "success", request=request, by=admin.id, detections_removed=removed)
    return {"message": f"The account and its {removed} detection(s) have been deleted."}


# --------------------------------------------------------------------------- activity
@router.get("/activity")
def activity(event_type: str | None = Query(None, pattern=r"^[a-z_]{3,40}$"),
             status: Literal["success", "failure", "blocked"] | None = None,
             page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
             _: CurrentUser = Depends(admin_user)):
    """Security events. E-mail/IP are stored only as keyed hashes and are not returned."""
    params = [("select", "id,event_type,event_status,user_id,created_at,metadata"), ("order", "created_at.desc"),
              ("offset", str((page - 1) * page_size)), ("limit", str(page_size))]
    if event_type:
        params.append(("event_type", f"eq.{event_type}"))
    if status:
        params.append(("event_status", f"eq.{status}"))
    g = gotrue()
    r = g.rest.request("GET", "/security_audit_logs", params=params, headers={**g._headers(), "Prefer": "count=exact"})
    if r.status_code >= 300:
        raise HTTPException(503, "Could not load the activity log.")
    total = int(r.headers.get("content-range", "*/0").split("/")[-1] or 0)
    names = {p["id"]: p["full_name"] for p in _profiles({"select": "id,full_name"})}
    safe_meta = ("via", "reason", "fields", "status", "detections_removed")
    items = [{**{k: v for k, v in e.items() if k != "metadata"}, "user_name": names.get(e.get("user_id")),
              "details": {k: v for k, v in (e.get("metadata") or {}).items() if k in safe_meta}}
             for e in r.json()]
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))}
