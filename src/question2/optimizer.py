"""计划求解器只接受电价与已截断的历史场景，不访问全年实际数据。"""
from functools import lru_cache
import logging
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from . import config as cfg
from .scenario_builder import validate_scenarios
from .types import DailyPlan, ScenarioSet, readonly
from .validator import array_check, validate_lp

T = cfg.N_SLOTS
S = cfg.HISTORY_WINDOW_DAYS


def idx_grid(t):
    return t


def idx_charge(t):
    return T + t


def idx_discharge(t):
    return 2 * T + t


def idx_soc(t):
    return 3 * T + t


def idx_emergency(s, t):
    return 4 * T + s * T + t


def idx_surplus(s, t):
    return (4 + S) * T + s * T + t


@lru_cache(maxsize=1)
def _structure():
    matrix = lil_matrix((S * T + T + 1, 4 * T + 2 * S * T))
    for s in range(S):
        for t in range(T):
            row = s * T + t
            matrix[row, idx_grid(t)] = 1
            matrix[row, idx_charge(t)] = -1
            matrix[row, idx_discharge(t)] = 1
            matrix[row, idx_emergency(s, t)] = 1
            matrix[row, idx_surplus(s, t)] = -1
    for t in range(T):
        row = S * T + t
        matrix[row, idx_soc(t)] = 1
        matrix[row, idx_charge(t)] = -cfg.ETA_CHARGE
        matrix[row, idx_discharge(t)] = 1 / cfg.ETA_DISCHARGE
        if t:
            matrix[row, idx_soc(t - 1)] = -1
    matrix[-1, idx_soc(T - 1)] = 1
    bounds = ([(0, None)] * T + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * T)
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * T + [(0, None)] * (2 * S * T))
    return matrix.tocsr(), bounds


def solve(price: np.ndarray, scenarios: ScenarioSet) -> DailyPlan:
    validate_scenarios(scenarios)
    array_check(price, (T,), str(scenarios.target_date), "price", True)
    matrix, bounds = _structure()
    objective = np.zeros(4 * T + 2 * S * T)
    objective[:T] = price
    objective[T:3 * T] = cfg.EPS_THROUGHPUT
    objective[4 * T:(4 + S) * T] = (cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * price).ravel()
    rhs = np.r_[scenarios.net_load_kwh.ravel(), cfg.INITIAL_SOC_KWH, np.zeros(T - 1), cfg.FINAL_SOC_KWH]
    result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"Question2 optimization failed on {scenarios.target_date}: HiGHS status {result.status}: {result.message}")
    grid, charge, discharge, soc = np.split(result.x[:4 * T], 4)
    emergency = result.x[4 * T:(4 + S) * T].reshape(S, T)
    surplus = result.x[(4 + S) * T:].reshape(S, T)
    plan = DailyPlan(scenarios.target_date, readonly(grid), readonly(charge), readonly(discharge), readonly(soc),
                     float(scenarios.probability @ emergency.sum(axis=1)), float(result.fun))
    # 在丢弃场景二阶段变量前验证求解器返回的实际矩阵。
    report = validate_lp(price, scenarios, plan, emergency, surplus)
    logging.debug("%s optimal: %s", plan.date, report)
    return plan
