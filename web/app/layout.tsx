import type { Metadata } from "next";
import { Inter, Noto_Sans_Bengali } from "next/font/google";
import Image from "next/image";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const bengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-bengali" });

export const metadata: Metadata = {
  title: "Jogan · যোগান",
  description: "Agent liquidity copilot prototype. All data is simulated.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${bengali.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <header className="border-b border-line bg-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
            <span className="flex items-center gap-2 text-lg font-bold text-brand">
              <Image src="/brand/jogan-mark.png" alt="" width={32} height={32} loading="eager" />
              <span>
                Jogan <span aria-hidden>·</span> <span lang="bn">যোগান</span>
              </span>
            </span>
            <span className="text-sm text-muted">Agent liquidity copilot</span>
            <span
              className="ml-auto rounded-full bg-accent px-3 py-1 text-xs font-semibold text-ink"
              title="Every agent, transaction and runner here comes from a simulator. No real customer data."
            >
              Simulated data · <span lang="bn">সিমুলেটেড ডেটা</span>
            </span>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
