"use client";

import type { ReactNode } from "react";

import type { Lang } from "@/lib/api";
import { LangProvider } from "@/lib/i18n";
import { SessionProvider } from "@/lib/session";

export function Providers({ lang, children }: { lang: Lang; children: ReactNode }) {
  return (
    <LangProvider initial={lang}>
      <SessionProvider>{children}</SessionProvider>
    </LangProvider>
  );
}
