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

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "Stock Research Agent",
  "url": "https://stockresearch-ai.vercel.app",
  "description": "A multi-agent AI system that helps individual investors find stocks, research them with real data, and know when to hold or sell.",
  "applicationCategory": "FinanceApplication",
  "operatingSystem": "Web",
  "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
  "featureList": [
    "AI-powered stock discovery from natural language queries",
    "Multi-agent research pipeline with real-time market data",
    "Hold Check thesis validation with actionable buy/sell signals"
  ],
  "author": { "@type": "Person", "name": "Kishore Ramaswa" }
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
      <body className="min-h-full flex flex-col">
        {children}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </body>
    </html>
  );
}
