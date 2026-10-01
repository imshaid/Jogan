"""Daily calendar for a window: weekdays, bank days, public holidays, Ramadan and Eid."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from jogan.sim.config import WEEKDAYS, CalendarConfig


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """First and last day of a ``YYYY-MM`` month."""
    first = dt.date.fromisoformat(f"{month}-01")
    after = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first, after - dt.timedelta(days=1)


def build_calendar(cal: CalendarConfig, start: dt.date, end: dt.date) -> pd.DataFrame:
    """One row per day from ``start`` to ``end`` inclusive. All columns are public knowledge."""
    days = [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]

    names: dict[dt.date, tuple[str, str]] = {}
    for holiday in cal.holidays:
        for day in holiday.days():
            names[day] = (holiday.name_en, holiday.name_bn)
    for eid in cal.eids:
        span = (eid.holidays[1] - eid.holidays[0]).days + 1
        for i in range(span):
            names[eid.holidays[0] + dt.timedelta(days=i)] = (eid.name_en, eid.name_bn)

    eids = sorted(cal.eids, key=lambda e: e.date)
    weekend = {WEEKDAYS.index(d) for d in cal.bank_weekend}
    rows = []
    for day in days:
        upcoming = [e for e in eids if e.date >= day]
        past = [e for e in eids if e.date <= day]
        rows.append(
            {
                "date": day,
                "weekday": day.weekday(),
                "day": day.day,
                "month": day.month,
                "bank_open": day.weekday() not in weekend and day not in names,
                "holiday_en": names.get(day, (None, None))[0],
                "holiday_bn": names.get(day, (None, None))[1],
                "is_ramadan": cal.ramadan.start <= day <= cal.ramadan.end,
                "eid": next((e.key for e in eids if e.date == day), None),
                "next_eid": upcoming[0].key if upcoming else None,
                "days_to_eid": (upcoming[0].date - day).days if upcoming else None,
                "days_since_eid": (day - past[-1].date).days if past else None,
            }
        )
    frame = pd.DataFrame(rows)
    frame["date"] = pd.to_datetime(frame["date"])
    for col in ("weekday", "day", "month"):
        frame[col] = frame[col].astype(np.int8)
    for col in ("days_to_eid", "days_since_eid"):
        frame[col] = frame[col].astype("Int16")
    return frame


def as_float(column: pd.Series) -> np.ndarray:
    """A nullable integer column as floats, with missing values as NaN."""
    return column.astype("Float64").to_numpy(dtype=float, na_value=np.nan)
