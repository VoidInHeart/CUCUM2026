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


def attach_scenario_diagnostics(
    evaluation: DailyEvaluation,
    scenarios: ScenarioSet,
    actual_load_kw: np.ndarray,
) -> DailyEvaluation:
    """追加只用于事后评价的场景中心、P80覆盖率和实际负荷偏差。"""
    array_check(actual_load_kw, (cfg.N_SLOTS,), str(evaluation.plan.date), "actual load", True)
    order = np.argsort(scenarios.load_kw, axis=0, kind="stable")
    sorted_load = np.take_along_axis(scenarios.load_kw, order, axis=0)
    sorted_probability = np.take_along_axis(
        np.broadcast_to(scenarios.probability[:, None], scenarios.load_kw.shape), order, axis=0
    )
    cumulative = np.cumsum(sorted_probability, axis=0)
    positions = np.argmax(cumulative >= 0.8, axis=0)
    p80 = sorted_load[positions, np.arange(cfg.N_SLOTS)]
    mean = scenarios.probability @ scenarios.load_kw
    actual_energy = float(actual_load_kw.sum() * cfg.TIME_STEP_HOURS)
    mean_energy = float(mean.sum() * cfg.TIME_STEP_HOURS)
    return replace(
        evaluation,
        scenario_method=scenarios.method,
        mean_scenario_load_kwh=mean_energy,
        p80_scenario_load_kwh=float(p80.sum() * cfg.TIME_STEP_HOURS),
        actual_load_kwh=actual_energy,
        scenario_mean_bias_kwh=mean_energy - actual_energy,
        scenario_p80_coverage=float(np.mean(actual_load_kw <= p80)),
    )
