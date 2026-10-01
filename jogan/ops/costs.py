"""Prices DERIVED from the sourced inputs in ``configs/ops/costs.yaml`` (D-019).

- commission rate = Tk per 1,000 ÷ 1,000
- runner fuel, Tk per km = petrol price on the day ÷ km per litre of the setting
- runner time, Tk per minute = monthly salary ÷ (hours per week · 60 · weeks per month)

The value of a customer lost after a failed request is not priced: :func:`break_even` gives the
value per lost request at which two policies cost the same.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import numpy as np

from jogan.ops.config import Costs
from jogan.sim.config import Setting, TxType

WEEKS_PER_MONTH = 365.25 / 12 / 7  # average Gregorian month


def commission_rate(costs: Costs) -> dict[TxType, float]:
    return {side: tk / 1000 for side, tk in costs.agent_commission_per_1000_tk.items()}


def salary_tk_per_month(costs: Costs) -> float:
    """Midpoint of the sourced salary range."""
    low, high = costs.runner.salary_tk_per_month
    return (low + high) / 2


def labour_tk_per_minute(costs: Costs, salary: float | None = None) -> float:
    minutes = costs.runner.hours_per_week * 60 * WEEKS_PER_MONTH
    return (salary_tk_per_month(costs) if salary is None else salary) / minutes


def petrol_tk_per_litre(costs: Costs, dates: Sequence[dt.date]) -> np.ndarray:
    """Official price in force on each date."""
    table = costs.runner.petrol_tk_per_litre
    starts = np.array([d for d, _ in table], dtype="datetime64[D]")
    days = np.asarray(dates, dtype="datetime64[D]")
    if (days < starts[0]).any():
        raise ValueError(f"no petrol price before {table[0][0]}")
    idx = np.searchsorted(starts, days, side="right") - 1
    return np.array([price for _, price in table])[idx]


def fuel_tk_per_km(costs: Costs, dates: Sequence[dt.date], setting: Setting) -> np.ndarray:
    return petrol_tk_per_litre(costs, dates) / costs.runner.km_per_litre[setting]


def break_even(cost_a: float, lost_a: int, cost_b: float, lost_b: int) -> dict[str, object]:
    """Value per lost request at which policies A and B cost the same.

    ``cost_*`` is the known cost (everything but lost customers). A is cheaper for every value
    above the break-even when it loses fewer requests, and for every value below it when it
    loses more.
    """
    if lost_a == lost_b:
        verdict = "a" if cost_a < cost_b else "b" if cost_b < cost_a else "equal"
        return {"value_tk": None, "cheaper": verdict}
    value = (cost_a - cost_b) / (lost_b - lost_a)
    if value <= 0:  # one policy is cheaper at every non-negative value
        return {"value_tk": None, "cheaper": "a" if lost_a < lost_b else "b"}
    side = "above" if lost_a < lost_b else "below"
    return {"value_tk": round(value, 2), "cheaper": f"a {side}"}
