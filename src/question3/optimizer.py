"""统一的初始/调整稀疏LP，不接收任何目标日真实未来数据。"""
from dataclasses import dataclass
from functools import lru_cache
import logging
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from ..question2.validator import array_check, require
from . import config as cfg
from .types import HorizonPlan, AdjustmentRevision, readonly
from .rolling_scenario_builder import validate_scenarios
from .validator import validate_lp


@dataclass(frozen=True)
class Index:
    h: int
    s: int = cfg.HISTORY_WINDOW_DAYS

    def grid(self, t): return t
    def charge(self, t): return self.h + t
    def discharge(self, t): return 2 * self.h + t
    def soc(self, t): return 3 * self.h + t
    def emergency(self, s, t): return 4 * self.h + s * self.h + t
    def surplus(self, s, t): return (4 + self.s) * self.h + s * self.h + t
    def up(self, t): return (4 + 2 * self.s) * self.h + t
    def down(self, t): return (5 + 2 * self.s) * self.h + t


@lru_cache(maxsize=16)
def _structure(h, adjustment, s=31, closed=True, contract_slots=None):
    idx = Index(h, s)
    m = h if contract_slots is None else contract_slots
    nrows = idx.s * h + h + int(closed) + (m if adjustment else 0)
    nvars = (4 + 2 * idx.s + (2 if adjustment else 0)) * h
    matrix = lil_matrix((nrows, nvars))
    for s in range(idx.s):
        for t in range(h):
            row = s * h + t
            for col, coefficient in ((idx.grid(t), 1), (idx.charge(t), -1), (idx.discharge(t), 1),
                                     (idx.emergency(s, t), 1), (idx.surplus(s, t), -1)):
                matrix[row, col] = coefficient
    for t in range(h):
        row = idx.s * h + t
        matrix[row, idx.soc(t)] = 1
        matrix[row, idx.charge(t)] = -cfg.ETA_CHARGE
        matrix[row, idx.discharge(t)] = 1 / cfg.ETA_DISCHARGE
        if t:
            matrix[row, idx.soc(t - 1)] = -1
    if closed:
        matrix[idx.s * h + h, idx.soc(h - 1)] = 1
    if adjustment:
        for t in range(m):
            row = idx.s * h + h + int(closed) + t
            matrix[row, idx.grid(t)] = 1
            matrix[row, idx.up(t)] = -1
            matrix[row, idx.down(t)] = 1
    return matrix.tocsr()


def _solve(price, scenarios, initial_soc, old_grid=None, soc_policy="daily_closed", continuation_price=None):
    validate_scenarios(scenarios)
    context = f"{scenarios.target_date} {scenarios.issue_hour}:00"
    array_check(price, (144,), context, "price", True)
    require(np.isfinite(initial_soc) and cfg.SOC_MIN_KWH <= initial_soc <= cfg.SOC_MAX_KWH, context, "invalid boundary SOC")
    start = cfg.ISSUE_SLOT[scenarios.issue_hour]
    closed = soc_policy == "daily_closed"
    if soc_policy not in ("daily_closed", "continuous_lookahead"):
        raise ValueError("unsupported Q3 SOC policy")
    h = 144 - start if closed else 144
    if scenarios.horizon_mode != ("calendar_day" if closed else "issue_relative"):
        raise ValueError("SOC policy and scenario horizon mismatch")
    m = 144-start
    adjustment = old_grid is not None
    if adjustment:
        array_check(old_grid, (m,), context, "old_grid", True)
    idx = Index(h, len(scenarios.probability))
    matrix = _structure(h, adjustment, idx.s, closed, m)
    continuation = price if continuation_price is None else continuation_price
    array_check(continuation, (144,), context, "continuation price", True)
    q = price[start:] if closed else np.r_[price[start:], continuation[:start]]
    objective = np.zeros(matrix.shape[1])
    objective[h:3 * h] = cfg.EPS_THROUGHPUT
    objective[idx.emergency(0, 0):idx.surplus(0, 0)] = (cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * q).ravel()
    if adjustment:
        objective[idx.up(0):idx.up(m)] = cfg.UP_ADJUST_PRICE_MULTIPLIER * q[:m]
        objective[idx.down(0):idx.down(m)] = -cfg.CANCEL_REFUND_MULTIPLIER * q[:m]
        objective[m:h] = q[m:]
    else:
        objective[:h] = q
    rhs = np.r_[scenarios.net_load_kwh.ravel(), initial_soc, np.zeros(h - 1)]
    if closed: rhs = np.r_[rhs, cfg.FINAL_SOC_KWH]
    bounds = ([(0, None)] * h + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * h)
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * h + [(0, None)] * (2 * idx.s * h))
    if adjustment:
        rhs = np.r_[rhs, old_grid]
        bounds += [(0, None)] * m + [(0, 0)] * (h-m)
        bounds += [(0, float(value)) for value in old_grid] + [(0, 0)] * (h-m)
    result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"Question3 optimization failed on {context}: HiGHS status {result.status}: {result.message}")
    grid, charge, discharge, soc = np.split(result.x[:4 * h], 4)
    emergency = result.x[idx.emergency(0, 0):idx.surplus(0, 0)].reshape(idx.s, h)
    surplus = result.x[idx.surplus(0, 0):idx.up(0)].reshape(idx.s, h)
    plan = HorizonPlan(scenarios.target_date, scenarios.issue_hour, float(initial_soc), readonly(grid), readonly(charge),
                       readonly(discharge), readonly(soc), float(result.fun), float(scenarios.probability @ emergency.sum(axis=1)),
                       soc_policy, None if closed else readonly(q))
    revision = None
    if adjustment:
        up, down = readonly(result.x[idx.up(0):idx.up(m)]), readonly(result.x[idx.down(0):idx.down(m)])
        cash = float(cfg.UP_ADJUST_PRICE_MULTIPLIER * q[:m] @ up - cfg.CANCEL_REFUND_MULTIPLIER * q[:m] @ down)
        revision = AdjustmentRevision(scenarios.issue_hour, start, readonly(old_grid), plan, up, down, cash)
    logging.debug("%s optimal %s", context, validate_lp(price, scenarios, plan, emergency, surplus, revision))
    return plan, revision


def solve_initial_plan(price, scenarios, initial_soc_kwh=None, soc_policy="daily_closed", continuation_price=None) -> HorizonPlan:
    if scenarios.issue_hour != 0:
        raise ValueError("initial_optimizer: expected 0:00 issue")
    if initial_soc_kwh is None:
        if soc_policy != "daily_closed":
            raise ValueError("continuous initial plan requires explicit initial_soc_kwh")
        initial_soc_kwh = 6000.0  # compatibility for legacy callers only
    return _solve(price, scenarios, initial_soc_kwh, soc_policy=soc_policy, continuation_price=continuation_price)[0]


def solve_adjustment(price, scenarios, old_grid, current_soc, soc_policy="daily_closed", continuation_price=None) -> AdjustmentRevision:
    if scenarios.issue_hour not in cfg.ISSUE_HOURS[1:]:
        raise ValueError("adjustment_optimizer: expected 6:00, 12:00 or 18:00 issue")
    return _solve(price, scenarios, current_soc, old_grid, soc_policy, continuation_price)[1]
