"""计划求解器只接受电价与已截断的历史场景，不访问全年实际数据。"""
from functools import lru_cache
import logging
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix, hstack, csr_matrix

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


@lru_cache(maxsize=8)
def _continuous_structure(h, s):
    matrix = lil_matrix((s * h + h, (4 + 2 * s) * h))
    for scenario in range(s):
        for t in range(h):
            row = scenario * h + t
            for col, value in ((t, 1), (h+t, -1), (2*h+t, 1),
                               (4*h+row, 1), ((4+s)*h+row, -1)):
                matrix[row, col] = value
    for t in range(h):
        row = s*h+t
        matrix[row, 3*h+t] = 1
        matrix[row, h+t] = -cfg.ETA_CHARGE
        matrix[row, 2*h+t] = 1/cfg.ETA_DISCHARGE
        if t:
            matrix[row, 3*h+t-1] = -1
    bounds = ([(0, None)]*h + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)]*(2*h)
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)]*h + [(0, None)]*(2*s*h))
    return matrix.tocsr(), bounds


def solve(price: np.ndarray, scenarios: ScenarioSet, initial_soc_kwh=None,
          soc_policy="daily_closed", risk_weight=0.0, risk_alpha=0.95) -> DailyPlan:
    if not np.isfinite(risk_weight) or risk_weight < 0 or not 0 < risk_alpha < 1:
        raise ValueError("invalid CVaR parameters")
    if soc_policy not in cfg.SOC_POLICIES:
        raise ValueError(f"unknown SOC policy: {soc_policy}")
    if initial_soc_kwh is None:
        if soc_policy != "daily_closed":
            raise ValueError("continuous solver requires explicit initial_soc_kwh")
        initial_soc_kwh = cfg.CONTROL_START_SOC_KWH
    if not np.isfinite(initial_soc_kwh) or not cfg.SOC_MIN_KWH <= initial_soc_kwh <= cfg.SOC_MAX_KWH:
        raise ValueError("initial SOC outside physical bounds")
    if soc_policy == "daily_closed" and initial_soc_kwh != cfg.CONTROL_START_SOC_KWH:
        raise ValueError("daily_closed requires reference initial SOC")
    validate_scenarios(scenarios)
    s, h = scenarios.net_load_kwh.shape
    if h != (288 if soc_policy == "continuous_lookahead" else 144):
        raise ValueError("scenario horizon differs from SOC policy")
    array_check(price, (h,), str(scenarios.target_date), "price", True)
    matrix, bounds = _structure() if soc_policy == "daily_closed" else _continuous_structure(h, s)
    objective = np.zeros(4 * h + 2 * s * h)
    objective[:h] = price
    objective[h:3 * h] = cfg.EPS_THROUGHPUT
    objective[4 * h:(4 + s) * h] = (cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * price).ravel()
    rhs = np.r_[scenarios.net_load_kwh.ravel(), initial_soc_kwh, np.zeros(h - 1)]
    if soc_policy == "daily_closed":
        rhs = np.r_[rhs, cfg.FINAL_SOC_KWH]
    risk_matrix = risk_rhs = None
    base_vars = len(objective)
    if risk_weight:
        # CVaR of scenario emergency expense; common plan expense already in expectation.
        matrix = hstack((matrix, csr_matrix((matrix.shape[0], 1+s))), format="csr")
        risk_matrix = lil_matrix((s, base_vars+1+s))
        for scenario in range(s):
            risk_matrix[scenario, 4*h+scenario*h:4*h+(scenario+1)*h] = cfg.EMERGENCY_PRICE_MULTIPLIER*price
            risk_matrix[scenario, base_vars] = -1
            risk_matrix[scenario, base_vars+1+scenario] = -1
        risk_matrix = risk_matrix.tocsr()
        risk_rhs = np.zeros(s)
        objective = np.r_[objective, risk_weight, risk_weight*scenarios.probability/(1-risk_alpha)]
        bounds = list(bounds) + [(None, None)] + [(0,None)]*s
    result = linprog(objective, A_eq=matrix, b_eq=rhs, A_ub=risk_matrix, b_ub=risk_rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"Question2 optimization failed on {scenarios.target_date}: HiGHS status {result.status}: {result.message}")
    grid, charge, discharge, soc = np.split(result.x[:4 * h], 4)
    emergency = result.x[4 * h:(4 + s) * h].reshape(s, h)
    surplus = result.x[(4 + s) * h:base_vars].reshape(s, h)
    risk_penalty = float(objective[base_vars:] @ result.x[base_vars:])
    plan = DailyPlan(scenarios.target_date, readonly(grid), readonly(charge), readonly(discharge), readonly(soc),
                     float(scenarios.probability @ emergency.sum(axis=1)), float(result.fun),
                     float(initial_soc_kwh), soc_policy, risk_weight, risk_alpha, risk_penalty)
    # 在丢弃场景二阶段变量前验证求解器返回的实际矩阵。
    report = validate_lp(price, scenarios, plan, emergency, surplus)
    logging.debug("%s optimal: %s", plan.date, report)
    return plan
