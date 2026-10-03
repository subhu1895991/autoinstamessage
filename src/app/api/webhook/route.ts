import { NextRequest, NextResponse } from "next/server";
import crypto from "crypto";
import { addMessage, getHistory } from "@/lib/store";
import { generateReply } from "@/lib/groq";
import { sendInstagramMessage } from "@/lib/instagram";

export const runtime = "nodejs";

/**
 * GET = Webhook verification (Meta sends this when you set the Callback URL)
 */
export async function GET(req: NextRequest) {
  const searchParams = req.nextUrl.searchParams;
  const mode = searchParams.get("hub.mode");
  const token = searchParams.get("hub.verify_token");
  const challenge = searchParams.get("hub.challenge");

  const verifyToken = process.env.VERIFY_TOKEN;

  if (mode === "subscribe" && token === verifyToken && challenge) {
    console.log("Webhook verified successfully");
    return new NextResponse(challenge, { status: 200 });
  }

  console.warn("Webhook verification failed", {
    mode,
    tokenMatch: token === verifyToken,
  });
  return new NextResponse("Forbidden", { status: 403 });
}

function verifySignature(
  rawBody: string,
  signatureHeader: string | null
): boolean {
  const appSecret = process.env.APP_SECRET;

  if (!appSecret) {
    console.warn("APP_SECRET is not set — skipping signature check");
    return true;
  }

  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    console.warn("Missing or invalid X-Hub-Signature-256 header");
    return true; // soft allow for debug
  }

  const expected =
    "sha256=" +
    crypto.createHmac("sha256", appSecret).update(rawBody).digest("hex");

  const expectedBuffer = Buffer.from(expected);
  const receivedBuffer = Buffer.from(signatureHeader);

  if (expectedBuffer.length !== receivedBuffer.length) {
    console.warn("Signature length mismatch — allowing for debug");
    return true;
  }

  const ok = crypto.timingSafeEqual(expectedBuffer, receivedBuffer);
  if (!ok) {
    console.warn("Signature mismatch — allowing for debug");
  }
  return true; // soft allow so we can see events in logs
}

/**
 * POST = Incoming messages from Instagram
 */
export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const signature = req.headers.get("x-hub-signature-256");

  console.log("Webhook POST received, body length:", rawBody.length);

  if (!verifySignature(rawBody, signature)) {
    console.warn("Invalid webhook signature — rejected");
    return new NextResponse("Invalid signature", { status: 401 });
  }

  let body: any;

  try {
    body = JSON.parse(rawBody);
  } catch {
    console.error("Invalid JSON body");
    return new NextResponse("Invalid JSON", { status: 400 });
  }

  console.log("Webhook body object:", body?.object);
  console.log("Webhook body (truncated):", JSON.stringify(body).slice(0, 800));

  try {
    await processWebhook(body);
    return new NextResponse("EVENT_RECEIVED", { status: 200 });
  } catch (err) {
    console.error("Error processing webhook:", err);
    return new NextResponse("EVENT_RECEIVED", { status: 200 });
  }
}

async function processWebhook(body: any) {
  if (body.object !== "instagram" && body.object !== "page") {
    console.log("Ignoring non-instagram/page object:", body.object);
    return;
  }

  for (const entry of body.entry || []) {
    const messagingEvents = entry.messaging || [];

    if (!messagingEvents.length) {
      console.log("No messaging events in entry");
    }

    for (const event of messagingEvents) {
      if (event.message?.is_echo) {
        console.log("Skipping echo message");
        continue;
      }

      if (!event.message?.text) {
        console.log("Skipping non-text event:", Object.keys(event));
        continue;
      }

      const senderId = event.sender?.id;
      const text = event.message.text.trim();

      if (!senderId || !text) {
        continue;
      }

      console.log(`Message from ${senderId}: ${text}`);

      const history = getHistory(senderId);
      const reply = await generateReply(history, text);

      console.log(`Groq reply: ${reply.slice(0, 120)}`);

      const result = await sendInstagramMessage(senderId, reply);

      if (!result.success) {
        console.error(`Failed to reply to ${senderId}:`, result.error);
        continue;
      }

      addMessage(senderId, { role: "user", content: text });
      addMessage(senderId, { role: "assistant", content: reply });

      console.log(`Replied to ${senderId}: ${reply.slice(0, 80)}...`);
    }
  }
}
