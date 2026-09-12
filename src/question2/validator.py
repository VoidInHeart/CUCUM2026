"""独立检查第一阶段储能、历史场景平衡和事后结算。"""
import numpy as np

from . import config as cfg
from .scenario_builder import validate_scenarios
from .types import DailyEvaluation, DailyPlan, ScenarioSet
from ..pricing import PriceInput, price_for_date


def require(ok, context: str, reason: str) -> None:
    if not ok:
        raise ValueError(f"{context}: validator: {reason}")


def array_check(value: np.ndarray, shape: tuple, context: str, name: str, nonnegative=False) -> None:
    require(np.shape(value) == shape, context, f"{name}: expected shape {shape}")
    require(np.isfinite(value).all(), context, f"{name}: NaN / Inf")
    if nonnegative:
        require((value >= -cfg.TOL).all(), context, f"{name}: negative values")


def validate_plan(plan: DailyPlan) -> float:
    context = str(plan.date)
    for name in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh"):
        array_check(getattr(plan, name), (cfg.N_SLOTS,), context, name, True)
    c, d, soc = plan.charge_kwh, plan.discharge_kwh, plan.soc_end_kwh
    for name, values in (("charge", c), ("discharge", d)):
        require(values.max() <= cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH + cfg.TOL, context, f"{name}: power limit")
    require(soc.min() >= cfg.SOC_MIN_KWH - cfg.TOL and soc.max() <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "SOC bounds")
    rebuilt = cfg.INITIAL_SOC_KWH + np.cumsum(cfg.ETA_CHARGE * c - d / cfg.ETA_DISCHARGE)
    residual = float(np.max(np.abs(rebuilt - soc)))
    require(residual <= cfg.RESIDUAL_TOL, context, "SOC dynamic residual")
    require(abs(soc[-1] - cfg.FINAL_SOC_KWH) <= cfg.RESIDUAL_TOL, context, "terminal SOC")
    require(not np.any((c > cfg.RESIDUAL_TOL) & (d > cfg.RESIDUAL_TOL)), context, "simultaneous charge/discharge")
    require(np.isfinite(plan.expected_objective) and np.isfinite(plan.expected_emergency_kwh), context, "invalid expected totals")
    return residual


def validate_lp(price: np.ndarray, scenarios: ScenarioSet, plan: DailyPlan,
                emergency: np.ndarray, surplus: np.ndarray) -> dict[str, float]:
    validate_scenarios(scenarios)
    context = str(plan.date)
    require(plan.date == scenarios.target_date, context, "scenario target date differs from plan")
    soc_residual = validate_plan(plan)
    array_check(price, (cfg.N_SLOTS,), context, "price", True)
    scenario_count = len(scenarios.history_dates)
    for name, array in (("emergency", emergency), ("surplus", surplus)):
        array_check(array, (scenario_count, cfg.N_SLOTS), context, name, True)
    scheduled = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    balance = scheduled[None, :] + emergency - surplus - scenarios.net_load_kwh
    max_residual = float(np.max(np.abs(balance)))
    require(max_residual <= cfg.RESIDUAL_TOL, context, "scenario balance residual")
    expected_emergency = float(scenarios.probability @ emergency.sum(axis=1))
    objective = float(price @ plan.grid_kwh + cfg.EMERGENCY_PRICE_MULTIPLIER *
                      (scenarios.probability @ emergency) @ price +
                      cfg.EPS_THROUGHPUT * (plan.charge_kwh.sum() + plan.discharge_kwh.sum()))
    require(abs(expected_emergency - plan.expected_emergency_kwh) <= cfg.RESIDUAL_TOL, context, "expected emergency total")
    require(abs(objective - plan.expected_objective) <= cfg.RESIDUAL_TOL, context, "solver objective mismatch")
    return {"max_scenario_balance_residual": max_residual, "max_soc_residual": soc_residual}


def validate_grid_recourse_lp(price, scenarios, plan, charge, discharge, soc,
                              emergency, surplus, reference_scenario) -> dict[str, float]:
    """独立检查grid一阶段、储能场景recourse及返回的参考轨迹。"""
    validate_scenarios(scenarios)
    context = f"{scenarios.target_date} grid-recourse"
    count = len(scenarios.history_dates)
    shape = (count, cfg.N_SLOTS)
    array_check(price, (cfg.N_SLOTS,), context, "price", True)
    array_check(plan.grid_kwh, (cfg.N_SLOTS,), context, "grid", True)
    for name, values in (("charge", charge), ("discharge", discharge), ("soc", soc),
                         ("emergency", emergency), ("surplus", surplus)):
        array_check(values, shape, context, name, True)
    require(0 <= reference_scenario < count, context, "invalid reference scenario")
    for name, expected in (("charge_kwh", charge[reference_scenario]),
                           ("discharge_kwh", discharge[reference_scenario]),
                           ("soc_end_kwh", soc[reference_scenario])):
        require(np.max(np.abs(getattr(plan, name) - expected)) <= cfg.RESIDUAL_TOL,
                context, f"reference {name} mismatch")
    max_power = max(float(charge.max()), float(discharge.max()))
    require(max_power <= cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH + cfg.TOL, context, "battery power limit")
    require(soc.min() >= cfg.SOC_MIN_KWH - cfg.TOL and soc.max() <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "SOC bounds")
    rebuilt = cfg.INITIAL_SOC_KWH + np.cumsum(
        cfg.ETA_CHARGE * charge - discharge / cfg.ETA_DISCHARGE, axis=1
    )
    soc_residual = float(np.max(np.abs(rebuilt - soc)))
    require(soc_residual <= cfg.RESIDUAL_TOL, context, "SOC dynamic residual")
    require(np.max(np.abs(soc[:, -1] - cfg.FINAL_SOC_KWH)) <= cfg.RESIDUAL_TOL,
            context, "terminal SOC")
    require(not np.any((charge > cfg.RESIDUAL_TOL) & (discharge > cfg.RESIDUAL_TOL)),
            context, "simultaneous charge/discharge")
    balance = (plan.grid_kwh[None, :] + discharge - charge + emergency - surplus
               - scenarios.net_load_kwh)
    balance_residual = float(np.max(np.abs(balance)))
    require(balance_residual <= cfg.RESIDUAL_TOL, context, "scenario balance residual")
    expected_emergency = float(scenarios.probability @ emergency.sum(axis=1))
    objective = float(
        price @ plan.grid_kwh
        + cfg.EMERGENCY_PRICE_MULTIPLIER * (scenarios.probability @ emergency) @ price
        + cfg.RECOURSE_EPS_THROUGHPUT * (scenarios.probability @ (charge + discharge).sum(axis=1))
    )
    require(abs(expected_emergency - plan.expected_emergency_kwh) <= cfg.RESIDUAL_TOL,
            context, "expected emergency total")
    require(abs(objective - plan.expected_objective) <= cfg.RESIDUAL_TOL,
            context, "solver objective mismatch")
    validate_plan(plan)
    return {"max_scenario_balance_residual": balance_residual, "max_soc_residual": soc_residual}


def validate_evaluation(price: np.ndarray, evaluation: DailyEvaluation) -> None:
    plan = evaluation.plan
    context = str(plan.date)
    validate_plan(plan)
    array_check(price, (cfg.N_SLOTS,), context, "price", True)
    array_check(evaluation.actual_net_load_kwh, (cfg.N_SLOTS,), context, "actual net load")
    for name in ("emergency_kwh", "surplus_kwh"):
        array_check(getattr(evaluation, name), (cfg.N_SLOTS,), context, name, True)
    scheduled = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    actual = evaluation.actual_net_load_kwh
    for name, expected in (("emergency_kwh", np.maximum(actual - scheduled, 0)),
                           ("surplus_kwh", np.maximum(scheduled - actual, 0))):
        require(np.max(np.abs(getattr(evaluation, name) - expected)) <= cfg.RESIDUAL_TOL, context, f"{name}: incorrect settlement")
    require(np.max(np.abs(scheduled + evaluation.emergency_kwh - evaluation.surplus_kwh - actual)) <= cfg.RESIDUAL_TOL,
            context, "actual balance residual")
    planned = float(plan.grid_kwh.sum())
    emergency = float(evaluation.emergency_kwh.sum())
    planned_cost = float(price @ plan.grid_kwh)
    emergency_cost = float(cfg.EMERGENCY_PRICE_MULTIPLIER * price @ evaluation.emergency_kwh)
    for name, expected in (("planned_grid_total", planned), ("emergency_total", emergency),
                           ("total_grid_purchase", planned + emergency), ("planned_cost", planned_cost),
                           ("emergency_cost", emergency_cost), ("total_cost", planned_cost + emergency_cost)):
        value = getattr(evaluation, name)
        require(np.isfinite(value) and abs(value - expected) <= cfg.RESIDUAL_TOL, context, f"{name}: total mismatch")


def validate_complete(price: PriceInput, evaluations: list[DailyEvaluation]) -> None:
    require(tuple(item.plan.date for item in evaluations) == cfg.OUTPUT_DATES, "export",
            "expected all 334 dates in chronological order")
    for item in evaluations:
        validate_evaluation(price_for_date(price, item.plan.date), item)
