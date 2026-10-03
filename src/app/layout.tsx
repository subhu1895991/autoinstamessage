import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Auto Insta Message",
  description: "AI auto-replies for Instagram DMs powered by Groq",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, padding: 0 }}>
        {children}
      </body>
    </html>
  );
}
