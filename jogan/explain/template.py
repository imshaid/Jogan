"""Template explanations in English and Bangla, built only from a recommendation's evidence.

The template is the explanation of record: it is deterministic, every number in it is read
from the stored evidence, and the Gemini narrator (:mod:`jogan.explain.narrator`) may only
reword it. Taka amounts use Bangladesh's lakh grouping (1,23,456); Bangla text uses Bangla
digits.
"""

from __future__ import annotations

import math
from typing import Any

from jogan.explain.config import load_labels

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def group_lakh(n: int) -> str:
    """``1234567`` → ``12,34,567``."""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        pairs = []
        while len(head) > 2:
            head, pairs = head[:-2], [head[-2:], *pairs]
        s = ",".join([head, *pairs, tail])
    return ("-" if n < 0 else "") + s


def digits(text: str, lang: str) -> str:
    return text.translate(BN_DIGITS) if lang == "bn" else text


def tk(x: float, lang: str) -> str:
    return digits(f"৳{group_lakh(round(x))}", lang)


def pct(p: float, lang: str) -> str:
    return digits(f"{round(p * 100)}%", lang)


def number(x: float, lang: str, places: int = 0) -> str:
    text = f"{x:.{places}f}" if places else group_lakh(round(x))
    return digits(text, lang)


def _unit(name: str, text: str, lang: str) -> str:
    return load_labels()["units"][name][lang].format(x=text)


def value_text(unit: str, value: Any, lang: str) -> str:
    """A feature value as shown to users."""
    labels = load_labels()["values"]
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return {"en": "no data", "bn": "তথ্য নেই"}[lang]
    if unit == "flag":
        return labels["flag"]["true" if float(value) >= 0.5 else "false"][lang]
    if unit == "text":
        for kind in ("setting", "size_class"):
            if str(value) in labels[kind]:
                return labels[kind][str(value)][lang]
        return str(value)
    if unit == "weekday":
        return labels["weekday"][lang][int(value) % 7]
    if unit == "hour":
        return digits(f"{int(value) % 24:02d}:00", lang)
    if unit == "tk":
        return tk(float(value), lang)
    if unit == "km":
        return _unit("km", number(float(value), lang, 1), lang)
    if unit in ("hours", "days"):
        return _unit(unit, number(float(value), lang), lang)
    if unit == "ratio":
        return _unit("ratio", number(float(value), lang, 1), lang)
    return number(float(value), lang)


def feature_text(name: str, value: Any, lang: str, section: str = "features") -> tuple[str, str]:
    """``(label, value)`` of a forecast or anomaly feature."""
    entry = load_labels()[section].get(name, {"unit": "count", "en": name, "bn": name})
    return entry[lang], value_text(entry["unit"], value, lang)


def side_text(side: str, lang: str) -> str:
    return load_labels()["values"]["side"][side][lang]


def _copy(key: str, lang: str, **kw: str) -> str:
    return load_labels()["copy"][key][lang].format(**kw)


def anomaly_items(items: list[dict], lang: str) -> str:
    sep = load_labels()["copy"]["list_sep"][lang]
    parts = []
    for it in items:
        label, value = feature_text(it["feature"], it["value"], lang, "anomaly_features")
        parts.append(f"{label} {value}")
    return sep.join(parts)


def reason_text(reason: dict, lang: str) -> str:
    """One manual-review reason as a phrase."""
    code = reason["code"]
    phrase = load_labels()["reasons"][code][lang]
    if code == "out_of_range":
        label, value = feature_text(reason["feature"], reason["value"], lang)
        return phrase.format(label=label, value=value)
    if code == "wide_interval":
        return phrase.format(ratio=_unit("ratio", number(reason["ratio"], lang, 1), lang))
    if code == "data_gap":
        return phrase.format(arrived=number(reason["arrived"], lang))
    if code == "short_history":
        return phrase.format(windows=number(reason["windows"], lang))
    if code == "anomaly":
        date = digits(str(reason["date"]), lang)
        return phrase.format(date=date, items=anomaly_items(reason["items"], lang))
    return phrase


def facts(rec: dict, lang: str) -> dict[str, Any]:
    """The evidence of one recommendation as display text: what the template says, structured.

    This is also what the narrator receives, so its numbers are already written the way the
    template writes them.
    """
    if lang not in ("en", "bn"):
        raise ValueError(f"unknown language {lang!r}")
    ev = rec["evidence"]
    side = ev.get("side") or "cash"
    drivers = []
    for d in ev.get("drivers") or []:
        label, value = feature_text(d["feature"], d["value"], lang)
        sign = "+" if d["effect_pct"] >= 0 else "-"
        drivers.append(
            {
                "feature": label,
                "value": value,
                "effect": digits(f"{sign}{abs(d['effect_pct'])}%", lang),
            }
        )
    review = ev.get("review") or {}
    return {
        "agent": rec["agent_id"],
        "territory": rec["territory"],
        "runner": rec["runner_id"],
        "side_at_risk": side_text(side, lang),
        "stockout_chance_24h": pct(ev[f"p_stockout_{side}"], lang),
        "cash_now": tk(ev["cash_tk"], lang),
        "efloat_now": tk(ev["efloat_tk"], lang),
        "drain_24h_q90": tk(ev[f"drain_{side}_q90"], lang),
        "drain_24h_median": tk(ev[f"drain_{side}_q50"], lang),
        "target_cash": tk(rec["target_cash_tk"], lang),
        "value_of_visit": tk(rec["value_tk"], lang),
        "drivers": drivers,
        "manual_review": [reason_text(r, lang) for r in review.get("reasons", [])],
    }


def render(rec: dict, lang: str) -> str:
    """The template explanation of one recommendation (a queue row with its evidence)."""
    f = facts(rec, lang)
    sep = load_labels()["copy"]["list_sep"][lang]
    side = f["side_at_risk"]
    sentences = [
        _copy("headline", lang, runner=f["runner"], agent=f["agent"], territory=f["territory"]),
        _copy("risk", lang, side=side, side_title=side[:1].upper() + side[1:],
              p=f["stockout_chance_24h"]),
        _copy("balances", lang, cash=f["cash_now"], efloat=f["efloat_now"]),
        _copy("drain", lang, side=side, q90=f["drain_24h_q90"], q50=f["drain_24h_median"]),
        _copy("target", lang, target=f["target_cash"], value=f["value_of_visit"]),
    ]  # fmt: skip
    if f["drivers"]:
        items = []
        for d in f["drivers"]:
            key = "driver_up" if d["effect"].startswith("+") else "driver_down"
            share = d["effect"][1:]
            items.append(_copy(key, lang, label=d["feature"], value=d["value"], pct=share))
        sentences.append(_copy("drivers", lang, items=sep.join(items)))
    if f["manual_review"]:
        sentences.append(_copy("review", lang, reasons=sep.join(f["manual_review"])))
    elif "review" in rec["evidence"]:
        sentences.append(_copy("no_review", lang))
    return " ".join(sentences)


def risk_percent(rec: dict) -> float:
    """The stock-out chance the template shows, in percent (the narrator must keep it)."""
    ev = rec["evidence"]
    return float(round(ev[f"p_stockout_{ev.get('side') or 'cash'}"] * 100))
