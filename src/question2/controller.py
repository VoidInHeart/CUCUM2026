"""固定0:00购电合同下的逐10分钟因果储能MPC。"""
from dataclasses import dataclass
from functools import lru_cache
import logging

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from . import config as cfg
from .scenario_builder import validate_scenarios
from .types import DailyPlan, ScenarioSet, readonly
from .validator import array_check, require


@dataclass(frozen=True)
class BatteryExecution:
    """当天实际执行的储能轨迹；购电合同不属于可调整变量。"""

    charge_kwh: np.ndarray
    discharge_kwh: np.ndarray
    soc_end_kwh: np.ndarray


@lru_cache(maxsize=cfg.N_SLOTS)
def _structure(horizon: int):
    """固定合同MPC：充、放、SOC、紧急购电、富余电量。"""
    charge = 0
    discharge = horizon
    soc = 2 * horizon
    emergency = 3 * horizon
    surplus = 4 * horizon
    matrix = lil_matrix((2 * horizon + 1, 5 * horizon))
    for slot in range(horizon):
        matrix[slot, charge + slot] = -1
        matrix[slot, discharge + slot] = 1
        matrix[slot, emergency + slot] = 1
        matrix[slot, surplus + slot] = -1
        row = horizon + slot
        matrix[row, soc + slot] = 1
        matrix[row, charge + slot] = -cfg.ETA_CHARGE
        matrix[row, discharge + slot] = 1 / cfg.ETA_DISCHARGE
        if slot:
            matrix[row, soc + slot - 1] = -1
    matrix[-1, soc + horizon - 1] = 1
    bounds = (
        [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * horizon)
        + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * horizon
        + [(0, None)] * (2 * horizon)
    )
    return matrix.tocsr(), bounds


def solve_storage_mpc(
    price: np.ndarray,
    plan: DailyPlan,
    slot: int,
    current_soc_kwh: float,
    observed_net_load_kwh: float,
) -> tuple[float, float, float]:
    """按逐时紧急电费优化余下时域，并只返回当前一步动作。"""
    context = f"{plan.date} storage MPC slot {slot}"
    require(0 <= slot < cfg.N_SLOTS, context, "slot out of range")
    require(np.isfinite(current_soc_kwh), context, "current SOC is not finite")
    require(cfg.SOC_MIN_KWH - cfg.TOL <= current_soc_kwh <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "current SOC outside bounds")
    require(np.isfinite(observed_net_load_kwh), context, "current observation is not finite")

    nominal_net_load = (
        plan.grid_kwh[slot:] + plan.discharge_kwh[slot:] - plan.charge_kwh[slot:]
    )
    return solve_storage_mpc_horizon(
        price[slot:], plan.grid_kwh[slot:], nominal_net_load,
        current_soc_kwh, observed_net_load_kwh, context=context,
    )


def solve_storage_mpc_horizon(
    price: np.ndarray,
    grid_kwh: np.ndarray,
    nominal_net_load_kwh: np.ndarray,
    current_soc_kwh: float,
    observed_net_load_kwh: float,
    *,
    context="storage MPC",
) -> tuple[float, float, float]:
    """通用固定合同MPC核心；调用者只提供当前可知的未来基准曲线。"""
    horizon = len(price)
    require(horizon > 0, context, "empty horizon")
    array_check(price, (horizon,), context, "price", True)
    array_check(grid_kwh, (horizon,), context, "grid", True)
    array_check(nominal_net_load_kwh, (horizon,), context, "nominal net load")
    require(np.isfinite(current_soc_kwh), context, "current SOC is not finite")
    require(cfg.SOC_MIN_KWH - cfg.TOL <= current_soc_kwh <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "current SOC outside bounds")
    require(np.isfinite(observed_net_load_kwh), context, "current observation is not finite")
    matrix, bounds = _structure(horizon)
    objective = np.zeros(5 * horizon)
    objective[:2 * horizon] = cfg.EPS_THROUGHPUT
    objective[3 * horizon:4 * horizon] = cfg.EMERGENCY_PRICE_MULTIPLIER * price

    # 当前点才替换为实时观测；未来基准由调用者在对应决策时刻提供。
    nominal_net_load = nominal_net_load_kwh.copy()
    nominal_net_load[0] = observed_net_load_kwh
    balance_rhs = nominal_net_load - grid_kwh
    soc_rhs = np.r_[current_soc_kwh, np.zeros(horizon - 1)]
    rhs = np.r_[balance_rhs, soc_rhs, cfg.FINAL_SOC_KWH]
    result = linprog(
        objective,
        A_eq=matrix,
        b_eq=rhs,
        bounds=bounds,
        method="highs",
        options={"dual_feasibility_tolerance": 1e-9},
    )
    if not result.success:
        raise RuntimeError(
            f"Storage MPC failed on {context}: HiGHS status {result.status}: {result.message}"
        )
    charge = float(result.x[0])
    discharge = float(result.x[horizon])
    next_soc = float(result.x[2 * horizon])
    require(not (charge > cfg.RESIDUAL_TOL and discharge > cfg.RESIDUAL_TOL),
            context, "simultaneous first-step charge/discharge")
    return charge, discharge, next_soc


def execute_causal_day(
    price: np.ndarray,
    plan: DailyPlan,
    scenarios: ScenarioSet,
    actual_net_load_kwh: np.ndarray,
) -> BatteryExecution:
    """逐点观察、求解、执行；slot时刻只索引actual[slot]，不读取未来值。"""
    validate_scenarios(scenarios)
    array_check(price, (cfg.N_SLOTS,), str(plan.date), "price", True)
    array_check(actual_net_load_kwh, (cfg.N_SLOTS,), str(plan.date), "actual net load")
    require(plan.date == scenarios.target_date, str(plan.date), "plan/scenario date mismatch")
    require(cfg.MPC_REOPTIMIZE_SLOTS == 1, str(plan.date), "first implementation requires per-slot MPC")
    charge = np.zeros(cfg.N_SLOTS)
    discharge = np.zeros(cfg.N_SLOTS)
    soc = np.zeros(cfg.N_SLOTS)
    current_soc = cfg.INITIAL_SOC_KWH
    for slot in range(cfg.N_SLOTS):
        charge[slot], discharge[slot], current_soc = solve_storage_mpc(
            price, plan, slot, current_soc, float(actual_net_load_kwh[slot])
        )
        soc[slot] = current_soc
    execution = BatteryExecution(readonly(charge), readonly(discharge), readonly(soc))
    logging.debug("%s causal battery executed: throughput=%.3f", plan.date, charge.sum() + discharge.sum())
    return execution
