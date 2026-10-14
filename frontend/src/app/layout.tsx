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
  title: "PolicyPilot — AI-Powered HR Policy Assistant",
  description:
    "Get accurate, region-aware answers to company policy questions. Powered by Retrieval-Augmented Generation with verifiable citations.",
  keywords: ["HR policy", "AI assistant", "RAG", "policy management", "employee experience"],
  openGraph: {
    title: "PolicyPilot — AI-Powered HR Policy Assistant",
    description:
      "Trusted answers grounded in your company's approved policy documents. Region-aware, citation-backed, and safe.",
    type: "website",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
