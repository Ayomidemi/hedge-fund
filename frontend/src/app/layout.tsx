import type { Metadata } from "next";
import { Source_Sans_3, Libre_Baskerville } from "next/font/google";
import { ToastProvider } from "@/components/ui/ToastProvider";
import "./globals.css";

const sourceSans = Source_Sans_3({
  variable: "--font-source-sans",
  display: "swap",
  subsets: ["latin"],
});

const baskerville = Libre_Baskerville({
  variable: "--font-baskerville",
  weight: ["400", "700"],
  display: "swap",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Pease Capital",
  description: "Technology-driven hedge fund operating system",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${sourceSans.variable} ${baskerville.variable} h-full antialiased`}
    >
      <body className="min-h-full font-sans">
        <ToastProvider position="top-right">{children}</ToastProvider>
      </body>
    </html>
  );
}
