"use client";

import Link from "next/link";

import { Public } from "@/components/shell";
import { useLang } from "@/lib/i18n";

export default function NotFound() {
  const { t } = useLang();
  return (
    <Public>
      <div className="mx-auto max-w-md py-24 text-center">
        <p className="num text-5xl font-medium tracking-tight text-fg-3">404</p>
        <h1 className="mt-3 text-2xl font-semibold tracking-tight">{t.notFound.title}</h1>
        <Link
          href="/"
          className="mt-6 inline-flex h-9 items-center rounded-lg bg-ink px-4 text-sm font-medium text-white hover:bg-ink/85"
        >
          {t.notFound.back} →
        </Link>
      </div>
    </Public>
  );
}
