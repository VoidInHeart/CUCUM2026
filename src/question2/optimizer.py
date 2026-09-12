"""计划求解器只接受电价与已截断的历史场景，不访问全年实际数据。"""
from functools import lru_cache
import logging
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from . import config as cfg
from .scenario_builder import validate_scenarios
from .types import DailyPlan, ScenarioSet, readonly
from .validator import array_check, validate_grid_recourse_lp, validate_lp

T = cfg.N_SLOTS


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


def idx_surplus(s, t, scenario_count):
    return (4 + scenario_count) * T + s * T + t


@lru_cache(maxsize=cfg.HISTORY_WINDOW_DAYS)
def _structure(scenario_count):
    matrix = lil_matrix((scenario_count * T + T + 1, 4 * T + 2 * scenario_count * T))
    for s in range(scenario_count):
        for t in range(T):
            row = s * T + t
            matrix[row, idx_grid(t)] = 1
            matrix[row, idx_charge(t)] = -1
            matrix[row, idx_discharge(t)] = 1
            matrix[row, idx_emergency(s, t)] = 1
            matrix[row, idx_surplus(s, t, scenario_count)] = -1
    for t in range(T):
        row = scenario_count * T + t
        matrix[row, idx_soc(t)] = 1
        matrix[row, idx_charge(t)] = -cfg.ETA_CHARGE
        matrix[row, idx_discharge(t)] = 1 / cfg.ETA_DISCHARGE
        if t:
            matrix[row, idx_soc(t - 1)] = -1
    matrix[-1, idx_soc(T - 1)] = 1
    bounds = ([(0, None)] * T + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * T)
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * T
              + [(0, None)] * (2 * scenario_count * T))
    return matrix.tocsr(), bounds


def solve(price: np.ndarray, scenarios: ScenarioSet) -> DailyPlan:
    validate_scenarios(scenarios)
    array_check(price, (T,), str(scenarios.target_date), "price", True)
    scenario_count = len(scenarios.history_dates)
    matrix, bounds = _structure(scenario_count)
    objective = np.zeros(4 * T + 2 * scenario_count * T)
    objective[:T] = price
    objective[T:3 * T] = cfg.EPS_THROUGHPUT
    objective[4 * T:(4 + scenario_count) * T] = (
        cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * price
    ).ravel()
    rhs = np.r_[scenarios.net_load_kwh.ravel(), cfg.INITIAL_SOC_KWH, np.zeros(T - 1), cfg.FINAL_SOC_KWH]
    result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"Question2 optimization failed on {scenarios.target_date}: HiGHS status {result.status}: {result.message}")
    grid, charge, discharge, soc = np.split(result.x[:4 * T], 4)
    emergency = result.x[4 * T:(4 + scenario_count) * T].reshape(scenario_count, T)
    surplus = result.x[(4 + scenario_count) * T:].reshape(scenario_count, T)
    plan = DailyPlan(scenarios.target_date, readonly(grid), readonly(charge), readonly(discharge), readonly(soc),
                     float(scenarios.probability @ emergency.sum(axis=1)), float(result.fun))
    # 在丢弃场景二阶段变量前验证求解器返回的实际矩阵。
    report = validate_lp(price, scenarios, plan, emergency, surplus)
    logging.debug("%s optimal: %s", plan.date, report)
    return plan


@lru_cache(maxsize=cfg.HISTORY_WINDOW_DAYS)
def _grid_recourse_structure(scenario_count):
    """仅grid为一阶段变量；每个场景拥有独立储能、SOC、紧急电和富余量。"""
    fields = 5
    matrix = lil_matrix((2 * scenario_count * T + scenario_count,
                         T + fields * scenario_count * T))

    def index(scenario, field, slot):
        return T + (scenario * fields + field) * T + slot

    for scenario in range(scenario_count):
        for slot in range(T):
            row = scenario * T + slot
            matrix[row, idx_grid(slot)] = 1
            matrix[row, index(scenario, 0, slot)] = -1
            matrix[row, index(scenario, 1, slot)] = 1
            matrix[row, index(scenario, 3, slot)] = 1
            matrix[row, index(scenario, 4, slot)] = -1

            row = scenario_count * T + scenario * T + slot
            matrix[row, index(scenario, 2, slot)] = 1
            matrix[row, index(scenario, 0, slot)] = -cfg.ETA_CHARGE
            matrix[row, index(scenario, 1, slot)] = 1 / cfg.ETA_DISCHARGE
            if slot:
                matrix[row, index(scenario, 2, slot - 1)] = -1
        matrix[2 * scenario_count * T + scenario, index(scenario, 2, T - 1)] = 1

    scenario_bounds = (
        [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * T)
        + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * T
        + [(0, None)] * (2 * T)
    )
    return matrix.tocsr(), [(0, None)] * T + scenario_bounds * scenario_count


def solve_grid_first_stage_storage_recourse(price: np.ndarray, scenarios: ScenarioSet) -> DailyPlan:
    """求一阶段购电合同；返回最高权重场景轨迹仅作为因果MPC的0:00未来基准。"""
    validate_scenarios(scenarios)
    array_check(price, (T,), str(scenarios.target_date), "price", True)
    scenario_count = len(scenarios.history_dates)
    matrix, bounds = _grid_recourse_structure(scenario_count)
    objective = np.zeros(matrix.shape[1])
    objective[:T] = price
    for scenario, probability in enumerate(scenarios.probability):
        base = T + scenario * 5 * T
        objective[base:base + 2 * T] = cfg.RECOURSE_EPS_THROUGHPUT * probability
        objective[base + 3 * T:base + 4 * T] = (
            cfg.EMERGENCY_PRICE_MULTIPLIER * probability * price
        )
    soc_rhs = np.tile(np.r_[cfg.INITIAL_SOC_KWH, np.zeros(T - 1)], scenario_count)
    rhs = np.r_[scenarios.net_load_kwh.ravel(), soc_rhs,
                np.full(scenario_count, cfg.FINAL_SOC_KWH)]
    result = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(
            f"Question2 grid-recourse optimization failed on {scenarios.target_date}: "
            f"HiGHS status {result.status}: {result.message}"
        )
    grid = result.x[:T]
    recourse = result.x[T:].reshape(scenario_count, 5, T)
    charge, discharge, soc, emergency, surplus = (recourse[:, field, :] for field in range(5))
    reference = int(np.argmax(scenarios.probability))
    plan = DailyPlan(
        scenarios.target_date,
        readonly(grid),
        readonly(charge[reference]),
        readonly(discharge[reference]),
        readonly(soc[reference]),
        float(scenarios.probability @ emergency.sum(axis=1)),
        float(result.fun),
    )
    report = validate_grid_recourse_lp(
        price, scenarios, plan, charge, discharge, soc, emergency, surplus, reference
    )
    logging.debug("%s grid-first-stage optimal: %s", plan.date, report)
    return plan
