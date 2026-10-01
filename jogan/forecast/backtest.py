"""Time-based backtest of the drain forecast on the status-quo log.

Models train on the training split, conformal shifts come from the calibration split, and
every score is on the test split (D-010); an origin belongs to a split only when its longest
window lies inside it. Ground truth enters only in :func:`evaluate`, passed in explicitly:
the true demand peak (every request, served or not) to measure the censoring bias, and the
live balance at each origin for stock-out probabilities.

Methods compared at every quantile level:

- ``model``: LightGBM quantiles before calibration;
- ``model_cqr``: the same after asymmetric CQR (what Jogan uses);
- ``empirical``: each agent's quantiles of its last same-hour windows (the safety-stock idea);
- ``naive_cqr``: the same window a week earlier, with additive conformal shifts in Tk from
  the calibration split.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

import numpy as np
import pandas as pd

from jogan.forecast.config import SIDES, ForecastConfig, Splits
from jogan.forecast.features import FeatureSet, build_features, origin_grid
from jogan.forecast.model import (
    Calibration,
    QuantileModel,
    calibrate,
    fit_quantiles,
    predict_log,
    stockout_probability,
    to_tk,
)
from jogan.forecast.panel import Panel
from jogan.forecast.targets import Demand, demand_estimate, drain_path, peak_drains, window_any

METHODS = ("model", "model_cqr", "empirical", "naive_cqr")
GROUP_REPORT = ("setting", "size_class")
GROUP_COLUMNS = ("setting", "size_class", "territory")


@dataclasses.dataclass(frozen=True)
class Dataset:
    """Features, split and labels for every origin-agent row (origin-major)."""

    cfg: ForecastConfig
    features: FeatureSet
    split: np.ndarray
    groups: pd.DataFrame
    labels: dict[int, dict[str, np.ndarray]]  # under the configured censoring strategy
    served_labels: dict[int, dict[str, np.ndarray]]  # served flows only (lost records filled)
    censored: dict[int, np.ndarray]  # the window holds an hour in which a side was empty
    demand: Demand

    def rows(self, split: str, horizon: int) -> np.ndarray:
        """Rows of ``split`` used for fitting; ``drop`` removes censored windows from them."""
        pick = self.split == split
        if self.cfg.censoring.strategy == "drop" and split != "test":
            pick &= ~self.censored[horizon]
        return pick


def day_range(start: dt.date, window: tuple[dt.date, dt.date]) -> tuple[int, int]:
    """Day indices ``[d0, d1)`` of an inclusive date window."""
    return (window[0] - start).days, (window[1] - start).days + 1


def split_of_origins(
    origins: np.ndarray, start: dt.date, splits: Splits, cfg: ForecastConfig
) -> np.ndarray:
    """The split each origin belongs to ("" for none): its longest window lies inside it."""
    out = np.full(len(origins), "", dtype=object)
    for name in ("train", "calibration", "test"):
        d0, d1 = day_range(start, getattr(splits, name))
        if name == "train":
            d0 += cfg.warmup_days
        inside = (origins >= d0 * 24) & (origins + cfg.max_horizon <= d1 * 24)
        out[inside] = name
    return out


def _labels(demand: Demand, origins: np.ndarray, cfg: ForecastConfig) -> dict:
    path = drain_path(demand.net, origins, cfg.max_horizon)
    return {
        h: {s: v.T.ravel() for s, v in peak_drains(path, h).items()} for h in cfg.horizons_hours
    }


def build_dataset(
    panel: Panel,
    calendar: pd.DataFrame,
    agents: pd.DataFrame,
    cfg: ForecastConfig,
    splits: Splits,
    start: dt.date,
) -> Dataset:
    """Everything the backtest needs from the observed log and the public tables."""
    n_days = panel.n_hours // 24
    origins = origin_grid(n_days, cfg.origin_hours, cfg.max_horizon)
    features = build_features(panel, calendar, agents, cfg, origins)
    split = np.repeat(split_of_origins(origins, start, splits, cfg), panel.n_agents)
    territory = pd.Categorical(agents["territory"]).codes.astype(np.int64)
    train_days = day_range(start, splits.train)
    demand = demand_estimate(panel, cfg.censoring, train_days, territory)
    served = demand_estimate(
        panel, cfg.censoring.model_copy(update={"strategy": "ignore"}), train_days, territory
    )
    groups = pd.DataFrame(
        {c: np.tile(agents[c].astype(str).to_numpy(), len(origins)) for c in GROUP_COLUMNS}
    )
    censored = {h: window_any(demand.censored, origins, h).T.ravel() for h in cfg.horizons_hours}
    return Dataset(
        cfg=cfg,
        features=features,
        split=split,
        groups=groups,
        labels=_labels(demand, origins, cfg),
        served_labels=_labels(served, origins, cfg),
        censored=censored,
        demand=demand,
    )


@dataclasses.dataclass(frozen=True)
class Forecaster:
    """Calibrated quantile models per (horizon, side), plus the naive baseline's shifts."""

    cfg: ForecastConfig
    models: dict[tuple[int, str], QuantileModel]
    naive: dict[tuple[int, str], Calibration]


def _repeat(point: np.ndarray, n_levels: int) -> np.ndarray:
    return np.repeat(point[:, None], n_levels, axis=1)


def fit_forecaster(ds: Dataset) -> Forecaster:
    """Train on the training split and calibrate on the calibration split, per horizon/side."""
    cfg = ds.cfg
    levels = cfg.quantiles
    models, naive = {}, {}
    for h in cfg.horizons_hours:
        x = ds.features.matrix(h)
        train, cal = ds.rows("train", h), ds.rows("calibration", h)
        for side in SIDES:
            y = ds.labels[h][side]
            boosters = fit_quantiles(x[train], y[train], levels, cfg.lightgbm)
            log_cal = predict_log(boosters, x[cal])
            calib = calibrate(log_cal, np.log1p(y[cal]), ds.groups[cal], levels, cfg.conformal)
            models[h, side] = QuantileModel(h, side, levels, boosters, calib)
            point = ds.features.naive[h][side]
            ok = cal & np.isfinite(point)
            # additive shifts in Tk: a zero last week would make log-space shifts explode
            naive[h, side] = calibrate(
                _repeat(point[ok], len(levels)), y[ok], ds.groups[ok], levels, cfg.conformal
            )
    return Forecaster(cfg, models, naive)


def predict_all(
    ds: Dataset, fc: Forecaster, pick: np.ndarray
) -> dict[tuple[int, str], dict[str, np.ndarray]]:
    """Quantiles in Tk of every method on the rows ``pick``."""
    out = {}
    levels = ds.cfg.quantiles
    groups = ds.groups[pick]
    for h in ds.cfg.horizons_hours:
        x = ds.features.matrix(h)[pick]
        for side in SIDES:
            model = fc.models[h, side]
            log_q = predict_log(model.boosters, x)
            point = ds.features.naive[h][side][pick]
            naive = fc.naive[h, side].apply(_repeat(point, len(levels)), groups)
            naive = np.maximum(np.sort(naive, axis=1), 0.0)
            out[h, side] = {
                "model": to_tk(log_q),
                "model_cqr": to_tk(model.calibration.apply(log_q, groups)),
                "empirical": ds.features.empirical[h][side][pick],
                "naive_cqr": naive,
            }
    return out


# --- Evaluation ------------------------------------------------------------------------------


def pinball(y: np.ndarray, q: np.ndarray, levels: tuple[float, ...]) -> np.ndarray:
    """Mean pinball loss per level (Tk)."""
    diff = y[:, None] - q
    tau = np.asarray(levels)[None, :]
    return np.maximum(tau * diff, (tau - 1) * diff).mean(axis=0)


def _r(x: float, digits: int = 4) -> float:
    return round(float(x), digits)


def _by_level(values: np.ndarray, levels: tuple[float, ...], digits: int = 4) -> dict:
    return {str(q): _r(v, digits) for q, v in zip(levels, values, strict=True)}


def _intervals(y: np.ndarray, q: np.ndarray, cfg: ForecastConfig) -> dict:
    levels = list(cfg.quantiles)
    out = {}
    for lo, hi in cfg.intervals():
        a, b = q[:, levels.index(lo)], q[:, levels.index(hi)]
        out[f"{round(100 * (hi - lo))}"] = {
            "coverage": _r(((y >= a) & (y <= b)).mean()),
            "mean_width_tk": _r((b - a).mean(), 1),
        }
    return out


def _reliability(p: np.ndarray, event: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    out = []
    for b in range(bins):
        pick = which == b
        if pick.any():
            out.append(
                {
                    "bin": [_r(edges[b], 2), _r(edges[b + 1], 2)],
                    "rows": int(pick.sum()),
                    "mean_p": _r(p[pick].mean()),
                    "observed": _r(event[pick].mean()),
                }
            )
    return out


def truth_panels(frame: pd.DataFrame, agent_ids: list[str], start: dt.date, n_hours: int) -> dict:
    """Agents-by-hours arrays from ``truth/hourly.parquet`` (evaluation only)."""
    agent = pd.Categorical(frame["agent_id"].astype(str), categories=agent_ids).codes
    origin = np.datetime64(start, "s")
    hour = (frame["ts"].to_numpy().astype("datetime64[s]") - origin).astype(np.int64) // 3600
    out = {}
    for name in ("req_co_tk", "req_ci_tk", "lost_co_n", "lost_ci_n", "cash_tk", "efloat_tk"):
        arr = np.zeros((len(agent_ids), n_hours))
        arr[agent, hour] = frame[name].to_numpy(dtype=float)
        out[name] = arr
    return out


def _flag_quality(flag: np.ndarray, lost: np.ndarray, asked: np.ndarray) -> dict:
    """Flags scored over the hours in which customers asked for that side."""
    flag, lost = flag[asked], lost[asked]
    hit = (flag & lost).sum()
    return {
        "hours": int(asked.sum()),
        "flagged_share": _r(flag.mean()),
        "precision": _r(hit / max(flag.sum(), 1)),
        "recall": _r(hit / max(lost.sum(), 1)),
    }


def _bias(est: np.ndarray, truth: np.ndarray) -> dict:
    return {
        "mean_tk": _r((est - truth).mean(), 1),
        "relative": _r((est - truth).mean() / max(truth.mean(), 1e-9)),
    }


def censoring_report(ds: Dataset, truth: dict, true_labels: dict) -> dict:
    """How well the stock-out flags find hours with lost requests, and the label bias."""
    lost_co, lost_ci = truth["lost_co_n"] > 0, truth["lost_ci_n"] > 0
    out: dict[str, Any] = {
        "strategy": ds.cfg.censoring.strategy,
        "flags": {
            "cash": _flag_quality(ds.demand.censored_co, lost_co, truth["req_co_tk"] > 0),
            "efloat": _flag_quality(ds.demand.censored_ci, lost_ci, truth["req_ci_tk"] > 0),
        },
        "label_bias": {},
    }
    origins = ds.features.origins
    any_lost = {
        h: window_any(lost_co | lost_ci, origins, h).T.ravel() for h in ds.cfg.horizons_hours
    }
    scored = ds.split != ""
    for h in ds.cfg.horizons_hours:
        for side in SIDES:
            t = true_labels[h][side]
            entry = {}
            for name, pick in (
                ("all", scored),
                ("with_lost", scored & any_lost[h]),
                ("without_lost", scored & ~any_lost[h]),
            ):
                entry[name] = {
                    "rows": int(pick.sum()),
                    "served": _bias(ds.served_labels[h][side][pick], t[pick]),
                    "estimated": _bias(ds.labels[h][side][pick], t[pick]),
                }
            out["label_bias"].setdefault(side, {})[str(h)] = entry
    return out


def _period(ds: Dataset, pick: np.ndarray) -> np.ndarray:
    """``eid`` for rows from ten days before an Eid to three days after, else ``other``."""
    base = ds.features.base
    to = base["days_to_eid"].to_numpy()[pick]
    since = base["days_since_eid"].to_numpy()[pick]
    near = (np.nan_to_num(to, nan=99) <= 10) | (np.nan_to_num(since, nan=99) <= 3)
    return np.where(near, "eid", "other")


def evaluate(ds: Dataset, fc: Forecaster, truth: dict) -> dict:
    """Scores on the test split against estimated labels and against true demand."""
    cfg, levels = ds.cfg, ds.cfg.quantiles
    origins = ds.features.origins
    true_net = truth["req_co_tk"] - truth["req_ci_tk"]
    true_labels = _labels(
        Demand(
            co=truth["req_co_tk"],
            ci=truth["req_ci_tk"],
            censored_co=np.zeros(true_net.shape, dtype=bool),
            censored_ci=np.zeros(true_net.shape, dtype=bool),
            expected_co=truth["req_co_tk"],
            expected_ci=truth["req_ci_tk"],
        ),
        origins,
        cfg,
    )
    test = ds.split == "test"
    preds = predict_all(ds, fc, test)
    period = _period(ds, test)
    # live balance at each origin: the ledger's hour-end balance of the hour before
    row_o, row_a = ds.features.origin_of_row[test], ds.features.agent_of_row[test]
    balance = {
        "cash": truth["cash_tk"][row_a, row_o - 1],
        "efloat": truth["efloat_tk"][row_a, row_o - 1],
    }
    report: dict[str, Any] = {}
    for h in cfg.horizons_hours:
        for side in SIDES:
            p = preds[h, side]
            ok = np.all([np.isfinite(q).all(axis=1) for q in p.values()], axis=0)
            y_obs = ds.labels[h][side][test][ok]
            y_true = true_labels[h][side][test][ok]
            entry: dict[str, Any] = {"rows": int(ok.sum()), "methods": {}}
            for name in METHODS:
                q = p[name][ok]
                entry["methods"][name] = {
                    "pinball_obs": _r(pinball(y_obs, q, levels).mean(), 2),
                    "pinball_truth": _r(pinball(y_true, q, levels).mean(), 2),
                    "pinball_truth_by_level": _by_level(pinball(y_true, q, levels), levels, 2),
                    "coverage_obs": _by_level((y_obs[:, None] <= q).mean(axis=0), levels),
                    "coverage_truth": _by_level((y_true[:, None] <= q).mean(axis=0), levels),
                }
            q = p["model_cqr"][ok]
            entry["intervals"] = {
                "obs": _intervals(y_obs, q, cfg),
                "truth": _intervals(y_true, q, cfg),
            }
            g = ds.groups[test][ok]
            entry["groups"] = {}
            for col in GROUP_REPORT:
                entry["groups"][col] = {}
                for value in sorted(g[col].unique()):
                    m = (g[col] == value).to_numpy()
                    entry["groups"][col][value] = {
                        "rows": int(m.sum()),
                        "coverage_truth": _by_level((y_true[m, None] <= q[m]).mean(axis=0), levels),
                        "intervals_truth": _intervals(y_true[m], q[m], cfg),
                    }
            entry["periods"] = {}
            for name in ("eid", "other"):
                m = period[ok] == name
                if m.any():
                    entry["periods"][name] = {
                        "rows": int(m.sum()),
                        "pinball_truth": {
                            k: _r(pinball(y_true[m], p[k][ok][m], levels).mean(), 2)
                            for k in METHODS
                        },
                        "intervals_truth": _intervals(y_true[m], q[m], cfg),
                    }
            b = balance[side][ok]
            event = y_true > b  # stock-out within the window if no one tops the agent up
            entry["stockout"] = {"base_rate": _r(event.mean())}
            for name in ("model_cqr", "empirical"):
                prob = stockout_probability(p[name][ok], levels, b)
                entry["stockout"][name] = {"brier": _r(((prob - event) ** 2).mean())}
            prob = stockout_probability(q, levels, b)
            entry["stockout"]["reliability"] = _reliability(prob, event)
            report.setdefault(side, {})[str(h)] = entry
    return {"forecast": report, "censoring": censoring_report(ds, truth, true_labels)}
