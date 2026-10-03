# Python Instagram AI Auto-Reply Bot (Unofficial)

**WARNING: This violates Instagram Terms of Service. Use a secondary account only. Ban risk is real.**

Uses `instagrapi` + Groq. Runs as a long-running process on Render (or any VPS).

## Required environment variables

```
IG_USERNAME=secondary_username
IG_PASSWORD=secondary_password
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
POLL_INTERVAL=8
MAX_HISTORY=10
```

## Local test

```bash
cd python-bot
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python bot.py
```

## Deploy on Render

1. New → Background Worker (preferred) or Web Service
2. Connect this GitHub repo
3. Root Directory: `python-bot`
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `python bot.py`
6. Add the environment variables above
7. Deploy

### Render free tier note
Free Web Services sleep after ~15 minutes of no HTTP traffic.  
For a bot that must stay online, use a **Background Worker** (paid) or a cheap VPS.  
As a workaround on free Web Service you can add a simple HTTP server + external cron ping, but Background Worker / VPS is more reliable.

## First login tips

- Disable 2FA on the secondary account if possible
- First login may trigger an Instagram security challenge — open the Instagram app and approve it
- Session is saved to `session.json` so it reuses login
