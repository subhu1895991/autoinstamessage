/**
 * Simple in-memory conversation store.
 * Keeps the last N messages per sender (IGSID).
 *
 * NOTE: On Vercel serverless this is per-instance and can reset on cold starts.
 * For production reliability, switch to Vercel KV / Upstash Redis later.
 */

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

const MAX_MESSAGES = 10; // last 10 messages (user + assistant)

// Global so it survives hot reloads in dev and shares across invocations in the same instance
const globalForStore = globalThis as unknown as {
  convoStore?: Map<string, ChatMessage[]>;
};

const store = globalForStore.convoStore ?? new Map<string, ChatMessage[]>();
if (!globalForStore.convoStore) {
  globalForStore.convoStore = store;
}

export function getHistory(senderId: string): ChatMessage[] {
  return store.get(senderId) ?? [];
}

export function addMessage(senderId: string, message: ChatMessage) {
  const history = getHistory(senderId);
  history.push(message);

  // Keep only the most recent MAX_MESSAGES
  while (history.length > MAX_MESSAGES) {
    history.shift();
  }

  store.set(senderId, history);
}

export function clearHistory(senderId: string) {
  store.delete(senderId);
}
