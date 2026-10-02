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
SIDES = {"cash": "Cash", "efloat": "E-float"}
METHODS = {
    "empirical": "Empirical",
    "naive_cqr": "Naive + CQR",
    "model": "LightGBM",
    "model_cqr": "LightGBM + CQR",
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


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return out + ["| " + " | ".join(r) + " |" for r in rows]


def verdict(be: dict) -> str:
    """A break-even entry in words; A is Jogan, B the baseline."""
    v = be["verdict"]
    if v.endswith("every value"):
        who = "Jogan" if v.startswith("a") else "baseline"
        return f"{who} cheaper at every value of a lost customer"
    if v in ("a cheaper above the value", "a cheaper below the value"):
        side = v.split()[2]
        where = f"৳{be['value']:.2f} per lost request"
        if be["bounded"]:
            where += f" ({be['low']:.2f} to {be['high']:.2f})"
        else:
            where += " (interval unbounded)"
        return f"Jogan cheaper {side} {where}"
    return {"a cheaper": "Jogan cheaper", "b cheaper": "baseline cheaper"}.get(v, v)


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
        diff.append(
            f"| {NAMES[b]} | {ci(v['lost_per_1000'], 2)} | {ci(v['runner_km'])} | "
            f"{ci(v['known_cost_tk'][SALARY])} | {verdict(v['break_even_tk'][SALARY])} |"
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


# --- model card (docs/04-model-card.md) ------------------------------------------------------


def _forecast(s: Sources) -> dict:
    return s.metrics["forecast"]["forecast"]


def forecast(s: Sources) -> str:
    """Accuracy and calibration per side and horizon, against true demand."""
    rows = []
    for side, by_h in _forecast(s).items():
        for h in sorted(by_h, key=int):
            f = by_h[h]
            pin = " / ".join(num(f["methods"][k]["pinball_truth"]) for k in METHODS)
            i90 = f["intervals"]["truth"]["90"]
            so = f["stockout"]
            rows.append(
                [
                    SIDES[side],
                    f"{h} h",
                    pin,
                    f"{pct(i90['coverage'], 1)} (৳{num(i90['mean_width_tk'])})",
                    f"{so['empirical']['brier']:.3f} / {so['model_cqr']['brier']:.3f}",
                    pct(so["base_rate"], 1),
                ]
            )
    header = [
        "Side",
        "Horizon",
        "Pinball loss, ৳: " + " / ".join(METHODS.values()),
        "90% interval: coverage (mean width)",
        "Brier: Empirical / LightGBM + CQR",
        "Stock-out base rate",
    ]
    notes = [
        "",
        "Pinball loss is averaged over the eight quantile levels and scored against true demand "
        "(lower is better). Coverage is of the calibrated LightGBM interval against true demand "
        "(nominal 90%). Brier scores the stock-out chance for the no-top-up event (lower is "
        "better).",
        "",
        _scope(s),
    ]
    return "\n".join(table(header, rows) + notes)


def calibration(s: Sources) -> str:
    """Interval coverage at 24 h by level, period and agent group."""
    f = _forecast(s)
    levels = sorted(f["cash"]["24"]["intervals"]["truth"], key=int)
    rows = [
        ["All agents, test window"]
        + [
            pct(f[side]["24"]["intervals"]["truth"][lv]["coverage"], 1)
            for side in f
            for lv in levels
        ]
    ]
    for period, label in (("eid", "Eid-ul-Azha days"), ("other", "Other days")):
        rows.append(
            [label]
            + [
                pct(f[side]["24"]["periods"][period]["intervals_truth"][lv]["coverage"], 1)
                for side in f
                for lv in levels
            ]
        )
    for col, groups in f["cash"]["24"]["groups"].items():
        for g in groups:
            rows.append(
                [f"`{col}` = `{g}`"]
                + [
                    pct(f[side]["24"]["groups"][col][g]["intervals_truth"][lv]["coverage"], 1)
                    for side in f
                    for lv in levels
                ]
            )
    header = ["24-hour forecast"] + [f"{SIDES[side]} {lv}%" for side in f for lv in levels]
    misses = s.metrics["hypotheses"]["H3"]["misses"]
    overall = [x for x in misses if x["group"] == "all="]
    notes = [
        "",
        f"Cells off nominal by more than 5 points (every side, horizon, interval and group): "
        f"{len(misses)}. Over all agents: "
        + "; ".join(
            f"{SIDES[x['side']].lower()} {x['horizon_h']} h {x['interval']}% at "
            f"{pct(x['coverage'], 1)}"
            for x in overall
        )
        + ".",
    ]
    return "\n".join(table(header, rows) + notes)


def censoring(s: Sources) -> str:
    """How much served flows understate demand, and how the estimated labels fix it."""
    c = s.metrics["forecast"]["censoring"]
    rows = []
    for side, by_h in c["label_bias"].items():
        b = by_h["24"]
        rows.append(
            [
                SIDES[side],
                pct(b["all"]["served"]["relative"], 1),
                pct(b["all"]["estimated"]["relative"], 1),
                pct(b["with_lost"]["served"]["relative"], 1),
                pct(b["with_lost"]["estimated"]["relative"], 1),
                f"{pct(c['flags'][side]['precision'])} / {pct(c['flags'][side]['recall'])}",
            ]
        )
    header = [
        "Side (24 h peak drain)",
        "Bias, served flows",
        "Bias, estimated (used)",
        "Bias with lost requests, served",
        "Bias with lost requests, estimated",
        "Stock-out flag precision / recall",
    ]
    note = [
        "",
        f"Bias is the mean label minus true demand, relative to true demand, on the test window. "
        f"Strategy in use: `{c['strategy']}`.",
    ]
    return "\n".join(table(header, rows) + note)


def anomaly(s: Sources) -> str:
    a = s.metrics["anomaly"]
    names = {"night": "Night activity", "spike": "Unexplained spike", "split": "Split cash-outs"}
    rows = [
        [names.get(k, k), str(v["windows"]), str(v["detected"])]
        for k, v in a["windows_by_pattern"].items()
    ]
    pk = a["precision_at_k_mean"]
    notes = [
        "",
        f"{num(a['agent_days'])} test agent-days; {num(a['flagged'])} flagged "
        f"({pct(a['flagged'] / a['agent_days'], 1)}), {a['flagged_true']} of them on injected "
        f"anomalies: precision {pct(a['flag_precision'], 1)} against a base rate of "
        f"{pct(a['base_rate'], 2)}. Precision at 5 / 10 / 20 per seed, averaged: "
        + " / ".join(f"{pk[k]:.2f}" for k in sorted(pk, key=int))
        + f". Injected windows with at least one flag: {a['windows_detected']} of {a['windows']}.",
    ]
    header = ["Injected pattern", "Windows", "With a flag"]
    return "\n".join(table(header, rows) + notes)


# --- evaluation (docs/05-evaluation.md) -------------------------------------------------------


def _value(s: Sources) -> str:
    return f"{s.metrics['comparison']['jogan_value_tk']:g}"


def _values(s: Sources) -> list[tuple[str, dict]]:
    """The lost-customer values swept by ``make eval``, in numeric order."""
    return sorted(s.metrics["comparison"]["by_value"].items(), key=lambda kv: float(kv[0]))


def costs(s: Sources) -> str:
    """Known cost by component, test window, middle salary."""
    m = s.metrics
    parts = {
        "lost_commission": "Lost commission",
        "runner_time": "Runner time",
        "runner_fuel": "Runner fuel",
        "idle_liquidity": "Idle liquidity",
    }
    rows = []
    for name in (*BASELINES, s.jogan):
        p = m["policies"][name]["test"]
        rows.append(
            [NAMES.get(name, "**Jogan**")]
            + [num(p["cost_tk"][k]["mean"]) for k in parts]
            + [num(p["known_cost_tk"][SALARY]["mean"]), num(p["runner_visits"]["mean"])]
        )
    header = ["Policy", *parts.values(), "Known cost", "Runner visits"]
    note = ["", "Means over seeds in ৳, middle runner salary, test window."]
    return "\n".join(table(header, rows) + note)


def by_value(s: Sources) -> str:
    """Jogan at every lost-customer value: its service, and its total cost against each baseline."""
    m = s.metrics
    rows = []
    for v, versus in _values(s):
        p = m["policies"][f"jogan@{v}"]["test"]
        rows.append(
            [
                f"৳{v}",
                ci(p["lost_per_1000"], 1),
                num(p["runner_km"]["mean"]),
                *(ci(versus[b]["test"]["total_cost_tk"][SALARY]) for b in BASELINES),
            ]
        )
    header = [
        "Lost-customer value",
        "Jogan lost per 1,000",
        "Jogan runner km",
        *(f"Total cost, Jogan minus {NAMES[b]} (৳)" for b in BASELINES),
    ]
    note = [
        "",
        "Total cost = known cost + the value times lost requests, middle salary, test window. The "
        "same value is used to plan (Jogan's setting) and to price the outcome.",
    ]
    return "\n".join(table(header, rows) + note)


def break_even(s: Sources) -> str:
    """Break-even verdict for every value and baseline; other salaries only where they differ."""
    rows = []
    for v, versus in _values(s):
        cells = []
        for b in BASELINES:
            be = versus[b]["test"]["break_even_tk"]
            cell = verdict(be[SALARY])
            others = [f"{sal} salary: {verdict(be[sal])}" for sal in ("low", "high")]
            others = [
                o
                for o, sal in zip(others, ("low", "high"), strict=True)
                if be[sal]["verdict"] != be[SALARY]["verdict"]
            ]
            cells.append(cell + (f" ({'; '.join(others)})" if others else ""))
        rows.append([f"৳{v}", *cells])
    header = ["Jogan's setting", *(NAMES[b] for b in BASELINES)]
    note = [
        "",
        "Middle runner salary; the low and high salary are named only where their verdict differs.",
    ]
    return "\n".join(table(header, rows) + note)


def hypotheses(s: Sources) -> str:
    m = s.metrics
    h = m["hypotheses"]
    h1 = "; ".join(
        f"{NAMES[b]}: {verdict(e['break_even_tk'])}" for b, e in h["H1"]["by_baseline"].items()
    )
    best = NAMES[h["H2"]["best_baseline"]]
    misses = h["H3"]["misses"]
    rows = [
        ["H1", h["H1"]["statement"], f"at ৳{h['H1']['jogan_value_tk']:g}: {h1}"],
        [
            "H2",
            h["H2"]["statement"],
            f"{'holds' if h['H2']['holds'] else 'fails'}: against {best}, "
            f"{ci(h['H2']['lost_per_1000'], 2)} lost per 1,000 and "
            f"{ci(h['H2']['runner_km'])} km",
        ],
        [
            "H3",
            h["H3"]["statement"],
            f"{'holds' if h['H3']['holds'] else 'fails'}: {len(misses)} cells outside ±5 points",
        ],
        [
            "H4",
            h["H4"]["statement"],
            f"{'holds' if h['H4']['holds'] else 'fails'}: worse in "
            + ", ".join(f"`{g}`" for g in h["H4"]["worse_groups"]),
        ],
    ]
    return "\n".join(table(["", "Hypothesis", "Result"], rows))


def fairness(s: Sources) -> str:
    m = s.metrics
    f = m["fairness"]
    best = f["best_baseline"]
    rows = []
    for col, groups in f["groups"].items():
        for g, row in groups.items():
            d = row["jogan_minus_best"]
            rows.append(
                [
                    f"`{col}`",
                    f"`{g}`",
                    ci(row[s.jogan], 1),
                    ci(row[best], 1),
                    ci(d, 2),
                    d["sign"],
                ]
            )
    header = [
        "Group",
        "Value",
        "Jogan lost per 1,000",
        f"{NAMES[best]} lost per 1,000",
        "Jogan minus best",
        "Verdict",
    ]
    return "\n".join(table(header, rows))


def ablations(s: Sources) -> str:
    m = s.metrics
    names = {
        "greedy": "Greedy round instead of the MILP (same forecast and levels)",
        "two_sided": "Two-sided newsvendor split instead of the typical split",
    }
    rows = [
        [
            names.get(k, k),
            ci(a["test"]["lost_per_1000"], 2),
            ci(a["test"]["runner_km"]),
            ci(a["test"]["known_cost_tk"][SALARY]),
        ]
        for k, a in m["ablations"].items()
    ]
    header = ["Jogan minus …", "Lost per 1,000", "Runner km", "Known cost (৳)"]
    return "\n".join(table(header, rows))


def eid(s: Sources) -> str:
    m = s.metrics
    versus = m["comparison"]["by_value"][_value(s)]
    rows = []
    for name in (*BASELINES, s.jogan, "oracle"):
        p = m["policies"][name]["eid"]
        diff = ci(versus[name]["eid"]["lost_per_1000"], 2) if name in BASELINES else ""
        rows.append(
            [
                NAMES.get(name, "**Jogan**"),
                ci(p["lost_per_1000"], 1),
                num(p["runner_km"]["mean"]),
                diff,
            ]
        )
    window = m["meta"]["windows"]["eid"]
    header = ["Policy", "Lost per 1,000", "Runner km", "Jogan minus this policy, lost per 1,000"]
    note = ["", f"Eid-ul-Azha window: {window[0]} to {window[1]} ({_days(window)} days)."]
    return "\n".join(table(header, rows) + note)


def does_not_win(s: Sources) -> str:
    m = s.metrics
    value = float(_value(s))
    rows = [
        [
            NAMES[d["baseline"]],
            f"`{d['column']}` = `{d['group']}`",
            ci(d["difference"], 2),
            d["why"],
        ]
        for d in m["does_not_win"]
        if d["jogan_value_tk"] == value
    ]
    header = ["Baseline", "Agent group", "Jogan minus baseline, lost per 1,000", "Why no win"]
    counts: dict[str, int] = {}
    for d in m["does_not_win"]:
        counts[d["why"]] = counts.get(d["why"], 0) + 1
    note = [
        "",
        f"At Jogan's setting of ৳{value:g}. Over every setting: "
        + ", ".join(f"{n} {why}" for why, n in counts.items())
        + f" ({len(m['does_not_win'])} in all).",
    ]
    return "\n".join(table(header, rows) + note)


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
    "ablations": ablations,
    "anomaly": anomaly,
    "break_even": break_even,
    "by_value": by_value,
    "calibration": calibration,
    "censoring": censoring,
    "costs": costs,
    "does_not_win": does_not_win,
    "eid": eid,
    "fairness": fairness,
    "forecast": forecast,
    "headline": headline,
    "hypotheses": hypotheses,
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
