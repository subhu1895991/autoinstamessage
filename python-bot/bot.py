"""
Unofficial Instagram DM auto-replier using instagrapi + Groq.

WARNING: Violates Instagram ToS. Use a secondary account only.
"""

import base64
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, TwoFactorRequired

load_dotenv()

IG_USERNAME = os.environ["IG_USERNAME"]
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
IG_SESSION_JSON = os.getenv("IG_SESSION_JSON", "").strip()
SESSION_ONLY = os.getenv("SESSION_ONLY", "1").strip() in ("1", "true", "True", "yes")
PORT = int(os.getenv("PORT", "10000"))

SESSION_FILE = Path("session.json")
REPLIED_FILE = Path("replied.json")

SYSTEM_PROMPT = (
    "You are a friendly Instagram assistant chatting in DMs. "
    "Reply with ONE short natural message only (1-2 sentences). "
    "Do not ask multiple questions. Do not send lists. "
    "Do not mention that you are an AI unless asked."
)

groq_client = Groq(api_key=GROQ_API_KEY)
_in_flight: set = set()
_status = {"ok": False, "msg": "starting"}
_thread_last_handled: dict = {}
# Our Instagram user id as string (set after login)
MY_USER_ID = ""


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(_status).encode("utf-8")
        self.send_response(200 if _status.get("ok") else 503)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server on port {PORT}")
    server.serve_forever()


def load_replied() -> set:
    if REPLIED_FILE.exists():
        try:
            return set(json.loads(REPLIED_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_replied(replied: set) -> None:
    items = list(replied)[-5000:]
    try:
        REPLIED_FILE.write_text(json.dumps(items), encoding="utf-8")
    except Exception as e:
        print(f"Could not save replied.json: {e}")


def ensure_session_file() -> bool:
    if IG_SESSION_JSON:
        try:
            raw = base64.b64decode(IG_SESSION_JSON).decode("utf-8")
            data = json.loads(raw)
            SESSION_FILE.write_text(json.dumps(data), encoding="utf-8")
            print("Loaded session from IG_SESSION_JSON env")
            return True
        except Exception as e:
            print(f"Failed to decode IG_SESSION_JSON: {e}")
            return False
    return SESSION_FILE.exists()


def resolve_my_user_id(cl: Client, settings: dict) -> str:
    """Get our user id without assigning to cl.user_id (read-only in some versions)."""
    global MY_USER_ID

    # 1) From client after successful login
    try:
        if getattr(cl, "user_id", None):
            MY_USER_ID = str(cl.user_id)
            return MY_USER_ID
    except Exception:
        pass

    # 2) From session settings
    for key in ("ds_user_id", "user_id"):
        if settings.get(key):
            MY_USER_ID = str(settings[key])
            return MY_USER_ID

    auth = settings.get("authorization_data") or {}
    if auth.get("ds_user_id"):
        MY_USER_ID = str(auth["ds_user_id"])
        return MY_USER_ID

    # 3) From account_info API
    try:
        info = cl.account_info()
        MY_USER_ID = str(info.pk)
        return MY_USER_ID
    except Exception as e:
        print(f"account_info failed: {e}")

    # 4) From username lookup
    try:
        uid = cl.user_id_from_username(IG_USERNAME)
        MY_USER_ID = str(uid)
        return MY_USER_ID
    except Exception as e:
        print(f"user_id_from_username failed: {e}")

    return ""


def login_client() -> Client:
    global MY_USER_ID
    has_session = ensure_session_file()
    cl = Client()
    cl.delay_range = [2, 5]

    if has_session and SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            try:
                cl.username = IG_USERNAME
            except Exception:
                pass

            settings = {}
            try:
                settings = cl.get_settings() or {}
            except Exception:
                pass

            sessionid = (settings.get("cookies") or {}).get("sessionid")

            if sessionid:
                cl.login_by_sessionid(sessionid)
                print("Logged in with sessionid (no password)")
            else:
                cl.get_timeline_feed()
                print("Logged in with saved settings")

            my_id = resolve_my_user_id(cl, settings)
            if not my_id:
                raise RuntimeError("Could not resolve user_id — unsafe to run (would spam)")

            print(f"My user_id: {my_id}")
            _status.update({"ok": True, "msg": "logged_in", "user_id": my_id})
            return cl
        except Exception as e:
            print(f"Session login failed: {e}")
            _status.update({"ok": False, "msg": f"session_failed: {e}"})
            if SESSION_ONLY or not IG_PASSWORD:
                raise RuntimeError(
                    "Session invalid/expired. Refresh session.json on PC and "
                    "update IG_SESSION_JSON on Render."
                )

    if SESSION_ONLY:
        raise RuntimeError(
            "SESSION_ONLY=1 and no working session. "
            "Do not password-login from Render (gets 429)."
        )

    if not IG_PASSWORD:
        raise RuntimeError("No session and no IG_PASSWORD")

    print("WARNING: password login (may get 429 on cloud IPs)...")
    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except TwoFactorRequired:
        print("2FA enabled — disable on secondary account.")
        raise
    except ChallengeRequired:
        print("Challenge required — approve on phone.")
        raise

    cl.dump_settings(SESSION_FILE)
    my_id = resolve_my_user_id(cl, {})
    print(f"Fresh login successful, user_id={my_id}")
    _status.update({"ok": True, "msg": "logged_in_password", "user_id": my_id})
    return cl


def generate_reply(history: list, latest: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(MAX_HISTORY - 1) :])
    messages.append({"role": "user", "content": latest})

    completion = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=100,
    )
    text = (completion.choices[0].message.content or "").strip()
    if "\n" in text:
        text = text.split("\n")[0].strip()
    return text or "Hey!"


def get_thread_history(cl: Client, thread_id: str) -> list:
    try:
        thread = cl.direct_thread(thread_id, amount=MAX_HISTORY)
        messages = []
        for m in reversed(thread.messages or []):
            if not m.text:
                continue
            role = "assistant" if str(m.user_id) == MY_USER_ID else "user"
            messages.append({"role": role, "content": m.text})
        return messages
    except Exception as e:
        print(f"History error for {thread_id}: {e}")
        return []


def process_inbox(cl: Client, replied: set) -> None:
    try:
        threads = cl.direct_threads(amount=10)
    except LoginRequired:
        print("Login required again...")
        raise
    except Exception as e:
        print(f"Error fetching threads: {e}")
        return

    if not MY_USER_ID:
        print("ERROR: MY_USER_ID empty — skip cycle to avoid spam")
        return

    for thread in threads:
        try:
            if not thread.messages:
                continue

            last = thread.messages[0]
            last_uid = str(getattr(last, "user_id", ""))
            msg_id = str(last.id)
            thread_id = str(thread.id)

            # ONLY if the other person sent the newest message
            if last_uid == MY_USER_ID:
                continue

            if not getattr(last, "text", None):
                continue

            if msg_id in replied or msg_id in _in_flight:
                continue

            if _thread_last_handled.get(thread_id) == msg_id:
                continue

            text = last.text.strip()
            if not text:
                continue

            _in_flight.add(msg_id)
            replied.add(msg_id)
            _thread_last_handled[thread_id] = msg_id
            save_replied(replied)

            print(f"New USER message in thread {thread_id} from {last_uid}: {text[:80]}")

            history = get_thread_history(cl, thread_id)
            if history and history[-1]["role"] == "user":
                history = history[:-1]

            reply = generate_reply(history, text)
            print(f"AI reply: {reply[:120]}")

            cl.direct_send(reply, thread_ids=[int(thread.id)])
            print("Reply sent (one only — waiting for next user message)")
            time.sleep(4)

        except Exception as e:
            print(f"Error handling thread {getattr(thread, 'id', '?')}: {e}")
            continue


def main() -> None:
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    print("Starting Instagram AI bot...")
    print(f"Account: {IG_USERNAME}")
    print(f"Poll every {POLL_INTERVAL}s | Model: {GROQ_MODEL}")
    print(f"SESSION_ONLY={SESSION_ONLY} | has IG_SESSION_JSON={bool(IG_SESSION_JSON)}")
    print("Rule: ONE reply only when the OTHER person sends a new message")

    replied = load_replied()

    try:
        cl = login_client()
    except Exception as e:
        print(f"Login failed: {e}")
        _status.update({"ok": False, "msg": str(e)})
        while True:
            time.sleep(60)
            try:
                cl = login_client()
                break
            except Exception as e2:
                print(f"Retry login failed: {e2}")

    while True:
        try:
            process_inbox(cl, replied)
            _status.update({"ok": True, "msg": "running", "user_id": MY_USER_ID})
        except LoginRequired:
            try:
                cl = login_client()
            except Exception as e:
                print(f"Re-login failed: {e}")
                time.sleep(60)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(30)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
