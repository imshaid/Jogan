import type { Metadata, Viewport } from "next";
import { Geist_Mono, Inter, Noto_Sans_Bengali } from "next/font/google";
import { cookies } from "next/headers";

import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

import { LANG_COOKIE, SIDEBAR_COOKIE } from "@/lib/config";

import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const bengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-bengali" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });

export const metadata: Metadata = {
  title: { default: "Jogan · যোগান", template: "%s · Jogan" },
  description: "Agent liquidity copilot prototype for upay agents. All data is simulated.",
};

export const viewport: Viewport = { themeColor: "#ffffff" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // the language and the sidebar width are cookies, so the server renders them and nothing flashes
  const jar = await cookies();
  const lang = jar.get(LANG_COOKIE)?.value === "bn" ? "bn" : "en";
  const sidebar = jar.get(SIDEBAR_COOKIE)?.value === "rail" ? "rail" : "full";
  return (
    <html lang={lang} data-sidebar={sidebar} className={`${inter.variable} ${bengali.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <Providers lang={lang}>{children}</Providers>
      </body>
    </html>
  );
}
