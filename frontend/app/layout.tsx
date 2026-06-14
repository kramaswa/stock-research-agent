import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  title: "Stock Research Agent",
  description: "AI agents to help you find, analyze, and hold stocks with conviction.",
  openGraph: {
    title: "Stock Research Agent",
    description: "AI agents to help you find, analyze, and hold stocks with conviction.",
    url: "https://stockresearch-ai.vercel.app",
    siteName: "Stock Research Agent",
    images: [{ url: "https://stockresearch-ai.vercel.app/opengraph-image", width: 1200, height: 630 }],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Stock Research Agent",
    description: "AI agents to help you find, analyze, and hold stocks with conviction.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
