import Groq from "groq-sdk";
import type { ChatMessage } from "./store";

const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY,
});

const DEFAULT_SYSTEM = `You are a helpful, friendly Instagram assistant for this account.
Keep replies short, natural and conversational (1-3 sentences usually).
Do not mention that you are an AI unless asked.
If you are unsure, politely say so and offer to connect them with a human.`;

export async function generateReply(
  history: ChatMessage[],
  latestUserMessage: string
): Promise<string> {
  const systemPrompt =
    process.env.SYSTEM_PROMPT?.trim() || DEFAULT_SYSTEM;

  const messages: ChatMessage[] = [
    { role: "system", content: systemPrompt },
    ...history,
    { role: "user", content: latestUserMessage },
  ];

  const model =
    process.env.GROQ_MODEL?.trim() || "llama-3.3-70b-versatile";

  const completion = await groq.chat.completions.create({
    model,
    messages,
    temperature: 0.7,
    max_tokens: 300,
  });

  const reply =
    completion.choices[0]?.message?.content?.trim() ||
    "Sorry, I couldn't generate a reply right now.";

  return reply;
}
