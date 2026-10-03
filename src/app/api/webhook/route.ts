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

  console.warn("Webhook verification failed");
  return new NextResponse("Forbidden", { status: 403 });
}

function verifySignature(
  rawBody: string,
  signatureHeader: string | null
): boolean {
  const appSecret = process.env.APP_SECRET;

  if (!appSecret) {
    console.error("APP_SECRET is not set");
    return false;
  }

  if (!signatureHeader || !signatureHeader.startsWith("sha256=")) {
    return false;
  }

  const expected =
    "sha256=" +
    crypto.createHmac("sha256", appSecret).update(rawBody).digest("hex");

  const expectedBuffer = Buffer.from(expected);
  const receivedBuffer = Buffer.from(signatureHeader);

  if (expectedBuffer.length !== receivedBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(expectedBuffer, receivedBuffer);
}

/**
 * POST = Incoming messages from Instagram
 *
 * Important: await processing before returning. On Vercel, a fire-and-forget
 * promise can be terminated when the serverless invocation finishes.
 */
export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const signature = req.headers.get("x-hub-signature-256");

  if (!verifySignature(rawBody, signature)) {
    console.warn("Invalid webhook signature");
    return new NextResponse("Invalid signature", { status: 401 });
  }

  let body: unknown;

  try {
    body = JSON.parse(rawBody);
  } catch {
    return new NextResponse("Invalid JSON", { status: 400 });
  }

  try {
    await processWebhook(body);
    return new NextResponse("EVENT_RECEIVED", { status: 200 });
  } catch (err) {
    console.error("Error processing webhook:", err);
    return new NextResponse("Webhook processing failed", { status: 500 });
  }
}

async function processWebhook(body: any) {
  if (body.object !== "instagram" && body.object !== "page") {
    console.log("Ignoring non-instagram/page object:", body.object);
    return;
  }

  for (const entry of body.entry || []) {
    const messagingEvents = entry.messaging || [];

    for (const event of messagingEvents) {
      if (event.message?.is_echo) {
        continue;
      }

      if (!event.message?.text) {
        console.log("Skipping non-text event");
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

      const result = await sendInstagramMessage(senderId, reply);

      if (!result.success) {
        console.error(`Failed to reply to ${senderId}:`, result.error);
        throw new Error(result.error || "Instagram message send failed");
      }

      addMessage(senderId, { role: "user", content: text });
      addMessage(senderId, { role: "assistant", content: reply });

      console.log(
        `Replied to ${senderId}: ${reply.slice(0, 80)}...`
      );
    }
  }
}
