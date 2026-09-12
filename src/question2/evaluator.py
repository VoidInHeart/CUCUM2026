"""分别评价冻结储能基线和固定购电合同下的因果储能执行。"""
from dataclasses import replace
import numpy as np

from . import config as cfg
from .controller import execute_causal_day
from .scenario_builder import validate_scenarios
from .types import DailyEvaluation, DailyPlan, ScenarioSet, readonly
from .validator import array_check, validate_evaluation


def evaluate_frozen_storage(price: np.ndarray, plan: DailyPlan, actual_net_load_kwh: np.ndarray) -> DailyEvaluation:
    array_check(actual_net_load_kwh, (cfg.N_SLOTS,), str(plan.date), "actual net load")
    scheduled = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    emergency = readonly(np.maximum(actual_net_load_kwh - scheduled, 0))
    surplus = readonly(np.maximum(scheduled - actual_net_load_kwh, 0))
    planned_total = float(plan.grid_kwh.sum())
    emergency_total = float(emergency.sum())
    planned_cost = float(price @ plan.grid_kwh)
    emergency_cost = float(cfg.EMERGENCY_PRICE_MULTIPLIER * price @ emergency)
    evaluation = DailyEvaluation(plan, readonly(actual_net_load_kwh), emergency, surplus,
                                 planned_total, emergency_total, planned_total + emergency_total,
                                 planned_cost, emergency_cost, planned_cost + emergency_cost)
    validate_evaluation(price, evaluation)
    return evaluation


def evaluate_causal_storage(
    price: np.ndarray,
    plan: DailyPlan,
    scenarios: ScenarioSet,
    actual_net_load_kwh: np.ndarray,
) -> DailyEvaluation:
    """购电量沿用原计划，储能轨迹替换为逐时因果执行结果。"""
    validate_scenarios(scenarios)
    execution = execute_causal_day(price, plan, scenarios, actual_net_load_kwh)
    executed_plan = replace(
        plan,
        charge_kwh=execution.charge_kwh,
        discharge_kwh=execution.discharge_kwh,
        soc_end_kwh=execution.soc_end_kwh,
    )
    evaluation = evaluate_frozen_storage(price, executed_plan, actual_net_load_kwh)
    if not np.array_equal(evaluation.plan.grid_kwh, plan.grid_kwh):
        raise RuntimeError(f"{plan.date}: causal storage changed the frozen grid contract")
    return evaluation


# 旧入口固定代表A0，供问题4基线与已有调用保持精确回归。
evaluate = evaluate_frozen_storage
