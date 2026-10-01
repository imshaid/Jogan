"""Advisory anomaly flag: unusual excess activity of an agent, from the observed log.

Every feature comes from the observed hourly log (served flows only), using records that had
arrived by ``now``; nothing reads the simulator's truth. Per agent and day:

- ``night_n``: transactions in hours the agent is closed;
- ``volume``: transactions against the agent's own hour-of-day profile over the same arrived
  hours (the last ``history_days`` days), divided by the territory's median that day, so a
  payday or Eid that lifts everyone is not unusual;
- ``ticket``: the mean cash-out against the agent's own mean, divided by the territory's
  median that day;
- ``burst``: the busiest hour's cash-out count against its usual count, ``(n + 1) / (λ + 1)``,
  divided by the territory's median that day.

Only excess counts: ``volume``, ``ticket`` and ``burst`` enter as ``log(max(x, 1))``. A quiet
day is mostly an agent that ran dry (served flows are censored), which the liquidity forecast
already handles. One Isolation Forest (Liu, Ting and Zhou 2008; scikit-learn) per setting
scores these three on the training days. Two rules cover what a forest misses (D-023):

- transactions outside opening hours: zero on nearly every training day, so the forest's
  sub-samples almost never hold a value to split on;
- a feature above the largest value its setting showed in training: a forest scores a point
  past the edge of its training sample like the edge itself.

An agent-day is flagged when a rule fires or when its forest score is above a high quantile
of its setting's training scores. For ranking, a rule hit adds 1 to the forest score (which
lies in (0, 1]), so rule hits come first. A flag never decides anything: it puts the agent's
visit under manual review and lists the agent for a person to look at. The simulator's
injected anomalies (docs/02-data-assumptions.md §8) are used only by :func:`evaluate`.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from jogan.explain.config import Anomaly
from jogan.forecast.panel import Panel

FEATURES = ("night_n", "volume", "ticket", "burst")
FOREST = ("volume", "ticket", "burst")  # the Isolation Forest's inputs; night_n is a rule


@dataclasses.dataclass(frozen=True)
class DayFeatures:
    """Agents by days: the four features, and whether the agent-day can be scored."""

    values: dict[str, np.ndarray]
    valid: np.ndarray

    @property
    def n_days(self) -> int:
        return self.valid.shape[1]

    def matrix(self, rows: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
        """Forest inputs of the given (agent, day) cells: ``log(max(x, 1))``, excess only."""
        a, d = rows
        return np.column_stack([np.log(np.maximum(self.values[k][a, d], 1.0)) for k in FOREST])

    def night(self, day: int) -> np.ndarray:
        return self.values["night_n"][:, day] > 0


def _window(x: np.ndarray, days: int) -> np.ndarray:
    """Sums over the previous ``days`` days (axis 1), excluding the day itself."""
    c = np.concatenate([np.zeros_like(x[:, :1]), np.cumsum(x, axis=1)], axis=1)
    idx = np.arange(x.shape[1])
    return c[:, idx] - c[:, np.maximum(idx - days, 0)]


def _territory_median(x: np.ndarray, ok: np.ndarray, territory: np.ndarray) -> np.ndarray:
    """``x`` divided by the median over the territory's agents that day (where ``ok``)."""
    out = np.full_like(x, np.nan)
    for t in np.unique(territory):
        mine = territory == t
        masked = np.where(ok[mine], x[mine], np.nan)
        with warnings.catch_warnings():  # an all-NaN day has no median
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(masked, axis=0)
        out[mine] = x[mine] / np.where(med > 0, med, np.nan)
    return out


def day_features(
    panel: Panel, agents: pd.DataFrame, cfg: Anomaly, now: int | None = None
) -> DayFeatures:
    """Features of every agent-day from records arrived by hour ``now`` (all when ``None``)."""
    n_agents, n_hours = panel.co_n.shape
    n_days = n_hours // 24
    hours = n_days * 24
    seen = panel.received if now is None else panel.arrive <= now
    shape = (n_agents, n_days, 24)
    avail = seen[:, :hours].reshape(shape)
    count = (panel.co_n + panel.ci_n)[:, :hours].reshape(shape) * avail
    co_n = panel.co_n[:, :hours].reshape(shape) * avail
    co_tk = panel.co_tk[:, :hours].reshape(shape) * avail

    hod = np.arange(24)
    open_h, close_h = agents["open_hour"].to_numpy(), agents["close_hour"].to_numpy()
    is_open = (hod[None, :] >= open_h[:, None]) & (hod[None, :] < close_h[:, None])
    night_n = (count * ~is_open[:, None, :]).sum(axis=2)

    days = cfg.history_days
    seen_h = _window(avail.astype(float), days)  # arrived records per hour of day
    lam = _window(count, days) / np.maximum(seen_h, 1.0)
    lam_co = _window(co_n, days) / np.maximum(seen_h, 1.0)
    history = _window(avail.any(axis=2).astype(float), days)

    expected = (lam * avail).sum(axis=2)
    with np.errstate(all="ignore"):
        volume = np.where(expected > 0, count.sum(axis=2) / expected, np.nan)
        own_ticket = _window(co_tk.sum(axis=2), days) / _window(co_n.sum(axis=2), days)
        ticket = co_tk.sum(axis=2) / co_n.sum(axis=2) / own_ticket
    burst = np.where(avail, (co_n + 1.0) / (lam_co + 1.0), 0.0).max(axis=2)

    arrived = avail.mean(axis=2)
    valid = (arrived >= cfg.min_arrived_share) & (history >= cfg.min_history_days)
    territory = agents["territory"].astype(str).to_numpy()
    volume = _territory_median(volume, valid & np.isfinite(volume), territory)
    ticket = _territory_median(ticket, valid & np.isfinite(ticket), territory)
    burst = _territory_median(burst, valid, territory)
    values = {
        "night_n": night_n,
        # no cash-out or no profile: neither feature says anything unusual
        "volume": np.where(np.isfinite(volume) & (volume > 0), volume, 1.0),
        "ticket": np.where(np.isfinite(ticket) & (ticket > 0), ticket, 1.0),
        "burst": np.where(np.isfinite(burst) & (burst > 0), burst, 1.0),
    }
    return DayFeatures(values, valid)


@dataclasses.dataclass(frozen=True)
class Detector:
    """One Isolation Forest per setting, its flag threshold and its training feature values."""

    cfg: Anomaly
    groups: np.ndarray  # setting of each agent
    models: dict[str, IsolationForest]
    thresholds: dict[str, float]
    reference: dict[str, np.ndarray]  # setting → sorted training values, rows by features

    def forest_scores(self, feats: DayFeatures, day: int) -> tuple[np.ndarray, np.ndarray]:
        """Isolation Forest score of every agent on ``day`` (higher is stranger; NaN if not
        valid), and whether a feature is above its setting's training maximum."""
        score = np.full(len(self.groups), np.nan)
        beyond = np.zeros(len(self.groups), dtype=bool)
        for g, model in self.models.items():
            a = np.flatnonzero((self.groups == g) & feats.valid[:, day])
            if len(a):
                x = feats.matrix((a, np.full(len(a), day)))
                score[a] = -model.score_samples(x)
                beyond[a] = (x > self.reference[g][:, -1]).any(axis=1)
        return score, beyond

    def scores(self, feats: DayFeatures, day: int) -> tuple[np.ndarray, np.ndarray]:
        """Ranking score (rule hits first) and the flag of every agent on ``day``."""
        forest, beyond = self.forest_scores(feats, day)
        ok = np.isfinite(forest)
        rule = ok & (feats.night(day) | beyond)
        threshold = np.array([self.thresholds.get(str(g), np.inf) for g in self.groups])
        flagged = rule | (ok & (np.where(ok, forest, -np.inf) > threshold))
        return forest + rule, flagged

    def flags(self, feats: DayFeatures, day: int, date: dt.date) -> dict[int, dict]:
        """Flagged agents on ``day``: agent index → score and the features behind the flag.

        Listed: transactions outside opening hours if any, and every forest feature above the
        setting's ``threshold_quantile`` of training values (the most extreme first); at least
        one feature.
        """
        score, flagged = self.scores(feats, day)
        out = {}
        for a in np.flatnonzero(flagged):
            g = str(self.groups[a])
            x = feats.matrix((np.array([a]), np.array([day])))[0]
            ref = self.reference[g]
            share = np.array([np.searchsorted(ref[j], x[j], side="right") for j in range(len(x))])
            share = share / ref.shape[1]
            order = np.argsort(-share, kind="stable")
            names = ["night_n"] if feats.night(day)[a] else []
            names += [FOREST[j] for j in order if share[j] >= self.cfg.threshold_quantile]
            names = names or [FOREST[order[0]]]
            out[int(a)] = {
                "date": date.isoformat(),
                "score": round(float(score[a]), 4),
                "items": [
                    {"feature": k, "value": round(float(feats.values[k][a, day]), 2)} for k in names
                ],
            }
        return out


def fit_detector(
    feats: DayFeatures, agents: pd.DataFrame, days: np.ndarray, cfg: Anomaly
) -> Detector:
    """Fit on the valid agent-days among ``days`` (training days only)."""
    groups = agents["setting"].astype(str).to_numpy()
    models, thresholds, reference = {}, {}, {}
    pick = np.zeros_like(feats.valid)
    pick[:, days] = True
    for g in np.unique(groups):
        a, d = np.nonzero(pick & feats.valid & (groups == g)[:, None])
        if len(a) < cfg.max_samples:
            continue
        x = feats.matrix((a, d))
        model = IsolationForest(
            n_estimators=cfg.n_estimators,
            max_samples=cfg.max_samples,
            random_state=cfg.seed,
        ).fit(x)
        models[g] = model
        thresholds[g] = float(np.quantile(-model.score_samples(x), cfg.threshold_quantile))
        reference[g] = np.sort(x, axis=0).T
    return Detector(cfg, groups, models, thresholds, reference)


def _truth(anomalies: pd.DataFrame, agent_ids: list[str], start: dt.date, n_days: int):
    """Agents by days: inside an injected anomaly window; and the windows as index tuples."""
    index = {a: i for i, a in enumerate(agent_ids)}
    truth = np.zeros((len(agent_ids), n_days), dtype=bool)
    windows = []
    for r in anomalies.itertuples(index=False):
        first = (pd.Timestamp(r.first_date).date() - start).days
        last = (pd.Timestamp(r.last_date).date() - start).days
        a = index[str(r.agent_id)]
        truth[a, max(first, 0) : min(last, n_days - 1) + 1] = True
        windows.append((a, first, last, str(r.pattern)))
    return truth, windows


def evaluate(
    panel: Panel,
    agents: pd.DataFrame,
    anomalies: pd.DataFrame,
    start: dt.date,
    train: tuple[dt.date, dt.date],
    test: tuple[dt.date, dt.date],
    cfg: Anomaly,
) -> dict:
    """Fit on the training days, score the test days, compare with the injected anomalies."""
    feats = day_features(panel, agents, cfg)
    train_days = np.arange((train[0] - start).days, (train[1] - start).days + 1)
    test_days = np.arange((test[0] - start).days, (test[1] - start).days + 1)
    det = fit_detector(feats, agents, train_days, cfg)
    ids = agents["agent_id"].astype(str).tolist()
    truth, windows = _truth(anomalies, ids, start, feats.n_days)

    ranked = [det.scores(feats, d) for d in test_days]
    scores = np.column_stack([r[0] for r in ranked])
    flagged = np.column_stack([r[1] for r in ranked])
    hit = truth[:, test_days]
    ok = np.isfinite(scores)
    s, h = scores[ok], hit[ok]
    order = np.argsort(-s, kind="stable")
    precision = {
        str(k): round(float(h[order[:k]].mean()), 4) if len(h) else None for k in cfg.precision_at_k
    }

    in_test = []
    for a, first, last, pattern in windows:
        lo, hi = max(first, test_days[0]), min(last, test_days[-1])
        if lo > hi:
            continue
        cols = np.arange(lo, hi + 1) - test_days[0]
        in_test.append({"pattern": pattern, "detected": bool(flagged[a, cols].any())})
    return {
        "agent_days": int(ok.sum()),
        "anomalous_agent_days": int(h.sum()),
        "base_rate": round(float(h.mean()), 4) if len(h) else 0.0,
        "precision_at_k": precision,
        "flagged": int(flagged.sum()),
        "flagged_true": int((flagged & hit).sum()),
        "windows": len(in_test),
        "windows_detected": sum(w["detected"] for w in in_test),
        "windows_by_pattern": {
            p: [sum(w["detected"] for w in in_test if w["pattern"] == p),
                sum(w["pattern"] == p for w in in_test)]
            for p in sorted({w["pattern"] for w in in_test})
        },
    }  # fmt: skip
