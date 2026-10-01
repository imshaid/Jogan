"""Jogan's policy: forecast → newsvendor level → value of a visit → runner assignment (D-021).

At the plan hour Jogan builds the forecast features from the observed history exactly as the
backtest does (:func:`~jogan.forecast.panel.panel_from_history`, tested equal to the log),
predicts calibrated quantiles of the peak drain of each side over the horizon, and sets a
newsvendor target cash level per agent (:mod:`jogan.plan.newsvendor`). An agent is a candidate
when the expected shortage cost a visit avoids exceeds the runner time of a stop; the program
in :mod:`jogan.plan.dispatch` (or, for the ablation, M3's greedy round) picks the visits. Calls
are answered exactly as under every other policy.

Live balances enter only here, in the levels and the value of a visit, never in the forecast
(D-020). Each plan's evidence per agent is kept in :attr:`Jogan.last` for the decision trace.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from jogan.forecast.backtest import GROUP_COLUMNS, Forecaster
from jogan.forecast.features import build_features
from jogan.forecast.model import stockout_probability
from jogan.forecast.panel import Panel, panel_from_history
from jogan.ops.costs import commission_rate, fuel_tk_per_km, labour_tk_per_minute
from jogan.ops.env import Context, Observation
from jogan.ops.fleet import Visit
from jogan.ops.metrics import HOURS_PER_YEAR
from jogan.ops.policies import Planned, balanced_target
from jogan.plan.config import PlanConfig, load_plan_config
from jogan.plan.dispatch import SolveLog, milp_rounds
from jogan.plan.newsvendor import exceedance, shortage_cost, target_cash

EVIDENCE_LEVELS = (0.5, 0.9, 0.99)  # quantiles kept in the decision trace


class Jogan(Planned):
    name = "jogan"

    def __init__(self, forecaster: Forecaster, cfg: PlanConfig | None = None) -> None:
        self.cfg = cfg or load_plan_config()
        self.forecaster = forecaster
        if self.cfg.horizon_hours not in forecaster.cfg.horizons_hours:
            raise ValueError(f"no forecast for a {self.cfg.horizon_hours}-hour horizon")
        self.log = SolveLog()
        self.last: pd.DataFrame | None = None
        self.last_inputs: tuple[Panel, pd.DataFrame] | None = None  # panel and features

    def reset(self, ctx: Context) -> None:
        super().reset(ctx)
        costs = ctx.ops.costs
        rate = commission_rate(costs)
        self.rate = (rate["CO"], rate["CI"])
        self.labour = labour_tk_per_minute(costs)
        self.overage = costs.idle.rate_per_year * self.cfg.horizon_hours / HOURS_PER_YEAR
        self.stop_floor = ctx.config.runners.visit_minutes * self.labour
        self.groups = ctx.agents[list(GROUP_COLUMNS)].astype(str).reset_index(drop=True)
        setting_of = dict(
            zip(ctx.territories["territory"], ctx.territories["setting"], strict=True)
        )
        self.runner_setting = ctx.runners["territory"].map(setting_of).to_numpy()
        self.dates = ctx.calendar["date"].dt.date.tolist()
        # one runner of each agent's territory: its speed today and its fuel price
        runner_territory = ctx.runners["territory"].to_numpy()
        first = {t: int(np.flatnonzero(runner_territory == t)[0]) for t in set(runner_territory)}
        self.agent_runner = ctx.agents["territory"].map(first).to_numpy(dtype=int)
        self.log = SolveLog()
        self.last = None
        self.last_inputs = None

    def fuel_per_km(self, day: int) -> np.ndarray:
        """Fuel Tk per km for each runner on ``day`` (petrol price on the date, its setting)."""
        out = np.empty(len(self.runner_setting))
        for setting in np.unique(self.runner_setting):
            mine = self.runner_setting == setting
            out[mine] = fuel_tk_per_km(self.ctx.ops.costs, [self.dates[day]], setting)[0]
        return out

    def call_cost(self, obs: Observation, fuel: np.ndarray) -> np.ndarray:
        """Known cost of a separate trip from the hub to each agent and back, at today's speed."""
        fleet, net = obs.fleet, self.ctx.network
        speed = np.array(fleet.speed)[self.agent_runner]
        km = 2 * np.array(net.hub_km)
        minutes = km / speed * 60 + self.ctx.config.runners.visit_minutes
        return km * fuel[self.agent_runner] + minutes * self.labour

    def tickets(self, obs: Observation) -> tuple[np.ndarray, np.ndarray]:
        """Mean served ticket per side over the recent observed days (pooled where none)."""
        days = min(self.params.typical.history_days, obs.day)
        h0, h1 = obs.hour - 24 * max(days, 1), obs.hour
        hist = obs.history
        ok = hist.available(obs.hour, max(h0, 0), h1)
        out = []
        for n, tk in ((hist.co_n, hist.co_tk), (hist.ci_n, hist.ci_tk)):
            count = (n[:, max(h0, 0) : h1] * ok).sum(axis=1).astype(float)
            amount = (tk[:, max(h0, 0) : h1] * ok).sum(axis=1).astype(float)
            pooled = amount.sum() / count.sum() if count.sum() > 0 else 1.0
            out.append(np.where(count > 0, amount / np.maximum(count, 1.0), pooled))
        return out[0], out[1]

    def plan(self, obs: Observation) -> list[Visit]:
        ctx, cfg, h = self.ctx, self.cfg, self.cfg.horizon_hours
        fcfg = self.forecaster.cfg
        levels = fcfg.quantiles
        panel = panel_from_history(obs.history)
        x = build_features(panel, ctx.calendar, ctx.agents, fcfg, np.array([obs.hour])).matrix(h)
        self.last_inputs = (panel, x)
        q_cash = self.forecaster.models[h, "cash"].predict(x, self.groups)
        q_efloat = self.forecaster.models[h, "efloat"].predict(x, self.groups)

        ticket_co, ticket_ci = self.tickets(obs)
        value_tk = cfg.lost_customer_value_tk
        under_c = self.rate[0] + value_tk / ticket_co
        under_e = self.rate[1] + value_tk / ticket_ci
        cash, efloat = obs.cash_est.astype(float), obs.efloat.astype(float)
        total = cash + efloat
        typ_co, typ_ci = self.typical(obs)
        typical = cfg.newsvendor.split == "typical"
        level = target_cash(
            q_cash,
            q_efloat,
            levels,
            total,
            under_c,
            under_e,
            self.overage,
            fallback=balanced_target(obs, typ_co, typ_ci) if typical else None,
            iterations=cfg.newsvendor.split_iterations,
        )
        target = level["target"]
        points = cfg.newsvendor.integration_points
        now = shortage_cost(q_cash, q_efloat, levels, cash, efloat, under_c, under_e, points)
        then = shortage_cost(
            q_cash, q_efloat, levels, target, total - target, under_c, under_e, points
        )
        # an agent left to drift below the call level calls, and a runner makes a separate trip
        call_c, call_e = self.params.calls.call_days * typ_co, self.params.calls.call_days * typ_ci

        def p_call(c: np.ndarray, e: np.ndarray) -> np.ndarray:
            return np.maximum(
                exceedance(q_cash, levels, c - call_c), exceedance(q_efloat, levels, e - call_e)
            )

        fuel = self.fuel_per_km(obs.day)
        call_tk = self.call_cost(obs, fuel)
        value = now - then + (p_call(cash, efloat) - p_call(target, total - target)) * call_tk
        candidate = ~obs.pending & (value > self.stop_floor)
        ranked = [int(a) for a in np.flatnonzero(candidate)[np.argsort(-value[candidate])]]

        def goal(a: int, _: int) -> float:
            return float(target[a])

        if cfg.dispatch == "greedy":
            visits = self.rounds(obs, ranked, goal)
        else:
            visits = milp_rounds(
                ranked,
                value,
                obs.fleet,
                obs.t,
                goal,
                fuel,
                self.labour,
                self.params.call_reserve_visits,
                cfg.milp,
                self.log,
            )

        runner_ids = ctx.runners["runner_id"].to_numpy()
        sent = np.full(len(total), None, dtype=object)
        for v in visits:
            sent[v.agent] = runner_ids[v.runner]
        evidence = {
            "agent_id": ctx.agents["agent_id"].to_numpy(),
            "cash_tk": cash,
            "efloat_tk": efloat,
            "p_stockout_cash": stockout_probability(q_cash, levels, cash),
            "p_stockout_efloat": stockout_probability(q_efloat, levels, efloat),
        }
        for side, q in (("cash", q_cash), ("efloat", q_efloat)):
            for lv in EVIDENCE_LEVELS:
                if lv in levels:
                    evidence[f"drain_{side}_q{round(lv * 100)}"] = q[:, levels.index(lv)]
        self.last = pd.DataFrame(
            {
                **evidence,
                "need_cash_tk": level["need_cash"],
                "need_efloat_tk": level["need_efloat"],
                "needs_fit": level["fits"],
                "target_cash_tk": target,
                "value_tk": value,
                "candidate": candidate,
                "runner_id": sent,
            }
        ).assign(hour=obs.hour)
        return visits
