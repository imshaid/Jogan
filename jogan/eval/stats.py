"""Paired comparisons across seeds: mean differences and break-even values with intervals.

Policies run on the same worlds with common random numbers (D-017), so each seed gives one
paired difference. Means get a Student-t interval over the seeds. The break-even value of a
lost customer is a ratio of two paired means, ``mean(Δ known cost) / mean(Δ lost requests)``,
and gets Fieller's interval (Fieller 1954, JRSS B 16(2), 175-185), which stays honest when the
denominator is close to zero: the interval is then unbounded, and reported as such.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import t as student_t


def _r(x: float | None, digits: int = 4) -> float | None:
    return None if x is None or not math.isfinite(x) else round(float(x), digits)


def t_quantile(level: float, n: int) -> float:
    """Two-sided Student-t quantile for ``n`` paired observations."""
    return float(student_t.ppf((1 + level) / 2, n - 1))


def mean_interval(x, level: float, digits: int = 4) -> dict:
    """Mean with a t-interval (``None`` bounds below two observations)."""
    x = np.asarray(x, dtype=float)
    n, mean = len(x), float(x.mean())
    if n < 2:
        return {"mean": _r(mean, digits), "low": None, "high": None, "n": n}
    half = t_quantile(level, n) * float(x.std(ddof=1)) / math.sqrt(n)
    return {
        "mean": _r(mean, digits),
        "low": _r(mean - half, digits),
        "high": _r(mean + half, digits),
        "n": n,
    }


def paired(a, b, level: float, digits: int = 4) -> dict:
    """Interval of the mean of ``a - b`` with a sign verdict."""
    out = mean_interval(np.asarray(a, dtype=float) - np.asarray(b, dtype=float), level, digits)
    if out["low"] is not None and out["low"] > 0:
        out["sign"] = "higher"
    elif out["high"] is not None and out["high"] < 0:
        out["sign"] = "lower"
    else:
        out["sign"] = "no significant difference"
    return out


def fieller(num, den, level: float) -> dict:
    """``mean(num) / mean(den)`` with Fieller's interval for paired observations."""
    num, den = np.asarray(num, dtype=float), np.asarray(den, dtype=float)
    n, a, b = len(num), float(num.mean()), float(den.mean())
    ratio = a / b if b != 0 else None
    if n < 2:
        return {"value": _r(ratio, 2), "low": None, "high": None, "bounded": False}
    t2 = t_quantile(level, n) ** 2
    cov = np.cov(num, den, ddof=1) / n  # variances and covariance of the two means
    qa, qb, qc = b * b - t2 * cov[1, 1], a * b - t2 * cov[0, 1], a * a - t2 * cov[0, 0]
    disc = qb * qb - qa * qc
    if qa <= 0 or disc < 0:  # the denominator is not clearly away from zero
        return {"value": _r(ratio, 2), "low": None, "high": None, "bounded": False}
    root = math.sqrt(disc)
    return {
        "value": _r(ratio, 2),
        "low": _r((qb - root) / qa, 2),
        "high": _r((qb + root) / qa, 2),
        "bounded": True,
    }


def break_even(cost_a, lost_a, cost_b, lost_b, level: float) -> dict:
    """Value per lost request at which policies A and B cost the same, paired over seeds.

    ``cost_*`` is the known cost and ``lost_*`` the lost requests per seed. The verdict says for
    which values A is cheaper, from the mean differences (as :func:`jogan.ops.costs.break_even`
    does for one run).
    """
    extra_cost = np.asarray(cost_a, dtype=float) - np.asarray(cost_b, dtype=float)
    saved = np.asarray(lost_b, dtype=float) - np.asarray(lost_a, dtype=float)
    dc, dl = float(extra_cost.mean()), float(saved.mean())
    out = fieller(extra_cost, saved, level)
    if dl > 0:
        verdict = "a cheaper at every value" if dc <= 0 else "a cheaper above the value"
    elif dl < 0:
        verdict = "b cheaper at every value" if dc >= 0 else "a cheaper below the value"
    else:
        verdict = "a cheaper" if dc < 0 else "b cheaper" if dc > 0 else "equal"
    if verdict.endswith("every value"):
        out = {"value": None, "low": None, "high": None, "bounded": False}
    seeds_a_dominates = int(((extra_cost <= 0) & (saved >= 0)).sum())
    return {**out, "verdict": verdict, "seeds_a_cheaper_and_fewer_lost": seeds_a_dominates}
