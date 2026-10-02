"use client";

import { BarChart3, ExternalLink, Info, LogOut, Map as MapIcon, Menu, ScrollText, ListChecks, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";

import { supabase, type Lang, type Role } from "@/lib/api";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, LOCAL_AUTH } from "@/lib/config";
import { useLang } from "@/lib/i18n";
import { useSession } from "@/lib/session";

import { Button, cx, ErrorNotice, Segmented, Skeleton } from "./ui";

const REPO = "https://github.com/imshaid/Jogan";

function Wordmark({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <Image src="/brand/jogan-mark.png" alt="" width={28} height={28} priority />
      <span className={cx("font-semibold tracking-tight text-ink", compact ? "text-[15px]" : "text-base")}>
        Jogan <span aria-hidden className="text-fg-3">·</span> <span lang="bn">যোগান</span>
      </span>
    </span>
  );
}

function SimulatedBadge() {
  const { t } = useLang();
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-ink"
      title={t.simulatedTitle}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-ink" />
      {t.simulated}
    </span>
  );
}

function useNav() {
  const { t } = useLang();
  return [
    {
      section: t.nav.sectionOps,
      items: [
        { href: "/", label: t.nav.network, Icon: MapIcon, keepDay: true },
        { href: "/queue", label: t.nav.queue, Icon: ListChecks, keepDay: true },
        { href: "/audit", label: t.nav.audit, Icon: ScrollText, keepDay: false },
      ],
    },
    {
      section: t.nav.sectionEvidence,
      items: [
        { href: "/impact", label: t.nav.impact, Icon: BarChart3, keepDay: false },
        { href: "/about", label: t.nav.about, Icon: Info, keepDay: false },
      ],
    },
  ];
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const nav = useNav();
  const pathname = usePathname();
  const params = useSearchParams();
  const day = params.get("day");
  return (
    <nav className="flex flex-col gap-5">
      {nav.map((group) => (
        <div key={group.section}>
          <div className="px-3 pb-1.5 text-[11px] font-semibold tracking-wide text-fg-3 uppercase">{group.section}</div>
          <ul className="flex flex-col gap-0.5">
            {group.items.map(({ href, label, Icon, keepDay }) => {
              const active = href === "/" ? pathname === "/" || pathname.startsWith("/agents") : pathname.startsWith(href);
              return (
                <li key={href}>
                  <Link
                    href={keepDay && day ? `${href}?day=${day}` : href}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cx(
                      "relative flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      active ? "bg-brand-tint text-brand" : "text-fg-2 hover:bg-page hover:text-fg",
                    )}
                  >
                    {active && (
                      <span aria-hidden className="absolute top-1.5 bottom-1.5 left-0 w-[3px] rounded-r bg-accent" />
                    )}
                    <Icon aria-hidden className="size-4 shrink-0" strokeWidth={2} />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function LangSwitch() {
  const { lang, setLang, t } = useLang();
  return (
    <Segmented<Lang>
      label={t.lang.label}
      value={lang}
      size="sm"
      onChange={setLang}
      options={[
        { value: "en", label: "EN" },
        { value: "bn", label: <span lang="bn">বাংলা</span> },
      ]}
    />
  );
}

function UserMenu() {
  const { t } = useLang();
  const { session, email, role, signOut } = useSession();
  if (!session) {
    return (
      <Link href="/" className="text-sm font-medium text-brand hover:underline">
        {t.signIn.submit}
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2.5">
      <div className="hidden text-right leading-tight sm:block">
        <div className="max-w-48 truncate text-[13px] text-fg">{email}</div>
        <div className="text-xs font-semibold text-brand">{role ? t.user.role[role] : role === null ? t.user.noRole : "…"}</div>
      </div>
      <Button variant="ghost" size="sm" onClick={signOut} aria-label={t.user.signOut} title={t.user.signOut}>
        <LogOut aria-hidden className="size-4" />
        <span className="sr-only sm:not-sr-only">{t.user.signOut}</span>
      </Button>
    </div>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useLang();
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center px-4">
        <Link href="/" onClick={onNavigate} className="rounded-md">
          <Wordmark compact />
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-4">
        <Suspense fallback={null}>
          <NavLinks onNavigate={onNavigate} />
        </Suspense>
      </div>
      <div className="space-y-2 border-t border-line px-4 py-3 text-xs text-fg-3">
        <div>{t.appTagline}</div>
        <a href={REPO} className="inline-flex items-center gap-1 hover:text-brand" target="_blank" rel="noreferrer">
          {t.about.source} <ExternalLink aria-hidden className="size-3" />
        </a>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <div className="min-h-screen">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-surface px-3 py-2 text-sm font-medium focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        {t.skipToContent}
      </a>
      <div aria-hidden className="fixed inset-x-0 top-0 z-40 h-[3px] bg-accent" />
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-line bg-surface pt-[3px] lg:block">
        <Sidebar />
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t.nav.menu}>
          <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-64 bg-surface pt-[3px] shadow-xl">
            <button
              className="absolute top-3.5 right-3 rounded p-1 text-fg-2 hover:bg-page"
              onClick={() => setOpen(false)}
              aria-label={t.nav.close}
            >
              <X className="size-5" />
            </button>
            <Sidebar key={pathname} onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
      <div className="pt-[3px] lg:pl-60">
        <header className="sticky top-[3px] z-20 flex h-14 items-center gap-3 border-b border-line bg-surface/95 px-4 backdrop-blur sm:px-6">
          <button
            className="-ml-1 rounded p-1.5 text-fg-2 hover:bg-page lg:hidden"
            onClick={() => setOpen(true)}
            aria-label={t.nav.menu}
          >
            <Menu className="size-5" />
          </button>
          <span className="lg:hidden">
            <Wordmark compact />
          </span>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden md:inline-flex">
              <SimulatedBadge />
            </span>
            <LangSwitch />
            <span aria-hidden className="hidden h-6 w-px bg-line sm:block" />
            <UserMenu />
          </div>
        </header>
        <div className="border-b border-line bg-accent-tint px-4 py-1.5 text-center text-xs font-medium text-ink md:hidden">
          {t.simulated}
        </div>
        <main id="main" className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
          {children}
        </main>
      </div>
    </div>
  );
}

function RoleButton({ role, disabled, onClick }: { role: Role; disabled?: boolean; onClick: () => void }) {
  const { t } = useLang();
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="group rounded-lg border border-line-strong px-3 py-2.5 text-left transition-colors hover:border-brand hover:bg-brand-tint disabled:opacity-60"
    >
      <div className="text-sm font-semibold text-brand">
        {role === "analyst" ? t.signIn.asAnalyst : t.signIn.asApprover}
      </div>
      <div className="mt-0.5 text-xs text-fg-2">
        {role === "analyst" ? t.signIn.asAnalystNote : t.signIn.asApproverNote}
      </div>
    </button>
  );
}

// A local run (`make run`) has no accounts: the in-memory API takes the role names as tokens.
function LocalSignIn() {
  const { t } = useLang();
  const { signInLocal } = useSession();
  return (
    <div className="mt-6">
      <div className="text-xs font-semibold tracking-wide text-fg-3 uppercase">{t.signIn.local}</div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {(["analyst", "approver"] as const).map((r) => (
          <RoleButton key={r} role={r} onClick={() => signInLocal(r)} />
        ))}
      </div>
      <p className="mt-2 text-xs text-fg-3">{t.signIn.localNote}</p>
    </div>
  );
}

function SignIn() {
  const { t } = useLang();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(e: string, p: string) {
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signInWithPassword({ email: e, password: p });
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div aria-hidden className="fixed inset-x-0 top-0 z-40 h-[3px] bg-accent" />
      <section className="hidden flex-col justify-between bg-brand px-12 py-10 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="rounded-lg bg-white p-1.5">
            <Image src="/brand/jogan-mark.png" alt="" width={28} height={28} priority />
          </span>
          <span className="text-lg font-semibold tracking-tight">
            Jogan · <span lang="bn">যোগান</span>
          </span>
        </div>
        <div className="max-w-md">
          <p className="text-[26px] leading-snug font-semibold tracking-tight">{t.appTagline}</p>
          <p className="mt-3 text-[15px] leading-relaxed text-white/85">{t.signIn.lead}</p>
          <ul className="mt-8 space-y-4">
            {t.signIn.points.map((p, i) => (
              <li key={p} className="flex gap-3 text-sm leading-relaxed text-white/90">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-ink">
                  {i + 1}
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/70">{t.signIn.footer}</p>
      </section>

      <section className="flex flex-col bg-surface">
        <div className="flex items-center justify-between px-6 pt-6 sm:px-10">
          <span className="lg:hidden">
            <Wordmark />
          </span>
          <div className="ml-auto flex items-center gap-3">
            <SimulatedBadge />
            <LangSwitch />
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
          <div className="w-full max-w-sm">
            <h1 className="text-2xl font-semibold tracking-tight">{t.signIn.title}</h1>
            <p className="mt-2 text-sm text-fg-2 lg:hidden">{t.signIn.lead}</p>

            {LOCAL_AUTH ? (
              <LocalSignIn />
            ) : (
              <>
                {DEMO_PASSWORD && (
                  <div className="mt-6">
                    <div className="text-xs font-semibold tracking-wide text-fg-3 uppercase">{t.signIn.demo}</div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      {DEMO_ACCOUNTS.map((a) => (
                        <RoleButton
                          key={a.email}
                          role={a.role}
                          disabled={busy}
                          onClick={() => signIn(a.email, DEMO_PASSWORD)}
                        />
                      ))}
                    </div>
                    <p className="mt-2 text-xs text-fg-3">{t.signIn.demoNote}</p>
                    <div className="my-6 flex items-center gap-3 text-xs text-fg-3">
                      <span className="h-px flex-1 bg-line" />
                      {t.signIn.or}
                      <span className="h-px flex-1 bg-line" />
                    </div>
                  </div>
                )}

                <form
                  className="space-y-4"
                  onSubmit={(ev) => {
                    ev.preventDefault();
                    signIn(email, password);
                  }}
                >
                  <label className="block">
                    <span className="text-sm font-medium">{t.signIn.email}</span>
                    <input
                      className="mt-1.5 h-10 w-full rounded-md border border-line-strong px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
                      type="email"
                      autoComplete="username"
                      value={email}
                      onChange={(ev) => setEmail(ev.target.value)}
                      required
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium">{t.signIn.password}</span>
                    <input
                      className="mt-1.5 h-10 w-full rounded-md border border-line-strong px-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20"
                      type="password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(ev) => setPassword(ev.target.value)}
                      required
                    />
                  </label>
                  <Button variant="primary" className="h-10 w-full" disabled={busy}>
                    {busy ? t.signIn.busy : t.signIn.submit}
                  </Button>
                </form>
                {error && (
                  <p role="alert" className="mt-4 text-sm text-danger-text">
                    {error}
                  </p>
                )}
              </>
            )}
            <p className="mt-8 flex gap-4 border-t border-line pt-4 text-sm">
              <Link href="/impact" className="font-medium text-brand hover:underline">
                {t.nav.impact} →
              </Link>
              <Link href="/about" className="font-medium text-brand hover:underline">
                {t.nav.about} →
              </Link>
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

// Signed-in pages: the sign-in screen when signed out, a notice when the account has no role.
export function Staff({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const { ready, session, role, roleError } = useSession();
  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-6 w-40" />
      </div>
    );
  }
  if (!session) return <SignIn />;
  return (
    <AppShell>
      {roleError ? (
        <ErrorNotice error={roleError} />
      ) : role === null ? (
        <p className="rounded-md border border-line bg-surface px-4 py-3 text-sm">{t.common.noRole}</p>
      ) : role === undefined ? (
        <div className="space-y-4">
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      ) : (
        children
      )}
    </AppShell>
  );
}

// Public pages (impact, about) use the same shell without asking for a sign-in.
export function Public({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
