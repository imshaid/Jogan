"use client";

import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Bike,
  ChevronRight,
  CodeXml,
  Eye,
  Info,
  Languages,
  ListChecks,
  LogOut,
  Map as MapIcon,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Search,
  ShieldCheck,
} from "lucide-react";
import { motion } from "motion/react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";

import { supabase, type Lang, type Recommendation, type Role } from "@/lib/api";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, LOCAL_AUTH, SIDEBAR_COOKIE } from "@/lib/config";
import { usePeek } from "@/lib/data";
import { keys, useMeta } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";
import { useSession } from "@/lib/session";

import { CommandDialog, type Command } from "./command";
import { ActivityMenu, ActivitySync, LiveStatus, Toaster, TopProgress } from "./live";
import { Button, cx, ErrorNotice, IconButton, Segmented, Skeleton } from "./ui";

const REPO = "https://github.com/imshaid/Jogan";

function Mark({ size = 32 }: { size?: number }) {
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-lg bg-accent-tint ring-1 ring-accent/60"
      style={{ width: size, height: size }}
    >
      <Image src="/brand/jogan-mark.png" alt="" width={Math.round(size * 0.7)} height={Math.round(size * 0.7)} priority />
    </span>
  );
}

function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cx("font-semibold tracking-tight text-ink", className)}>
      Jogan <span aria-hidden className="text-fg-3">·</span> <span lang="bn">যোগান</span>
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

// The sidebar width lives on <html data-sidebar>, set by the server from a cookie.
function subscribeRail(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-sidebar"] });
  return () => mo.disconnect();
}
const isRail = () => document.documentElement.dataset.sidebar === "rail";

function useRail(): [boolean, () => void] {
  const rail = useSyncExternalStore(subscribeRail, isRail, () => false);
  const toggle = useCallback(() => {
    const next = isRail() ? "full" : "rail";
    document.documentElement.dataset.sidebar = next;
    document.cookie = `${SIDEBAR_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
  }, []);
  return [rail, toggle];
}

type NavItem = { href: string; label: string; Icon: typeof MapIcon; keepDay: boolean; section: string };

function useNav() {
  const { t } = useLang();
  return useMemo(() => {
    const ops = t.nav.sectionOps;
    const ev = t.nav.sectionEvidence;
    const items: NavItem[] = [
      { href: "/", label: t.nav.network, Icon: MapIcon, keepDay: true, section: ops },
      { href: "/queue", label: t.nav.queue, Icon: ListChecks, keepDay: true, section: ops },
      { href: "/runner", label: t.nav.runner, Icon: Bike, keepDay: true, section: ops },
      { href: "/audit", label: t.nav.audit, Icon: ScrollText, keepDay: false, section: ops },
      { href: "/impact", label: t.nav.impact, Icon: BarChart3, keepDay: false, section: ev },
      { href: "/about", label: t.nav.about, Icon: Info, keepDay: false, section: ev },
    ];
    return items;
  }, [t]);
}

function isActive(href: string, pathname: string) {
  return href === "/" ? pathname === "/" || pathname.startsWith("/agents") : pathname.startsWith(href);
}

function useHref() {
  const params = useSearchParams();
  const day = params.get("day");
  return (item: NavItem) => (item.keepDay && day ? `${item.href}?day=${day}` : item.href);
}

// Pending visits for the day in view, only if a page has already loaded that day's plan.
function usePending() {
  const params = useSearchParams();
  const meta = useMeta();
  const day = params.get("day") ?? meta.data?.plan_dates[0] ?? null;
  const plan = usePeek<{ items: Recommendation[] }>(day && keys.plan(day));
  return plan?.items.filter((r) => r.status === "pending").length;
}

function NavLinks() {
  const { t, f } = useLang();
  const nav = useNav();
  const pathname = usePathname();
  const href = useHref();
  const pending = usePending();
  const sections = [...new Set(nav.map((n) => n.section))];
  return (
    <nav aria-label={t.nav.primary} className="flex flex-col gap-5">
      {sections.map((section, k) => (
        <div key={section}>
          <div className="eyebrow px-2.5 pb-1.5 text-fg-3 rail:sr-only">{section}</div>
          {k > 0 && <div aria-hidden className="mx-auto mb-3 hidden h-px w-6 bg-line-strong rail:block" />}
          <ul className="flex flex-col gap-0.5">
            {nav
              .filter((n) => n.section === section)
              .map((item) => {
                const active = isActive(item.href, pathname);
                const badge = item.href === "/queue" && pending ? pending : undefined;
                return (
                  <li key={item.href}>
                    <Link
                      href={href(item)}
                      aria-current={active ? "page" : undefined}
                      title={item.label}
                      className={cx(
                        "relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors rail:justify-center rail:px-0",
                        active ? "font-medium text-fg" : "text-fg-2 hover:bg-sunken/70 hover:text-fg",
                      )}
                    >
                      {active && (
                        <motion.span
                          layoutId="nav-active"
                          aria-hidden
                          className="absolute inset-0 rounded-lg border border-line bg-surface shadow-xs"
                          transition={{ type: "spring", bounce: 0.15, duration: 0.45 }}
                        >
                          <span className="absolute top-2 bottom-2 -left-3 w-0.75 rounded-r-full bg-accent rail:hidden" />
                        </motion.span>
                      )}
                      <item.Icon
                        aria-hidden
                        className={cx("relative size-4.5 shrink-0", active ? "text-brand" : "text-fg-3")}
                        strokeWidth={1.8}
                      />
                      <span className="relative min-w-0 flex-1 truncate rail:sr-only">{item.label}</span>
                      {badge !== undefined && (
                        <span className="num relative rounded-md bg-accent px-1.5 text-[11px] leading-5 font-semibold text-ink rail:hidden">
                          {f.num(badge)}
                          <span className="sr-only"> {t.queue.summary.pending}</span>
                        </span>
                      )}
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

function Sidebar({ onCommand }: { onCommand: () => void }) {
  const { t } = useLang();
  return (
    <div className="flex h-full flex-col">
      <div className="px-3 pt-3">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-xl border border-line bg-surface p-2 shadow-xs transition-colors hover:border-line-strong rail:justify-center rail:border-transparent rail:bg-transparent rail:p-0.5 rail:shadow-none"
        >
          <Mark />
          <span className="min-w-0 leading-tight rail:sr-only">
            <span className="block truncate text-[11px] text-fg-3">{t.appTagline}</span>
            <Wordmark className="block truncate text-sm" />
          </span>
        </Link>
        <button
          type="button"
          onClick={onCommand}
          title={t.cmd.label}
          className="mt-3 flex h-9 w-full items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-[13px] text-fg-3 shadow-xs transition-colors hover:border-line-strong hover:text-fg-2 rail:justify-center rail:px-0"
        >
          <Search aria-hidden className="size-4 shrink-0" />
          <span className="min-w-0 flex-1 truncate text-left rail:sr-only">{t.cmd.trigger}</span>
          <kbd aria-hidden className="mono rounded border border-line bg-tray px-1.5 text-[11px] leading-4 text-fg-3 rail:hidden">
            /
          </kbd>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-5">
        <Suspense fallback={null}>
          <NavLinks />
        </Suspense>
      </div>
      <div className="p-3">
        <div className="rounded-xl border border-line bg-surface p-3 shadow-xs rail:hidden">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
            <span aria-hidden className="size-2 rounded-full bg-accent ring-[3px] ring-accent/30" />
            {t.simulated}
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-fg-2">{t.simulatedTitle}</p>
          <a
            href={REPO}
            target="_blank"
            rel="noreferrer"
            className="mt-2.5 inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
          >
            {t.about.source} <ArrowUpRight aria-hidden className="size-3.5" />
          </a>
        </div>
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          title={t.about.source}
          aria-label={t.about.source}
          className="mx-auto hidden size-9 items-center justify-center rounded-lg text-fg-3 hover:bg-sunken hover:text-fg rail:flex"
        >
          <CodeXml aria-hidden className="size-4.5" />
        </a>
      </div>
    </div>
  );
}

function Breadcrumb() {
  const { t } = useLang();
  const nav = useNav();
  const pathname = usePathname();
  const href = useHref();
  const item = nav.find((n) => isActive(n.href, pathname));
  if (!item) return null;
  const agent = pathname.startsWith("/agents/") ? decodeURIComponent(pathname.split("/")[2] ?? "") : null;
  return (
    <nav aria-label={t.nav.breadcrumb} className="hidden min-w-0 items-center gap-1.5 text-sm lg:flex">
      <span className="text-fg-3">{item.section}</span>
      <ChevronRight aria-hidden className="size-3.5 shrink-0 text-fg-3" />
      {agent ? (
        <>
          <Link href={href(item)} className="text-fg-2 hover:text-fg">
            {item.label}
          </Link>
          <ChevronRight aria-hidden className="size-3.5 shrink-0 text-fg-3" />
          <span aria-current="page" className="mono truncate font-medium text-fg">
            {agent}
          </span>
        </>
      ) : (
        <span aria-current="page" className="truncate font-medium text-fg">
          {item.label}
        </span>
      )}
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

function initials(email: string | null | undefined) {
  const local = (email ?? "").split("@")[0];
  const parts = local.split(/[._-]/).filter(Boolean);
  return (parts[parts.length - 1] ?? "?").slice(0, 2).toUpperCase();
}

function UserMenu() {
  const { t } = useLang();
  const { session, email, role, signOut } = useSession();
  if (!session) {
    return (
      <Link
        href="/"
        className="inline-flex h-8 items-center rounded-lg bg-brand px-3 text-[13px] font-medium text-white hover:bg-brand-strong"
      >
        {t.signIn.submit}
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="hidden size-8 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-white sm:flex"
      >
        {initials(email)}
      </span>
      <div className="hidden leading-tight sm:block">
        <div className="max-w-44 truncate text-[13px] font-medium text-fg">{email}</div>
        <div className="text-xs text-fg-3">{role ? t.user.role[role] : role === null ? t.user.noRole : "…"}</div>
      </div>
      <IconButton label={t.user.signOut} onClick={signOut}>
        <LogOut aria-hidden className="size-4" />
      </IconButton>
    </div>
  );
}

function MobileNav() {
  const { t } = useLang();
  const nav = useNav();
  const pathname = usePathname();
  const href = useHref();
  return (
    <nav
      aria-label={t.nav.primary}
      className="pointer-events-none fixed inset-x-0 bottom-0 z-30 px-3 pb-[max(12px,env(safe-area-inset-bottom))] lg:hidden"
    >
      <ul className="pointer-events-auto mx-auto flex max-w-md items-center gap-1 rounded-full border border-line bg-surface/90 p-1.5 shadow-pop backdrop-blur-md">
        {nav.map((item) => {
          const active = isActive(item.href, pathname);
          return (
            <li key={item.href} className={cx("min-w-0 transition-[flex-grow] duration-300", active ? "flex-[2.4]" : "flex-1")}>
              <Link
                href={href(item)}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "relative flex h-11 items-center justify-center gap-1.5 rounded-full px-3 text-[13px] font-medium transition-colors",
                  active ? "text-white" : "text-fg-2 hover:bg-sunken hover:text-fg",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="tab-active"
                    aria-hidden
                    className="absolute inset-0 rounded-full bg-ink"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.45 }}
                  />
                )}
                <item.Icon aria-hidden className="relative size-5 shrink-0" strokeWidth={1.8} />
                <span className={active ? "relative truncate" : "sr-only"}>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function useCommands(toggleRail: () => void, rail: boolean) {
  const { t, lang, setLang } = useLang();
  const nav = useNav();
  const router = useRouter();
  const href = useHref();
  const pages: Command[] = nav.map((n) => ({
    id: `page:${n.href}`,
    label: n.label,
    hint: n.section,
    Icon: n.Icon,
    run: () => router.push(href(n)),
  }));
  const actions: Command[] = [
    { id: "lang", label: t.cmd.switchLang, Icon: Languages, run: () => setLang(lang === "en" ? "bn" : "en") },
    {
      id: "rail",
      label: rail ? t.nav.expand : t.nav.collapse,
      Icon: rail ? PanelLeftOpen : PanelLeftClose,
      run: toggleRail,
    },
  ];
  return { pages, actions };
}

function CommandLayer({ open, setOpen, rail, toggleRail }: { open: boolean; setOpen: (o: boolean) => void; rail: boolean; toggleRail: () => void }) {
  const { pages, actions } = useCommands(toggleRail, rail);
  return open ? <CommandDialog pages={pages} actions={actions} onClose={() => setOpen(false)} /> : null;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useLang();
  const { session, role } = useSession();
  const staff = !!session && !!role;
  const [rail, toggleRail] = useRail();
  const [command, setCommand] = useState(false);
  const pathname = usePathname();

  // Ctrl/⌘ K anywhere, or "/" outside a text field, opens the command menu
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCommand((o) => !o);
      } else if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        setCommand(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen bg-page">
      <a
        href="#main"
        className="sr-only z-50 rounded-lg bg-surface px-3 py-2 text-sm font-medium shadow-pop focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        {t.skipToContent}
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-side transition-[width] duration-200 lg:block rail:w-17">
        <Sidebar onCommand={() => setCommand(true)} />
      </aside>
      <div className="transition-[padding] duration-200 lg:pl-64 rail:lg:pl-17">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-line bg-page/85 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <Link href="/" className="flex min-w-0 items-center gap-2 lg:hidden">
            <Mark size={28} />
            <Wordmark className="hidden truncate text-[15px] whitespace-nowrap min-[400px]:inline" />
          </Link>
          <span className="-ml-2 hidden lg:block">
            <IconButton
              label={rail ? t.nav.expand : t.nav.collapse}
              onClick={toggleRail}
              className="border-transparent bg-transparent shadow-none"
            >
              {rail ? <PanelLeftOpen aria-hidden className="size-4.5" /> : <PanelLeftClose aria-hidden className="size-4.5" />}
            </IconButton>
          </span>
          <span aria-hidden className="hidden h-5 w-px bg-line lg:block" />
          <Suspense fallback={null}>
            <Breadcrumb />
          </Suspense>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            <span className="hidden sm:inline-flex">
              <LiveStatus />
            </span>
            <span className="sm:hidden">
              <LiveStatus compact />
            </span>
            <span className="lg:hidden">
              <IconButton label={t.cmd.label} onClick={() => setCommand(true)}>
                <Search aria-hidden className="size-4" />
              </IconButton>
            </span>
            <span className="hidden md:inline-flex">
              <SimulatedBadge />
            </span>
            {staff && <ActivityMenu />}
            <LangSwitch />
            <span aria-hidden className="hidden h-6 w-px bg-line sm:block" />
            <UserMenu />
          </div>
        </header>
        <div className="border-b border-accent/50 bg-accent-tint px-4 py-1.5 text-center text-xs font-medium text-ink md:hidden">
          {t.simulated}
        </div>
        <main id="main" className="mx-auto max-w-360 px-4 pt-6 pb-28 sm:px-6 lg:px-8 lg:pt-8 lg:pb-12">
          <div key={pathname} className="anim-page">
            {children}
          </div>
        </main>
      </div>
      <Suspense fallback={null}>
        <MobileNav />
        <CommandLayer open={command} setOpen={setCommand} rail={rail} toggleRail={toggleRail} />
        <TopProgress />
      </Suspense>
      <Toaster />
      {staff && <ActivitySync />}
    </div>
  );
}

function RoleButton({ role, disabled, onClick }: { role: Role; disabled?: boolean; onClick: () => void }) {
  const { t } = useLang();
  const Icon = role === "analyst" ? Eye : ShieldCheck;
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="group flex items-center gap-3 rounded-xl border border-line bg-surface p-3 text-left shadow-xs transition-colors hover:border-brand/50 hover:bg-brand-tint/50 disabled:opacity-60"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-fg">
          {role === "analyst" ? t.signIn.asAnalyst : t.signIn.asApprover}
        </span>
        <span className="mt-0.5 block text-xs text-fg-2">
          {role === "analyst" ? t.signIn.asAnalystNote : t.signIn.asApproverNote}
        </span>
      </span>
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-line bg-tray text-fg-2 transition-colors group-hover:border-brand/40 group-hover:text-brand">
        <Icon aria-hidden className="size-4" />
      </span>
    </button>
  );
}

// A local run (`make run`) has no accounts: the in-memory API takes the role names as tokens.
function LocalSignIn() {
  const { t } = useLang();
  const { signInLocal } = useSession();
  return (
    <div className="mt-7">
      <div className="eyebrow text-fg-3">{t.signIn.local}</div>
      <div className="mt-2.5 grid grid-cols-1 gap-2">
        {(["analyst", "approver"] as const).map((r) => (
          <RoleButton key={r} role={r} onClick={() => signInLocal(r)} />
        ))}
      </div>
      <p className="mt-2.5 text-xs leading-relaxed text-fg-3">{t.signIn.localNote}</p>
    </div>
  );
}

// Decorative block pattern for the sign-in panel (not data).
const BLOCKS = [2, 3, 2, 4, 3, 5, 3, 4, 6, 5, 7, 6, 8, 7, 9];

function BlockArt() {
  return (
    <div aria-hidden className="flex items-end gap-1.25">
      {BLOCKS.map((h, i) => (
        <div key={i} className="anim-grow-y flex flex-col-reverse gap-1.25" style={{ ["--i" as string]: i * 2 }}>
          {Array.from({ length: 10 }, (_, k) => (
            <span
              key={k}
              className={cx(
                "size-3 rounded-xs",
                k >= h ? "bg-white/6" : i === BLOCKS.length - 1 ? "bg-accent" : "bg-white/75",
              )}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

const INPUT =
  "mt-1.5 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm shadow-xs outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";

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
    <div className="grid grid-cols-1 min-h-screen bg-tray lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:gap-2 lg:p-2">
      <section className="relative hidden flex-col justify-between overflow-hidden rounded-2xl bg-ink px-12 py-10 text-white lg:flex">
        <div className="flex items-center gap-3">
          <span className="rounded-lg bg-white p-1">
            <Mark size={30} />
          </span>
          <span className="text-lg font-semibold tracking-tight">
            Jogan · <span lang="bn">যোগান</span>
          </span>
        </div>
        <div className="max-w-md">
          <BlockArt />
          <p className="mt-10 text-[28px] leading-tight font-semibold tracking-[-0.02em]">{t.appTagline}</p>
          <p className="mt-3 text-[15px] leading-relaxed text-white/75">{t.signIn.lead}</p>
          <ul className="mt-8 space-y-3.5">
            {t.signIn.points.map((p, i) => (
              <li key={p} className="flex gap-3 text-sm leading-relaxed text-white/90">
                <span className="mono mt-px flex h-5 min-w-7 shrink-0 items-center justify-center rounded-md bg-white/10 text-[11px] font-medium text-accent">
                  0{i + 1}
                </span>
                {p}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/60">{t.signIn.footer}</p>
      </section>

      <section className="flex flex-col bg-surface lg:rounded-2xl lg:border lg:border-line">
        <div className="flex items-center justify-between gap-3 px-6 pt-6 sm:px-10">
          <span className="flex items-center gap-2 lg:invisible">
            <Mark size={28} />
            <Wordmark className="text-base" />
          </span>
          <div className="flex items-center gap-3">
            <SimulatedBadge />
            <LangSwitch />
          </div>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
          <div className="w-full max-w-sm">
            <h1 className="text-[26px] leading-8 font-semibold tracking-[-0.02em]">{t.signIn.title}</h1>
            <p className="mt-2 text-sm leading-relaxed text-fg-2 lg:hidden">{t.signIn.lead}</p>

            {LOCAL_AUTH ? (
              <LocalSignIn />
            ) : (
              <>
                {DEMO_PASSWORD && (
                  <div className="mt-7">
                    <div className="eyebrow text-fg-3">{t.signIn.demo}</div>
                    <div className="mt-2.5 grid grid-cols-1 gap-2">
                      {DEMO_ACCOUNTS.map((a) => (
                        <RoleButton
                          key={a.email}
                          role={a.role}
                          disabled={busy}
                          onClick={() => signIn(a.email, DEMO_PASSWORD)}
                        />
                      ))}
                    </div>
                    <p className="mt-2.5 text-xs leading-relaxed text-fg-3">{t.signIn.demoNote}</p>
                    <div className="my-6 flex items-center gap-3 text-xs text-fg-3">
                      <span className="h-px flex-1 bg-line" />
                      {t.signIn.or}
                      <span className="h-px flex-1 bg-line" />
                    </div>
                  </div>
                )}

                <form
                  className={cx("space-y-4", !DEMO_PASSWORD && "mt-7")}
                  onSubmit={(ev) => {
                    ev.preventDefault();
                    signIn(email, password);
                  }}
                >
                  <label className="block">
                    <span className="text-sm font-medium">{t.signIn.email}</span>
                    <input
                      className={INPUT}
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
                      className={INPUT}
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
            <p className="mt-8 flex flex-wrap gap-x-5 gap-y-2 border-t border-line pt-4 text-sm">
              <Link href="/impact" className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
                {t.nav.impact} <ArrowRight aria-hidden className="size-3.5" />
              </Link>
              <Link href="/about" className="inline-flex items-center gap-1 font-medium text-brand hover:underline">
                {t.nav.about} <ArrowRight aria-hidden className="size-3.5" />
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
        <p className="rounded-xl border border-line bg-tray px-4 py-3 text-sm">{t.common.noRole}</p>
      ) : role === undefined ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-28 w-full" />
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
