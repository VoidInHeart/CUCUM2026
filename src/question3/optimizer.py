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
    s: int

    def grid(self, t): return t
    def charge(self, t): return self.h + t
    def discharge(self, t): return 2 * self.h + t
    def soc(self, t): return 3 * self.h + t
    def emergency(self, s, t): return 4 * self.h + s * self.h + t
    def surplus(self, s, t): return (4 + self.s) * self.h + s * self.h + t
    def up(self, t): return (4 + 2 * self.s) * self.h + t
    def down(self, t): return (5 + 2 * self.s) * self.h + t


@lru_cache(maxsize=16)
def _structure(h, scenario_count, adjustment):
    idx = Index(h, scenario_count)
    nrows = idx.s * h + h + 1 + (h if adjustment else 0)
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
    matrix[idx.s * h + h, idx.soc(h - 1)] = 1
    if adjustment:
        for t in range(h):
            row = idx.s * h + h + 1 + t
            matrix[row, idx.grid(t)] = 1
            matrix[row, idx.up(t)] = -1
            matrix[row, idx.down(t)] = 1
    return matrix.tocsr()


def _solve(price, scenarios, initial_soc, old_grid=None):
    validate_scenarios(scenarios)
    context = f"{scenarios.target_date} {scenarios.issue_hour}:00"
    array_check(price, (144,), context, "price", True)
    require(np.isfinite(initial_soc)
            and cfg.SOC_MIN_KWH - cfg.TOL <= initial_soc <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "invalid boundary SOC")
    # 因果MPC的HiGHS解可能在物理边界外留下机器精度级尾差，进入下一版LP前归一化。
    initial_soc = float(np.clip(initial_soc, cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH))
    start = cfg.ISSUE_SLOT[scenarios.issue_hour]
    h = 144 - start
    adjustment = old_grid is not None
    if adjustment:
        array_check(old_grid, (h,), context, "old_grid", True)
    idx = Index(h, len(scenarios.history_dates))
    matrix = _structure(h, idx.s, adjustment)
    q = price[start:]
    objective = np.zeros(matrix.shape[1])
    objective[h:3 * h] = cfg.EPS_THROUGHPUT
    objective[idx.emergency(0, 0):idx.surplus(0, 0)] = (cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * q).ravel()
    if adjustment:
        objective[idx.up(0):idx.down(0)] = cfg.UP_ADJUST_PRICE_MULTIPLIER * q
        objective[idx.down(0):] = -cfg.CANCEL_REFUND_MULTIPLIER * q
    else:
        objective[:h] = q
    rhs = np.r_[scenarios.net_load_kwh.ravel(), initial_soc, np.zeros(h - 1), cfg.FINAL_SOC_KWH]
    bounds = ([(0, None)] * h + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * h)
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * h + [(0, None)] * (2 * idx.s * h))
    if adjustment:
        rhs = np.r_[rhs, old_grid]
        bounds += [(0, None)] * h + [(0, float(value)) for value in old_grid]
    result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"Question3 optimization failed on {context}: HiGHS status {result.status}: {result.message}")
    grid, charge, discharge, soc = np.split(result.x[:4 * h], 4)
    emergency = result.x[idx.emergency(0, 0):idx.surplus(0, 0)].reshape(idx.s, h)
    surplus = result.x[idx.surplus(0, 0):idx.up(0)].reshape(idx.s, h)
    plan = HorizonPlan(scenarios.target_date, scenarios.issue_hour, float(initial_soc), readonly(grid), readonly(charge),
                       readonly(discharge), readonly(soc), float(result.fun), float(scenarios.probability @ emergency.sum(axis=1)))
    revision = None
    if adjustment:
        up, down = readonly(result.x[idx.up(0):idx.down(0)]), readonly(result.x[idx.down(0):])
        cash = float(cfg.UP_ADJUST_PRICE_MULTIPLIER * q @ up - cfg.CANCEL_REFUND_MULTIPLIER * q @ down)
        revision = AdjustmentRevision(scenarios.issue_hour, start, readonly(old_grid), plan, up, down, cash)
    logging.debug("%s optimal %s", context, validate_lp(price, scenarios, plan, emergency, surplus, revision))
    return plan, revision


def solve_initial_plan(price, scenarios) -> HorizonPlan:
    if scenarios.issue_hour != 0:
        raise ValueError("initial_optimizer: expected 0:00 issue")
    return _solve(price, scenarios, cfg.INITIAL_SOC_KWH)[0]


def solve_adjustment(price, scenarios, old_grid, current_soc) -> AdjustmentRevision:
    if scenarios.issue_hour not in cfg.ISSUE_HOURS[1:]:
        raise ValueError("adjustment_optimizer: expected 6:00, 12:00 or 18:00 issue")
    return _solve(price, scenarios, current_soc, old_grid)[1]
