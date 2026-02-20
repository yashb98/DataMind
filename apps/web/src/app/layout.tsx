import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataMind — AI-Native Analytics",
  description: "Enterprise AI analytics & digital labor platform",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-background text-foreground antialiased">{children}</body>
    </html>
  );
}
