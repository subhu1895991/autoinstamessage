import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { addMessage, getHistory } from "@/lib/store";
import { generateReply } from "@/lib/groq";
import { sendInstagramMessage } from "@/lib/instagram";

/**
 * GET = Webhook verification (Meta sends this when you set the Callback URL)
 */
export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const mode = searchParams.get("hub.mode");
  const token = searchParams.get("hub.verify_token");
  const challenge = searchParams.get("hub.challenge");

  const verifyToken = process.env.VERIFY_TOKEN;

  if (mode === "subscribe" && token === verifyToken) {
    console.log("Webhook verified successfully");
    return new NextResponse(challenge, { status: 200 });
  }

  console.warn("Webhook verification failed");
  return new NextResponse("Forbidden", { status: 403 });
}

/**
 * Optional: verify X-Hub-Signature-256 from Meta
 */
function verifySignature(rawBody: string, signatureHeader: string | null): boolean {
  const appSecret = process.env.APP_SECRET;
  if (!appSecret) {
    // If no secret configured, skip signature check (not recommended for production)
    return true;
  }

  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return false;
  }

  const expected =
    "sha256=" +
    crypto.createHmac("sha256", appSecret).update(rawBody).digest("hex");

  try {
    return crypto.timingSafeEqual(
      Buffer.from(expected),
      Buffer.from(signatureHeader)
    );
  } catch {
    return false;
  }
}

/**
 * POST = Incoming messages from Instagram
 */
export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const signature = req.headers.get("x-hub-signature-256");

  if (!verifySignature(rawBody, signature)) {
    console.warn("Invalid webhook signature");
    return new NextResponse("Invalid signature", { status: 401 });
  }

  let body: any;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return new NextResponse("Invalid JSON", { status: 400 });
  }

  // Always respond 200 quickly so Meta doesn't retry
  // Process asynchronously (fire-and-forget style)
  processWebhook(body).catch((err) =>
    console.error("Error processing webhook:", err)
  );

  return new NextResponse("EVENT_RECEIVED", { status: 200 });
}

async function processWebhook(body: any) {
  // Instagram webhooks use object: "instagram"
  // (sometimes also "page" depending on setup)
  if (body.object !== "instagram" && body.object !== "page") {
    console.log("Ignoring non-instagram/page object:", body.object);
    return;
  }

  for (const entry of body.entry || []) {
    const messagingEvents = entry.messaging || [];

    for (const event of messagingEvents) {
      // Ignore echoes (messages we ourselves sent)
      if (event.message?.is_echo) {
        continue;
      }

      // Only handle text messages for now
      if (!event.message?.text) {
        // Could be attachment, reaction, read receipt, etc.
        console.log("Skipping non-text event");
        continue;
      }

      const senderId = event.sender?.id;
      const text = event.message.text.trim();

      if (!senderId || !text) continue;

      console.log(`Message from ${senderId}: ${text}`);

      // 1. Load previous history
      const history = getHistory(senderId);

      // 2. Generate AI reply with last ~10 messages as context
      const reply = await generateReply(history, text);

      // 3. Store both the user message and our reply
      addMessage(senderId, { role: "user", content: text });
      addMessage(senderId, { role: "assistant", content: reply });

      // 4. Send the reply back to Instagram
      const result = await sendInstagramMessage(senderId, reply);

      if (result.success) {
        console.log(`Replied to ${senderId}: ${reply.slice(0, 80)}...`);
      } else {
        console.error(`Failed to reply to ${senderId}:`, result.error);
      }
    }
  }
}
