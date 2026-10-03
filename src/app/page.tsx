export default function Home() {
  return (
    <main
      style={{
        maxWidth: 640,
        margin: "40px auto",
        padding: "0 20px",
        lineHeight: 1.6,
      }}
    >
      <h1>Auto Insta Message</h1>
      <p>
        Instagram DM auto-replier using <strong>Groq</strong> + conversation
        history (last 10 messages).
      </p>
      <p>
        Webhook endpoint: <code>/api/webhook</code>
      </p>
      <p style={{ color: "#666", fontSize: 14 }}>
        Deploy to Vercel, set the environment variables, then configure the
        webhook in the Meta App Dashboard.
      </p>
    </main>
  );
}
