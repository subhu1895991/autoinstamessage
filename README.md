# Auto Insta Message

AI-powered auto-replies for **Instagram DMs** using **Groq**.

- Receives messages via Meta webhooks
- Keeps the **last 10 messages** of conversation context per user
- Generates a natural reply with Groq (Llama models)
- Sends the reply back through the Instagram Messaging API
- Ready to deploy on **Vercel**

---

## 1. What you need

| Item | Where to get it |
|------|-----------------|
| Instagram **Professional** account (Business or Creator) | Instagram app |
| Facebook **Page** linked to that Instagram account | Facebook |
| Meta App | [developers.facebook.com](https://developers.facebook.com) |
| Groq API key | [console.groq.com/keys](https://console.groq.com/keys) |
| GitHub account + this repo | already done |
| Vercel account | [vercel.com](https://vercel.com) |

---

## 2. Deploy to Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import this GitHub repository (`subhu1895991/autoinstamessage`)
3. Add these **Environment Variables**:

| Name | Value |
|------|-------|
| `GROQ_API_KEY` | your Groq key |
| `PAGE_ACCESS_TOKEN` | long-lived Page Access Token from Meta |
| `VERIFY_TOKEN` | any secret string you invent (e.g. `my_verify_token_xyz`) |
| `APP_SECRET` | App Secret from Meta App Dashboard → Settings → Basic |

4. Click **Deploy**
5. Copy your production URL, e.g. `https://autoinstamessage.vercel.app`

Webhook endpoint will be:
```
https://YOUR-PROJECT.vercel.app/api/webhook
```

---

## 3. Meta / Facebook Developer setup (detailed)

See the section **"What to do on developers.facebook.com"** below, or follow the checklist in the chat.

---

## 4. Local development (optional)

```bash
npm install
cp .env.example .env.local
# fill in the values
npm run dev
```

For webhooks locally you need a tunnel (ngrok, cloudflared, etc.):
```bash
ngrok http 3000
# then put https://xxxx.ngrok.io/api/webhook as the Callback URL
```

---

## 5. How it works

1. User sends a DM to your Instagram Professional account
2. Meta sends a POST to `/api/webhook`
3. We store the message and load the last 10 messages for that user
4. Groq generates a reply using that history
5. We send the reply back via `POST /me/messages`

Conversation history is currently stored **in-memory**. It works for testing. For production, replace `src/lib/store.ts` with Vercel KV or Upstash Redis.

---

## 6. Environment variables reference

```env
GROQ_API_KEY=...
PAGE_ACCESS_TOKEN=...
VERIFY_TOKEN=...
APP_SECRET=...

# Optional
GROQ_MODEL=llama-3.3-70b-versatile
SYSTEM_PROMPT=You are a friendly Instagram assistant...
```

---

## License

MIT – use freely.
