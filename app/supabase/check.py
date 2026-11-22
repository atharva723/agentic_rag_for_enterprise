"""Is the Supabase project set up right? Run it after you edit .env, and again after you run supabase/schema.sql.

    python -m app.supabase.check               a quick read-only check (a few calls, nothing is created)
    python -m app.supabase.check --isolation   also proves that one user cannot see or change another user's chats

--isolation makes two throwaway users with the secret key, tries to break the rules as each of them, then deletes both users and
everything they made. It is not part of pytest: it needs your project and your keys. No key or token is ever printed.
"""
import argparse
import base64
import json
import secrets
import sys
from datetime import datetime

from app.config import get_settings
from app.supabase.client import SupabaseError, configured, request

failed: list[str] = []


def step(ok: bool, text: str, hint: str = "") -> bool:
    print(f"  {'ok  ' if ok else 'FAIL'} {text}")
    if not ok:
        failed.append(text)
        if hint:
            print(f"       -> {hint}")
    return ok


def kind(key: str) -> str:
    """"publishable", "secret" or "unknown". Only the kind of key is read; the key itself is never shown."""
    if key.startswith("sb_publishable_"):
        return "publishable"
    if key.startswith("sb_secret_"):
        return "secret"
    try:  # an old-style key is a token that names its own role
        part = key.split(".")[1]
        role = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))).get("role")
    except (IndexError, ValueError, AttributeError):
        return "unknown"
    return {"anon": "publishable", "service_role": "secret"}.get(role, "unknown")


def why(reply) -> str:
    """The reason Supabase gave for a failed call. It never contains a key."""
    body = reply.json() if reply.content else {}
    return str(body.get("message") or body.get("msg") or body.get("error_description") or "") if isinstance(body, dict) else ""


def quick() -> None:
    """The read-only checks."""
    print("Settings")
    if not step(configured(), "SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY are set", "put them in .env (Project Settings in the Supabase dashboard)"):
        return
    step(
        kind(get_settings().supabase_publishable_key) == "publishable",
        "SUPABASE_PUBLISHABLE_KEY is a publishable key",
        "that value is not a publishable key. If it is the secret key, swap them: only the publishable key may ever be shown in a browser",
    )

    print("Project")
    reply = request("GET", "/auth/v1/settings")
    if not step(reply.status_code == 200, "the project answers", f"HTTP {reply.status_code}: check SUPABASE_URL and the publishable key"):
        return
    auth = reply.json()
    print(
        f"       email login: {'on' if auth.get('external', {}).get('email') else 'OFF'}"
        f" | sign-ups: {'closed' if auth.get('disable_signup') else 'open'}"
        f" | email confirmation: {'off (a new user can sign in at once)' if auth.get('mailer_autoconfirm') else 'on (a new user must click an emailed link first)'}"
    )
    reply = request("GET", "/auth/v1/.well-known/jwks.json")
    algorithms = sorted({key.get("alg", "?") for key in reply.json().get("keys", [])}) if reply.status_code == 200 else []
    step(
        bool(algorithms),
        f"login tokens are signed with a public key ({', '.join(algorithms) or 'none'}), so our server can check them without calling Supabase",
        "this project still uses the old shared secret. In Project Settings > JWT Keys, switch to the new signing keys",
    )

    print("Tables (supabase/schema.sql)")
    for table in ("conversations", "messages"):
        reply = request("GET", f"/rest/v1/{table}", params={"select": "id", "limit": 1})
        if not step(reply.status_code != 404, f"{table} exists", "run supabase/schema.sql in the Supabase SQL editor"):
            continue
        nothing = reply.status_code in (401, 403) or (reply.status_code == 200 and reply.json() == [])
        step(nothing, f"{table}: someone who is not signed in gets nothing", f"HTTP {reply.status_code}: the table is open to anyone. Run supabase/schema.sql again")


def isolation() -> None:
    """Two users try to reach each other's chats. The secret key is used only to make and delete them and to look behind the rules."""
    print("Isolation (two throwaway users)")
    secret = get_settings().supabase_secret_key
    if not step(kind(secret) == "secret", "SUPABASE_SECRET_KEY is set and is a secret key", "only this test needs it (Project Settings > API Keys). The running app never does"):
        return

    def admin(method, path, **kw):
        return request(method, path, key=secret, **kw)

    def rest(method, table, token=None, **kw):
        return request(method, f"/rest/v1/{table}", token=token, **kw)

    def rows(reply):
        return reply.json() if reply.status_code < 300 and reply.content else []

    def blocked(reply):  # refused outright, or allowed but it touched nothing. Any other answer (400, 404...) is a surprise, not a pass
        return reply.status_code in (401, 403) or (reply.status_code < 300 and rows(reply) == [])

    ids, tokens, label, back = [], [], secrets.token_hex(3), {"Prefer": "return=representation"}
    try:
        for name in ("a", "b"):
            email, password = f"rls-check-{label}-{name}@example.com", secrets.token_urlsafe(18)
            made = admin("POST", "/auth/v1/admin/users", json={"email": email, "password": password, "email_confirm": True})
            if not step(made.status_code == 200, f"user {name.upper()} created", f"HTTP {made.status_code}: {why(made)}"):
                return
            ids.append(made.json()["id"])
            login = request("POST", "/auth/v1/token", params={"grant_type": "password"}, json={"email": email, "password": password})
            if not step(login.status_code == 200, f"user {name.upper()} signs in with email and password", f"HTTP {login.status_code}: {why(login)}"):
                return
            tokens.append(login.json()["access_token"])
        (a, b), (ta, tb) = ids, tokens

        made = rest("POST", "conversations", ta, json={"title": "isolation check"}, headers=back)
        chat = rows(made)[0] if rows(made) else {}
        if not step(chat.get("user_id") == a, "A creates a chat, and the database stamps it with A's id", f"HTTP {made.status_code}: {why(made)}"):
            return
        cid = chat["id"]
        pair = [  # the same keys in both rows, so both fill the same columns
            {"conversation_id": cid, "role": "user", "content": "hello", "source_used": None, "citations": None, "trace": None, "latency_ms": None},
            {"conversation_id": cid, "role": "assistant", "content": "hi", "source_used": "direct", "citations": [], "trace": ["Direct answer (no search)"], "latency_ms": 5},
        ]
        saved = rest("POST", "messages", ta, json=pair, headers=back)
        step(saved.status_code == 201 and len(rows(saved)) == 2, "A saves a question and its answer in one request", f"HTTP {saved.status_code}: {why(saved)}")
        now = rows(rest("GET", "conversations", ta, params={"id": f"eq.{cid}"}))
        step(bool(now) and datetime.fromisoformat(now[0]["updated_at"]) > datetime.fromisoformat(chat["updated_at"]), "saving messages moves the chat to the top of A's list")
        thread = rows(rest("GET", "messages", ta, params={"conversation_id": f"eq.{cid}", "order": "id"}))
        step([m["role"] for m in thread] == ["user", "assistant"], "A reads the messages back in order")

        step(rows(rest("GET", "conversations", tb)) == [], "B's chat list is empty: B cannot see A's chat")
        step(rows(rest("GET", "messages", tb, params={"conversation_id": f"eq.{cid}"})) == [], "B cannot read A's messages")
        step(blocked(rest("POST", "messages", tb, json={"conversation_id": cid, "role": "user", "content": "intruder"}, headers=back)), "B cannot add a message to A's chat")
        step(blocked(rest("PATCH", "conversations", tb, params={"id": f"eq.{cid}"}, json={"title": "hacked"}, headers=back)), "B cannot rename A's chat")
        step(blocked(rest("DELETE", "conversations", tb, params={"id": f"eq.{cid}"}, headers=back)), "B cannot delete A's chat")
        again = rows(rest("GET", "conversations", ta, params={"id": f"eq.{cid}"}))
        step(bool(again) and again[0]["title"] == "isolation check", "after B's attempts, A's chat is exactly as it was")
        renamed = rows(rest("PATCH", "conversations", ta, params={"id": f"eq.{cid}"}, json={"title": "renamed"}, headers=back))
        step(bool(renamed) and renamed[0]["title"] == "renamed", "A renames A's own chat (the same request B's attempt used)")

        step(blocked(rest("POST", "conversations", ta, json={"user_id": b, "title": "forged"}, headers=back)), "A cannot create a chat in B's name")
        step(blocked(rest("POST", "messages", ta, json={"conversation_id": cid, "user_id": b, "role": "user", "content": "forged"}, headers=back)), "A cannot create a message in B's name")
        step(blocked(rest("PATCH", "messages", ta, params={"conversation_id": f"eq.{cid}"}, json={"content": "edited"}, headers=back)), "nobody can edit a saved message, not even its owner")
        step(blocked(rest("DELETE", "messages", ta, params={"conversation_id": f"eq.{cid}"}, headers=back)), "nobody can delete a single message, not even its owner")
        for table in ("conversations", "messages"):
            step(blocked(rest("GET", table)), f"{table}: someone who is not signed in sees nothing")

        step(len(rows(rest("POST", "conversations", tb, json={"title": "B's own chat"}, headers=back))) == 1, "B creates B's own chat (so deleting B's account has something to remove too)")
        step(len(rows(rest("DELETE", "conversations", ta, params={"id": f"eq.{cid}"}, headers=back))) == 1, "A deletes A's own chat")
        step(rows(admin("GET", "/rest/v1/messages", params={"conversation_id": f"eq.{cid}"})) == [], "deleting a chat deletes its messages too (looked at with the secret key)")
    except Exception as exc:  # an odd reply or a dropped connection: say so, and still clean up below
        step(False, "the isolation test stopped early", f"{type(exc).__name__}: {exc}")
    finally:
        deleted = [admin("DELETE", f"/auth/v1/admin/users/{user}").status_code for user in ids]
        if ids:
            owned = {"user_id": f"in.({','.join(ids)})"}
            left = rows(admin("GET", "/rest/v1/conversations", params=owned)) + rows(admin("GET", "/rest/v1/messages", params=owned))
            step(all(code == 200 for code in deleted) and not left, "both test users and everything they made are deleted", "delete the users whose email starts with rls-check- in Authentication > Users")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check that the Supabase project is set up right.")
    parser.add_argument("--isolation", action="store_true", help="also prove that users cannot reach each other's chats (makes and deletes two test users)")
    args = parser.parse_args()
    try:
        quick()
        if args.isolation and failed:
            print("\nSkipping the isolation test until the checks above pass.")
        elif args.isolation:
            isolation()
    except SupabaseError as exc:
        step(False, "Supabase could not be used", str(exc))
    if failed:
        print(f"\n{len(failed)} problem(s). Fix the FAIL lines above, then run this again.")
        return 1
    print("\nAll good." + ("" if args.isolation else " Add --isolation to prove that users cannot see each other's chats."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
