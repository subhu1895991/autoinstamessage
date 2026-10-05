"""
Unofficial Instagram DM auto-replier using instagrapi + Groq.

WARNING
-------
This violates Instagram Terms of Service.
Your account can be locked or permanently banned.
Use ONLY a secondary / throwaway account.
"""

import base64
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, TwoFactorRequired

load_dotenv()

IG_USERNAME = os.environ["IG_USERNAME"]
IG_PASSWORD = os.getenv("IG_PASSWORD", "")  # optional on Render if session is provided
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "8"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
# Base64 of session.json contents (for Render)
IG_SESSION_JSON = os.getenv("IG_SESSION_JSON", "").strip()

SESSION_FILE = Path("session.json")
REPLIED_FILE = Path("replied.json")

SYSTEM_PROMPT = (
    "You are a friendly Instagram assistant. "
    "Keep replies short and natural (1-3 sentences). "
    "Do not mention that you are an AI unless asked."
)

groq_client = Groq(api_key=GROQ_API_KEY)


def load_replied() -> set:
    if REPLIED_FILE.exists():
        try:
            return set(json.loads(REPLIED_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_replied(replied: set) -> None:
    items = list(replied)[-2000:]
    REPLIED_FILE.write_text(json.dumps(items), encoding="utf-8")


def ensure_session_file() -> None:
    """If IG_SESSION_JSON is set, write it to session.json."""
    if not IG_SESSION_JSON:
        return
    try:
        raw = base64.b64decode(IG_SESSION_JSON).decode("utf-8")
        # validate json
        json.loads(raw)
        SESSION_FILE.write_text(raw, encoding="utf-8")
        print("Loaded session from IG_SESSION_JSON env")
    except Exception as e:
        print(f"Failed to load IG_SESSION_JSON: {e}")


def login_client() -> Client:
    ensure_session_file()
    cl = Client()
    cl.delay_range = [1, 3]

    # 1) Try existing session without forcing a full password login from cloud IP
    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            # set username so library knows who we are
            cl.username = IG_USERNAME
            cl.get_timeline_feed()
            print("Logged in with saved session (no password login)")
            return cl
        except Exception as e:
            print(f"Saved session invalid ({e})")
            if not IG_PASSWORD:
                raise RuntimeError(
                    "Session expired and IG_PASSWORD is not set. "
                    "Generate a new session.json on your PC and update IG_SESSION_JSON."
                )
            print("Trying password login...")

    if not IG_PASSWORD:
        raise RuntimeError("No valid session and IG_PASSWORD is empty")

    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except TwoFactorRequired:
        print("2FA is enabled. Disable 2FA on the secondary account.")
        raise
    except ChallengeRequired:
        print("Instagram challenge required. Approve on your phone.")
        raise

    cl.dump_settings(SESSION_FILE)
    print("Fresh login successful, session saved")
    return cl


def generate_reply(history: list, latest: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(MAX_HISTORY - 1) :])
    messages.append({"role": "user", "content": latest})

    completion = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=250,
    )
    return (completion.choices[0].message.content or "").strip() or "Hey!"


def get_thread_history(cl: Client, thread_id: str) -> list:
    try:
        thread = cl.direct_thread(thread_id, amount=MAX_HISTORY)
        messages = []
        for m in reversed(thread.messages or []):
            if not m.text:
                continue
            role = "assistant" if m.user_id == cl.user_id else "user"
            messages.append({"role": role, "content": m.text})
        return messages
    except Exception as e:
        print(f"History error for {thread_id}: {e}")
        return []


def process_inbox(cl: Client, replied: set) -> None:
    try:
        threads = cl.direct_threads(amount=20)
    except LoginRequired:
        print("Login required again, re-authenticating...")
        raise
    except Exception as e:
        print(f"Error fetching threads: {e}")
        return

    my_id = cl.user_id

    for thread in threads:
        try:
            if not thread.messages:
                continue

            last = thread.messages[0]

            if last.user_id == my_id:
                continue

            if not last.text:
                continue

            msg_id = str(last.id)
            if msg_id in replied:
                continue

            text = last.text.strip()
            if not text:
                continue

            print(f"New message in thread {thread.id}: {text[:80]}")

            history = get_thread_history(cl, str(thread.id))
            history_without_last = (
                history[:-1]
                if history and history[-1]["role"] == "user"
                else history
            )

            reply = generate_reply(history_without_last, text)
            print(f"AI reply: {reply[:100]}")

            cl.direct_send(reply, thread_ids=[int(thread.id)])
            replied.add(msg_id)
            save_replied(replied)
            print("Reply sent")

            time.sleep(2)

        except Exception as e:
            print(f"Error handling thread {getattr(thread, 'id', '?')}: {e}")
            continue


def main() -> None:
    print("Starting Instagram AI bot...")
    print(f"Account: {IG_USERNAME}")
    print(f"Poll every {POLL_INTERVAL}s | History: {MAX_HISTORY} messages")
    print(f"Model: {GROQ_MODEL}")

    replied = load_replied()
    cl = login_client()

    while True:
        try:
            process_inbox(cl, replied)
        except LoginRequired:
            cl = login_client()
        except Exception as e:
            print(f"Loop error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
