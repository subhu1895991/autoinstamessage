"""
Unofficial Instagram DM auto-replier using instagrapi + Groq.

WARNING: Violates Instagram ToS. Use a secondary account only.
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
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "12"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))
IG_SESSION_JSON = os.getenv("IG_SESSION_JSON", "").strip()

SESSION_FILE = Path("session.json")
REPLIED_FILE = Path("replied.json")

SYSTEM_PROMPT = (
    "You are a friendly Instagram assistant chatting in DMs. "
    "Reply with ONE short natural message only (1-2 sentences). "
    "Do not ask multiple questions. Do not send lists. "
    "Do not mention that you are an AI unless asked."
)

groq_client = Groq(api_key=GROQ_API_KEY)

# In-memory lock so the same message is never handled twice in one process
_in_flight: set = set()


def load_replied() -> set:
    if REPLIED_FILE.exists():
        try:
            return set(json.loads(REPLIED_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_replied(replied: set) -> None:
    items = list(replied)[-3000:]
    REPLIED_FILE.write_text(json.dumps(items), encoding="utf-8")


def ensure_session_file() -> None:
    if not IG_SESSION_JSON:
        return
    try:
        raw = base64.b64decode(IG_SESSION_JSON).decode("utf-8")
        json.loads(raw)
        SESSION_FILE.write_text(raw, encoding="utf-8")
        print("Loaded session from IG_SESSION_JSON env")
    except Exception as e:
        print(f"Failed to load IG_SESSION_JSON: {e}")


def login_client() -> Client:
    ensure_session_file()
    cl = Client()
    cl.delay_range = [2, 5]

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.username = IG_USERNAME
            cl.get_timeline_feed()
            print("Logged in with saved session (no password login)")
            return cl
        except Exception as e:
            print(f"Saved session invalid ({e})")
            if not IG_PASSWORD:
                raise RuntimeError(
                    "Session expired. Make a new session.json on your PC "
                    "and update IG_SESSION_JSON on Render."
                )
            print("Trying password login...")

    if not IG_PASSWORD:
        raise RuntimeError("No valid session and IG_PASSWORD is empty")

    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except TwoFactorRequired:
        print("2FA enabled — disable it on the secondary account.")
        raise
    except ChallengeRequired:
        print("Challenge required — approve on your phone.")
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
        max_tokens=120,
    )
    text = (completion.choices[0].message.content or "").strip()
    # Keep only the first paragraph / first 2 sentences worth
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
            role = "assistant" if m.user_id == cl.user_id else "user"
            messages.append({"role": role, "content": m.text})
        return messages
    except Exception as e:
        print(f"History error for {thread_id}: {e}")
        return []


def process_inbox(cl: Client, replied: set) -> None:
    try:
        threads = cl.direct_threads(amount=15)
    except LoginRequired:
        print("Login required again...")
        raise
    except Exception as e:
        print(f"Error fetching threads: {e}")
        return

    my_id = cl.user_id

    for thread in threads:
        try:
            if not thread.messages:
                continue

            last = thread.messages[0]  # newest message

            # ONLY reply if the other person sent the latest message
            if last.user_id == my_id:
                continue

            if not getattr(last, "text", None):
                continue

            msg_id = str(last.id)

            # Already replied to this exact message (disk or memory)
            if msg_id in replied or msg_id in _in_flight:
                continue

            text = last.text.strip()
            if not text:
                continue

            # Lock immediately so the next poll cannot double-send
            _in_flight.add(msg_id)
            replied.add(msg_id)
            save_replied(replied)

            print(f"New message in thread {thread.id}: {text[:80]}")

            history = get_thread_history(cl, str(thread.id))
            # Drop the last user message from history; we pass it as `latest`
            if history and history[-1]["role"] == "user":
                history = history[:-1]

            reply = generate_reply(history, text)
            print(f"AI reply: {reply[:120]}")

            cl.direct_send(reply, thread_ids=[int(thread.id)])
            print("Reply sent (one message only)")

            time.sleep(3)

        except Exception as e:
            print(f"Error handling thread {getattr(thread, 'id', '?')}: {e}")
            continue


def main() -> None:
    print("Starting Instagram AI bot...")
    print(f"Account: {IG_USERNAME}")
    print(f"Poll every {POLL_INTERVAL}s | History: {MAX_HISTORY}")
    print(f"Model: {GROQ_MODEL}")
    print("Rule: ONE reply per incoming message from the other person only")

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
