import type { Metadata, Viewport } from "next";
import { Inter, Noto_Sans_Bengali } from "next/font/google";
import { cookies } from "next/headers";

import "maplibre-gl/dist/maplibre-gl.css";
import "./globals.css";

import { LANG_COOKIE } from "@/lib/config";

import { Providers } from "./providers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const bengali = Noto_Sans_Bengali({ subsets: ["bengali"], variable: "--font-bengali" });

export const metadata: Metadata = {
  title: { default: "Jogan · যোগান", template: "%s · Jogan" },
  description: "Agent liquidity copilot prototype for upay agents. All data is simulated.",
};

export const viewport: Viewport = { themeColor: "#0c55a4" };

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // the language is a cookie, so the server renders the chosen language and nothing flashes
  const lang = (await cookies()).get(LANG_COOKIE)?.value === "bn" ? "bn" : "en";
  return (
    <html lang={lang} className={`${inter.variable} ${bengali.variable}`}>
      <body className="min-h-screen font-sans antialiased">
        <Providers lang={lang}>{children}</Providers>
      </body>
    </html>
  );
}
