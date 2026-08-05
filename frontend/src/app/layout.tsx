import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AppShell } from "@/components/shell/AppShell";
import { getHealth } from "@/lib/api";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Hedge Fund Platform",
  description: "Quantitative trading and portfolio operations platform",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let apiStatus: "connected" | "offline" = "offline";

  try {
    const health = await getHealth();
    if (health.status === "ok") {
      apiStatus = "connected";
    }
  } catch {
    apiStatus = "offline";
  }

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <AppShell apiStatus={apiStatus}>{children}</AppShell>
      </body>
    </html>
  );
}
