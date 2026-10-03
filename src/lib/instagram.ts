const GRAPH_API_VERSION = "v21.0";

/**
 * Send a text reply on Instagram.
 * Supports both:
 * - Instagram Login flow  → graph.instagram.com + INSTAGRAM_ACCESS_TOKEN
 * - Facebook Login / Page flow → graph.facebook.com + PAGE_ACCESS_TOKEN
 */
export async function sendInstagramMessage(
  recipientId: string,
  text: string
): Promise<{ success: boolean; data?: unknown; error?: string }> {
  const token =
    process.env.INSTAGRAM_ACCESS_TOKEN ||
    process.env.PAGE_ACCESS_TOKEN;

  if (!token) {
    return {
      success: false,
      error: "Neither INSTAGRAM_ACCESS_TOKEN nor PAGE_ACCESS_TOKEN is set",
    };
  }

  // Prefer Instagram host when using Instagram Login token
  const useInstagramHost = Boolean(process.env.INSTAGRAM_ACCESS_TOKEN);
  const host = useInstagramHost
    ? "https://graph.instagram.com"
    : "https://graph.facebook.com";

  const url = `${host}/${GRAPH_API_VERSION}/me/messages`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        recipient: { id: recipientId },
        message: { text },
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      console.error("Instagram send error:", JSON.stringify(data));
      return {
        success: false,
        error: data?.error?.message || JSON.stringify(data),
      };
    }

    console.log("Instagram send success:", JSON.stringify(data));
    return { success: true, data };
  } catch (err) {
    console.error("Instagram send exception:", err);
    return {
      success: false,
      error: err instanceof Error ? err.message : "Unknown error",
    };
  }
}
