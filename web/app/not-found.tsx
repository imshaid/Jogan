"use client";

import Link from "next/link";

import { Public } from "@/components/shell";
import { useLang } from "@/lib/i18n";

export default function NotFound() {
  const { t } = useLang();
  return (
    <Public>
      <div className="mx-auto max-w-md py-24 text-center">
        <p className="num text-sm font-semibold text-brand">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t.notFound.title}</h1>
        <Link href="/" className="mt-6 inline-block text-sm font-medium text-brand hover:underline">
          {t.notFound.back} →
        </Link>
      </div>
    </Public>
  );
}
