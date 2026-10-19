"""Create the first administrator account (one-time, server-side setup command).

This is deliberately a command-line tool and NOT a web endpoint, so nobody can
create an administrator through the website. It uses the service-role key from
backend/.env and Supabase Auth's admin API, so the password is hashed by
Supabase Auth exactly like every other account.

Safe to run more than once (idempotent):
  * if an administrator already exists, nothing is changed: no new account,
    no password reset, no role change;
  * if the e-mail already belongs to an ordinary account, it is NOT promoted
    unless you pass --promote-existing (its password is never touched).

The new account is marked "must change password": after the first sign-in the
app (and the API) allows nothing until a new password has been chosen.

Usage (backend folder, virtual environment active):
    python create_admin.py --email admin@your-school.edu.ph
    python create_admin.py --email you@example.com --name "Juan Dela Cruz" --username jdelacruz
    python create_admin.py --email existing@example.com --promote-existing

Settings can also come from environment variables / backend/.env:
    ADMIN_EMAIL, ADMIN_FULL_NAME, ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD
If no initial password is given, a strong random one is generated and printed
ONCE on this console. It is not stored anywhere else.
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

import auth


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!#$%*-_=+?"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(16))
        if not auth.password_problems(pw):
            return pw


def provision(email: str, full_name: str, username: str, password: str | None, promote_existing: bool) -> dict:
    """Returns {"status": "exists" | "created" | "promoted" | "refused", ...}. Never prints secrets itself."""
    if not auth.AUTH_ENABLED:
        raise SystemExit("Supabase is not configured in backend/.env (SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY).")
    g = auth.gotrue()
    r = g.call("GET", "/profiles", params={"select": "id,username,full_name", "role": "eq.admin"}, rest=True)
    if r.status_code >= 300:
        raise SystemExit("Could not read profiles. Has supabase/migrations/002_auth_profiles.sql been run?")
    admins = r.json()
    if admins:
        return {"status": "exists", "admins": [a["username"] for a in admins]}

    email = email.strip().lower()
    if not auth.EMAIL_RE.match(email):
        raise SystemExit(f"Not a valid e-mail address: {email!r}")
    username = username.strip().lower()
    if not auth.USERNAME_RE.match(username):
        raise SystemExit("Username must be 3-30 characters: lowercase letters, numbers or _.")

    status = auth._email_status(email)
    if status != "none":
        if not promote_existing:
            return {"status": "refused", "reason": f"{email} already has an account ({status}). "
                                                    "Re-run with --promote-existing to make that account the administrator."}
        if status != "verified":
            return {"status": "refused", "reason": f"{email} has not verified its e-mail yet; verify it first."}
        users = g.call("GET", "/admin/users", params={"per_page": 1000}).json().get("users", [])
        user = next(u for u in users if (u.get("email") or "").lower() == email)
        g.call("PATCH", "/profiles", params={"id": f"eq.{user['id']}"}, json={"role": "admin"}, rest=True)
        auth.audit("admin_provisioned", "success", user_id=user["id"], via="create_admin.py promote")
        return {"status": "promoted", "email": email}

    if g.call("GET", "/profiles", params={"select": "id", "username": f"eq.{username}"}, rest=True).json():
        raise SystemExit(f"The username {username!r} is already taken; choose another with --username.")
    generated = password is None
    password = password or _generate_password()
    problems = auth.password_problems(password, email, username)
    if problems:
        raise SystemExit("ADMIN_INITIAL_PASSWORD must contain " + ", ".join(problems) + ".")

    r = g.call("POST", "/admin/users", json={
        "email": email, "password": password, "email_confirm": True,
        "user_metadata": {"full_name": full_name, "username": username},
        "app_metadata": {"must_change_password": True}})
    if r.status_code >= 300:
        raise SystemExit(f"Supabase refused to create the account: {r.text[:300]}")
    user_id = r.json()["id"]
    p = g.call("PATCH", "/profiles", params={"id": f"eq.{user_id}"}, json={"role": "admin"}, rest=True)
    if p.status_code >= 300:
        g.call("DELETE", f"/admin/users/{user_id}")  # do not leave a half-provisioned account behind
        raise SystemExit(f"Could not assign the administrator role: {p.text[:300]}")
    auth.audit("admin_provisioned", "success", user_id=user_id, via="create_admin.py")
    return {"status": "created", "email": email, "username": username, "user_id": user_id,
            "password": password if generated else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", default=os.getenv("ADMIN_EMAIL"))
    ap.add_argument("--name", default=os.getenv("ADMIN_FULL_NAME", "System Administrator"))
    ap.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
    ap.add_argument("--promote-existing", action="store_true",
                    help="make an existing, verified account with this e-mail the administrator")
    args = ap.parse_args()
    if not args.email:
        raise SystemExit("Give the administrator e-mail with --email or ADMIN_EMAIL.")

    result = provision(args.email, args.name, args.username, os.getenv("ADMIN_INITIAL_PASSWORD") or None,
                       args.promote_existing)
    if result["status"] == "exists":
        print(f"An administrator already exists ({', '.join(result['admins'])}). Nothing was changed.")
    elif result["status"] == "refused":
        print(result["reason"])
        sys.exit(1)
    elif result["status"] == "promoted":
        print(f"{result['email']} is now the administrator. Its password was not changed.")
    else:
        print("Administrator account created.")
        print("  Sign in at:  http://localhost:8000/login")
        print(f"  Email:       {result['email']}")
        print(f"  Username:    {result['username']}")
        if result["password"]:
            print(f"  Temporary password (shown only now, copy it): {result['password']}")
        else:
            print("  Temporary password: the value of ADMIN_INITIAL_PASSWORD")
        print("You will be asked to choose a new password right after the first sign-in.")


if __name__ == "__main__":
    main()
