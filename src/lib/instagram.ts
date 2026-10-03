const GRAPH_API_VERSION = "v21.0";

export async function sendInstagramMessage(
  recipientId: string,
  text: string
): Promise<{ success: boolean; data?: unknown; error?: string }> {
  const token = process.env.PAGE_ACCESS_TOKEN;

  if (!token) {
    return { success: false, error: "PAGE_ACCESS_TOKEN is not set" };
  }

  const url = `https://graph.facebook.com/${GRAPH_API_VERSION}/me/messages?access_token=${token}`;

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        recipient: { id: recipientId },
        message: { text },
        messaging_type: "RESPONSE",
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      console.error("Instagram send error:", data);
      return {
        success: false,
        error: data?.error?.message || JSON.stringify(data),
      };
    }

    return { success: true, data };
  } catch (err) {
    console.error("Instagram send exception:", err);
    return {
      success: false,
      error: err instanceof Error ? err.message : "Unknown error",
    };
  }
}
