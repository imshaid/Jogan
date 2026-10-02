"""Numbers in the docs: blocks of the Markdown files written from the evaluation artifacts.

``python -m jogan.eval.docs`` (``make docs``) rewrites every block

    <!-- numbers:NAME -->
    ...
    <!-- /numbers -->

in ``README.md``, ``docs/*.md`` and ``report/*.md`` from ``artifacts/metrics.json`` (``make
eval``) and ``artifacts/stress.json`` (``make stress``). Nothing is estimated here: every value is
a copy of an artifact value, rounded for reading. Prose outside the blocks carries no result
numbers. A test regenerates every file and compares it with the committed one, so a stale number
fails CI.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jogan.eval.web import BASELINES, METRICS, ROOT, SALARY

STRESS = ROOT / "artifacts" / "stress.json"
BLOCK = re.compile(
    r"(?P<open><!-- numbers:(?P<name>[a-z_]+) -->\n)(?P<body>.*?)(?P<close><!-- /numbers -->)",
    re.S,
)

NAMES = {
    "fixed_round": "Fixed round (status quo)",
    "threshold": "Threshold",
    "safety_stock": "Safety stock",
    "oracle": "Oracle (perfect foresight, not deployable)",
}
VERDICTS = {
    "a cheaper at every value": "Jogan cheaper at every value of a lost customer",
    "b cheaper at every value": "baseline cheaper at every value of a lost customer",
}


@dataclass(frozen=True)
class Sources:
    metrics: dict[str, Any]
    stress: dict[str, Any]

    @property
    def jogan(self) -> str:
        return f"jogan@{self.metrics['comparison']['jogan_value_tk']:g}"


def files() -> list[Path]:
    """The Markdown files that may hold blocks."""
    return [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "report").glob("*.md")),
    ]


def num(x: float, digits: int = 0) -> str:
    return f"{x:,.{digits}f}"


def ci(d: dict, digits: int = 0) -> str:
    """Mean with its interval over seeds, e.g. ``-2.25 (-2.69 to -1.81)``."""
    return f"{num(d['mean'], digits)} ({num(d['low'], digits)} to {num(d['high'], digits)})"


def pct(x: float, digits: int = 0) -> str:
    return f"{100 * x:.{digits}f}%"


def _days(window: list[str]) -> int:
    start, end = (date.fromisoformat(d) for d in window)
    return (end - start).days + 1


def _command(generated_by: str) -> str:
    """``make eval`` from ``make eval (python -m jogan.eval)``."""
    return generated_by.split(" (")[0]


def _scope(s: Sources) -> str:
    meta = s.metrics["meta"]
    seeds = meta["seeds"]
    test = meta["windows"]["test"]
    return (
        f"_Evaluation on simulated data: profile `{meta['profile']}`, {len(seeds)} seeds "
        f"({seeds[0]} to {seeds[-1]}), test window {test[0]} to {test[1]} ({_days(test)} days), "
        f"mean and {pct(meta['interval_level'])} interval over seeds. "
        f"Source: `artifacts/metrics.json`, written by `{_command(meta['generated_by'])}`._"
    )


def headline(s: Sources) -> str:
    m = s.metrics
    value = m["comparison"]["jogan_value_tk"]
    rows = [
        "| Policy | Lost requests per 1,000 | Lost requests | Runner km | Known cost (৳) |",
        "|---|---|---|---|---|",
    ]
    for name in (*BASELINES, s.jogan, "oracle"):
        p = m["policies"][name]["test"]
        label = NAMES.get(name, "**Jogan**")
        rows.append(
            f"| {label} | {ci(p['lost_per_1000'], 1)} | {ci(p['lost'])} | "
            f"{ci(p['runner_km'])} | {ci(p['known_cost_tk'][SALARY])} |"
        )
    versus = m["comparison"]["by_value"][f"{value:g}"]
    diff = [
        "",
        "Jogan minus each baseline, paired by seed (negative means Jogan is lower):",
        "",
        "| Baseline | Lost per 1,000 | Runner km | Known cost (৳) | Break-even |",
        "|---|---|---|---|---|",
    ]
    for b in BASELINES:
        v = versus[b]["test"]
        verdict = v["break_even_tk"][SALARY]["verdict"]
        diff.append(
            f"| {NAMES[b]} | {ci(v['lost_per_1000'], 2)} | {ci(v['runner_km'])} | "
            f"{ci(v['known_cost_tk'][SALARY])} | {VERDICTS.get(verdict, verdict)} |"
        )
    eid = versus[m["fairness"]["best_baseline"]]["eid"]["lost_per_1000"]
    window = m["meta"]["windows"]["eid"]
    notes = [
        "",
        f"In the Eid-ul-Azha window ({window[0]} to {window[1]}), Jogan minus the best baseline "
        f"({NAMES[m['fairness']['best_baseline']]}): {ci(eid, 2)} lost requests per 1,000.",
        "",
        f"Known cost is runner time and fuel, lost commission and idle liquidity at the middle "
        f"runner salary (`configs/ops/costs.yaml`); Jogan runs at a lost-customer value of "
        f"৳{value:g}. The oracle sees the future and only marks how much room is left.",
        "",
        _scope(s),
    ]
    return "\n".join(rows + diff + notes)


def limits(s: Sources) -> str:
    """Where Jogan does not win, with the numbers behind each point."""
    m = s.metrics
    h = m["hypotheses"]
    best = NAMES[m["fairness"]["best_baseline"]]
    # groups holding the same agents (e.g. the one urban territory) share a row
    worse: dict[str, list[str]] = {}
    for g in h["H4"]["worse_groups"]:
        col, name = g.split("=")
        d = m["fairness"]["groups"][col][name]["jogan_minus_best"]
        worse.setdefault(ci(d, 2), []).append(f"`{name}`")
    worse_text = "; ".join(
        f"{' and '.join(names)}{' (the same agents)' if len(names) > 1 else ''} {d}"
        for d, names in worse.items()
    )
    misses = h["H3"]["misses"]
    overall = [x for x in misses if x["group"] == "all="]
    gap = m["oracle_gap"]["test"]["lost_per_1000"]
    split = m["anomaly"]["windows_by_pattern"]["split"]
    a = m["anomaly"]
    lines = [
        f"- **Some groups are served worse than by the best baseline ({best}).** "
        f"Lost requests per 1,000, Jogan minus {best}: {worse_text}.",
        f"- **Forecast intervals are off their nominal coverage by more than 5 points in "
        f"{len(misses)} cells** (by side, horizon, interval and agent group), "
        f"{len(overall)} of them over all agents.",
        f"- **The oracle is still ahead:** Jogan minus the oracle, {ci(gap, 1)} lost requests "
        f"per 1,000.",
        f"- **The anomaly flag is weak on structuring:** split cash-outs found in "
        f"{split['detected']} of {split['windows']} injected windows; precision "
        f"{pct(a['flag_precision'], 1)} against a base rate of {pct(a['base_rate'], 2)}.",
        f"- **{len(m['does_not_win'])} group-level comparisons** (across lost-customer values and "
        f"baselines) show no significant win or a baseline as good or better "
        f"(`does_not_win` in `artifacts/metrics.json`).",
    ]
    return "\n".join(lines)


def stress(s: Sources) -> str:
    st = s.stress
    w, sm, sec, mach = st["world"], st["summary"], st["seconds"], st["meta"]["machine"]
    measures = {
        "One morning, end to end (s)": "morning_s",
        "Plan (s)": "plan_s",
        "of which MILP solver (s)": "solver_s",
        "Drivers, guardrails, flags (s)": "explain_s",
    }
    rows = ["| Measure | Mean | Max |", "|---|---|---|"]
    rows += [f"| {k} | {sm[v]['mean']:.1f} | {sm[v]['max']:.1f} |" for k, v in measures.items()]
    notes = [
        "",
        f"{num(w['agents'])} agents, {w['runners']} runners, {w['territories']} territories; "
        f"{w['plan_mornings']} Jogan mornings after {st['meta']['warmup_days']} days of status "
        f"quo. {sm['programs']} programs, {sm['fallbacks']} fallbacks, {num(sm['visits'])} "
        f"visits; peak memory {num(sm['peak_memory_mb'])} MB; whole run {sec['total']:.0f} s.",
        "",
        f"_Timing only, on {mach['cpu']} ({mach['logical_cpus']} threads). "
        f"Source: `artifacts/stress.json`, written by `{_command(st['meta']['generated_by'])}`._",
    ]
    return "\n".join(rows + notes)


def runtime(s: Sources) -> str:
    """How long the heavy commands took when they made the committed artifacts."""
    meta, st = s.metrics["meta"], s.stress
    mach = st["meta"]["machine"]
    return (
        f"`make eval` took {meta['runtime_s'] / 60:.0f} min for {len(meta['seeds'])} seeds "
        f"(`meta.runtime_s`). `make stress` took {st['seconds']['total']:.0f} s at a peak of "
        f"{num(st['summary']['peak_memory_mb'])} MB on {mach['cpu']} ({mach['logical_cpus']} "
        f"threads, {mach['memory_gb']:.0f} GB RAM)."
    )


RENDERERS: dict[str, Callable[[Sources], str]] = {
    "headline": headline,
    "limits": limits,
    "runtime": runtime,
    "stress": stress,
}


def fill(text: str, s: Sources) -> str:
    """``text`` with every block rewritten; an unknown block name is an error."""

    def sub(match: re.Match[str]) -> str:
        name = match["name"]
        if name not in RENDERERS:
            raise KeyError(f"unknown numbers block {name!r}; known: {sorted(RENDERERS)}")
        return match["open"] + RENDERERS[name](s).rstrip("\n") + "\n" + match["close"]

    return BLOCK.sub(sub, text)


def load(metrics: Path = METRICS, stress_path: Path = STRESS) -> Sources:
    return Sources(json.loads(metrics.read_text()), json.loads(stress_path.read_text()))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    s = load()
    for path in files():
        old = path.read_text()
        new = fill(old, s)
        if new != old:
            path.write_text(new)
            print(f"updated {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
