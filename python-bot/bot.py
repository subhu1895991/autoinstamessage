"""
Unofficial Instagram DM auto-replier using instagrapi + Groq.

WARNING
-------
This violates Instagram Terms of Service.
Your account can be locked or permanently banned.
Use ONLY a secondary / throwaway account.
"""

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
IG_PASSWORD = os.environ["IG_PASSWORD"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "8"))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))

SESSION_FILE = Path("session.json")
REPLIED_FILE = Path("replied.json")

SYSTEM_PROMPT = (
    "You are a friendly Instagram assistant. "
    "Keep replies short and natural (1-3 sentences). "
    "Do not mention that you are an AI unless asked."
)

groq_client = Groq(api_key=GROQ_API_KEY)


def load_replied() -> set[str]:
    if REPLIED_FILE.exists():
        try:
            return set(json.loads(REPLIED_FILE.read_text()))
        except Exception:
            return set()
    return set()


def save_replied(replied: set[str]) -> None:
    # Keep file from growing forever
    items = list(replied)[-2000:]
    REPLIED_FILE.write_text(json.dumps(items))


def login_client() -> Client:
    cl = Client()
    cl.delay_range = [1, 3]

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            cl.login(IG_USERNAME, IG_PASSWORD)
            cl.get_timeline_feed()  # validate session
            print("Logged in with saved session")
            return cl
        except Exception as e:
            print(f"Saved session failed ({e}), doing fresh login...")

    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except TwoFactorRequired:
        print("2FA is enabled. Disable 2FA on the secondary account or handle it manually.")
        raise
    except ChallengeRequired:
        print("Instagram challenge required. Open the Instagram app on your phone and approve the login.")
        raise

    cl.dump_settings(SESSION_FILE)
    print("Fresh login successful, session saved")
    return cl


def generate_reply(history: list[dict], latest: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-(MAX_HISTORY - 1) :])
    messages.append({"role": "user", "content": latest})

    completion = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=250,
    )
    return (completion.choices[0].message.content or "").strip() or "Hey! 👋"


def get_thread_history(cl: Client, thread_id: str) -> list[dict]:
    """Return recent messages as OpenAI-style role/content list."""
    try:
        thread = cl.direct_thread(thread_id, amount=MAX_HISTORY)
        messages = []
        # thread.messages is usually newest-first; reverse for chronological order
        for m in reversed(thread.messages or []):
            if not m.text:
                continue
            role = "assistant" if m.user_id == cl.user_id else "user"
            messages.append({"role": role, "content": m.text})
        return messages
    except Exception as e:
        print(f"History error for {thread_id}: {e}")
        return []


def process_inbox(cl: Client, replied: set[str]) -> None:
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

            last = thread.messages[0]  # newest

            # Skip if we already sent the last message
            if last.user_id == my_id:
                continue

            # Skip non-text
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
            # history already includes the latest user message usually;
            # still pass text as the latest turn for clarity
            history_without_last = history[:-1] if history and history[-1]["role"] == "user" else history

            reply = generate_reply(history_without_last, text)
            print(f"AI reply: {reply[:100]}")

            cl.direct_send(reply, thread_ids=[int(thread.id)])
            replied.add(msg_id)
            save_replied(replied)
            print("Reply sent")

            # Small delay to look less robotic
            time.sleep(2)

        except Exception as e:
            print(f"Error handling thread {getattr(thread, 'id', '?')}: {e}")
            continue


def main() -> None:
    print("Starting Instagram AI bot...")
    print(f"Account: {IG_USERNAME}")
    print(f"Poll every {POLL_INTERVAL}s | History: {MAX_HISTORY} messages")

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
