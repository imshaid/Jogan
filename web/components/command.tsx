"use client";

import { CornerDownLeft, Search, Store, type LucideIcon } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { NetworkAgent, Recommendation } from "@/lib/api";
import { usePeek } from "@/lib/data";
import { keys, useMeta } from "@/lib/hooks";
import { useLang } from "@/lib/i18n";

import { cx } from "./ui";

export type Command = { id: string; label: string; hint?: string; Icon: LucideIcon; run: () => void };

type Group = { name: string; items: Command[] };

const AGENT_ID = /^[A-Z]{3}-\d{3}$/;
const MAX_AGENTS = 6;

// Search agents by id, jump to a page or run an action. Agent ids come from the network or the
// plan already loaded for the day in view; nothing is fetched from here.
export function CommandDialog({
  pages,
  actions,
  onClose,
}: {
  pages: Command[];
  actions: Command[];
  onClose: () => void;
}) {
  const { t } = useLang();
  const router = useRouter();
  const params = useSearchParams();
  const meta = useMeta();
  const day = params.get("day") ?? meta.data?.plan_dates[0] ?? null;
  const network = usePeek<{ agents: NetworkAgent[] }>(day && keys.network(day));
  const plan = usePeek<{ items: Recommendation[] }>(day && keys.plan(day));
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);

  const groups = useMemo<Group[]>(() => {
    const q = query.trim().toLowerCase();
    const match = (c: Command) => !q || c.label.toLowerCase().includes(q) || c.hint?.toLowerCase().includes(q);
    const ids = network?.agents.map((a) => a.agent_id) ?? plan?.items.map((r) => r.agent_id) ?? [];
    const found = q ? ids.filter((id) => id.toLowerCase().includes(q)).sort().slice(0, MAX_AGENTS) : [];
    const typed = query.trim().toUpperCase();
    if (AGENT_ID.test(typed) && !found.includes(typed)) found.unshift(typed);
    const openAgent = (id: string): Command => ({
      id: `agent:${id}`,
      label: t.cmd.openAgent(id),
      hint: id,
      Icon: Store,
      run: () => router.push(day ? `/agents/${id}?day=${day}` : `/agents/${id}`),
    });
    return [
      { name: t.cmd.agents, items: found.map(openAgent) },
      { name: t.cmd.pages, items: pages.filter(match) },
      { name: t.cmd.actions, items: actions.filter(match) },
    ].filter((g) => g.items.length);
  }, [query, network, plan, pages, actions, day, router, t]);

  const flat = groups.flatMap((g) => g.items);
  const current = flat[Math.min(active, flat.length - 1)];

  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    input.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      before?.focus?.();
    };
  }, []);

  useEffect(() => {
    if (current) document.getElementById(`${listId}-${current.id}`)?.scrollIntoView({ block: "nearest" });
  }, [current, listId]);

  function run(c: Command | undefined) {
    if (!c) return;
    onClose();
    c.run();
  }

  return (
    <div className="fixed inset-0 z-50">
      <div aria-hidden className="absolute inset-0 bg-ink/25 backdrop-blur-[2px]" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t.cmd.label}
        className="relative mx-auto mt-[12vh] w-[min(560px,calc(100%-2rem))] overflow-hidden rounded-2xl border border-line bg-surface shadow-pop"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-4">
          <Search aria-hidden className="size-4 shrink-0 text-fg-3" />
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={current ? `${listId}-${current.id}` : undefined}
            aria-label={t.cmd.label}
            value={query}
            placeholder={t.cmd.placeholder}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") setActive((a) => Math.min(flat.length - 1, a + 1));
              else if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
              else if (e.key === "Enter") run(current);
              else if (e.key === "Escape") onClose();
              else if (e.key === "Tab") {
                // the dialog has one control; Tab stays in it
              } else return;
              e.preventDefault();
            }}
            className="h-12 min-w-0 flex-1 bg-transparent text-[15px] text-fg outline-none placeholder:text-fg-3 focus-visible:outline-none"
          />
          <kbd className="mono rounded-md border border-line bg-tray px-1.5 py-0.5 text-[11px] text-fg-3">Esc</kbd>
        </div>
        <ul id={listId} role="listbox" aria-label={t.cmd.label} className="max-h-[min(420px,55vh)] overflow-y-auto p-1.5">
          {flat.length === 0 && (
            <li role="presentation" className="px-3 py-8 text-center text-sm text-fg-2">
              {t.cmd.empty}
            </li>
          )}
          {groups.map((g) => (
            <li key={g.name} role="presentation">
              <div className="eyebrow px-2.5 pt-2.5 pb-1 text-fg-3">{g.name}</div>
              <ul role="presentation">
                {g.items.map((c) => {
                  const on = c === current;
                  return (
                    <li
                      key={c.id}
                      id={`${listId}-${c.id}`}
                      role="option"
                      aria-selected={on}
                      onPointerMove={() => setActive(flat.indexOf(c))}
                      onClick={() => run(c)}
                      className={cx(
                        "flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm",
                        on ? "bg-tray text-fg" : "text-fg-2",
                      )}
                    >
                      <span
                        className={cx(
                          "flex size-7 shrink-0 items-center justify-center rounded-md border",
                          on ? "border-line-strong bg-surface text-brand" : "border-line bg-surface text-fg-3",
                        )}
                      >
                        <c.Icon aria-hidden className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1 truncate">{c.label}</span>
                      {on && <CornerDownLeft aria-hidden className="size-3.5 text-fg-3" />}
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
        <div className="border-t border-line bg-tray px-4 py-2 text-[11px] text-fg-3">{t.cmd.hint}</div>
      </div>
    </div>
  );
}
