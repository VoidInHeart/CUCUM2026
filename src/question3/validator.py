"""对每个LP、调整流水、冻结区间和实际日结算作独立验证。"""
import numpy as np
from ..pricing import price_for_date

from ..question2.validator import array_check, require
from . import config as cfg
from .rolling_scenario_builder import validate_scenarios
from .types import HorizonPlan, AdjustmentRevision, DailySchedule, DailyResult


def validate_horizon(plan: HorizonPlan) -> float:
    context = f"{plan.date} {plan.issue_hour}:00"
    require(plan.issue_hour in cfg.ISSUE_HOURS, context, "invalid issue hour")
    require(plan.soc_policy in ("daily_closed", "continuous_lookahead"), context, "invalid SOC policy")
    h = 6 * (24 - plan.issue_hour) if plan.soc_policy == "daily_closed" else 144
    for field in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh"):
        array_check(getattr(plan, field), (h,), context, field, True)
    require(np.isfinite(plan.initial_soc_kwh) and cfg.SOC_MIN_KWH - cfg.TOL <= plan.initial_soc_kwh <= cfg.SOC_MAX_KWH + cfg.TOL,
            context, "initial SOC outside bounds")
    if plan.issue_hour == 0 and plan.soc_policy == "daily_closed":
        require(abs(plan.initial_soc_kwh - cfg.INITIAL_SOC_KWH) <= cfg.RESIDUAL_TOL, context, "0:00 initial SOC")
    c, d, soc = plan.charge_kwh, plan.discharge_kwh, plan.soc_end_kwh
    require(max(c.max(), d.max()) <= cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH + cfg.TOL, context, "battery power limit")
    require(soc.min() >= cfg.SOC_MIN_KWH - cfg.TOL and soc.max() <= cfg.SOC_MAX_KWH + cfg.TOL, context, "SOC bounds")
    rebuilt = plan.initial_soc_kwh + np.cumsum(cfg.ETA_CHARGE * c - d / cfg.ETA_DISCHARGE)
    residual = float(np.max(np.abs(rebuilt - soc)))
    require(residual <= cfg.RESIDUAL_TOL, context, "SOC dynamic residual")
    if plan.soc_policy == "daily_closed":
        require(abs(soc[-1] - cfg.FINAL_SOC_KWH) <= cfg.RESIDUAL_TOL, context, "terminal SOC")
    else:
        array_check(plan.horizon_price, (h,), context, "horizon price", True)
    require(not np.any((c > cfg.RESIDUAL_TOL) & (d > cfg.RESIDUAL_TOL)), context, "simultaneous charge/discharge")
    require(np.isfinite(plan.solver_objective) and np.isfinite(plan.expected_emergency_kwh), context, "invalid solver totals")
    return residual


def validate_revision(price: np.ndarray, revision: AdjustmentRevision) -> None:
    plan = revision.plan
    context = f"{plan.date} {revision.issue_hour}:00"
    validate_horizon(plan)
    if plan.horizon_price is not None:
        require(np.max(np.abs(plan.horizon_price[:144-revision.start_slot]-price[revision.start_slot:])) <= cfg.TOL,
                context, "horizon current-day prices differ from settlement")
    require(revision.issue_hour in cfg.ISSUE_HOURS[1:] and revision.issue_hour == plan.issue_hour,
            context, "invalid revision issue")
    require(revision.start_slot == cfg.ISSUE_SLOT[revision.issue_hour], context, "incorrect start slot")
    shape = (144-revision.start_slot,)
    for name in ("old_grid", "up_adjust", "down_adjust"):
        array_check(getattr(revision, name), shape, context, name, True)
    require(np.max(np.abs(revision.new_grid - revision.old_grid - revision.up_adjust + revision.down_adjust)) <= cfg.RESIDUAL_TOL,
            context, "adjustment identity")
    require(np.all(revision.down_adjust <= revision.old_grid + cfg.TOL), context, "cancellation exceeds previous contract")
    require(not np.any((revision.up_adjust > cfg.RESIDUAL_TOL) & (revision.down_adjust > cfg.RESIDUAL_TOL)),
            context, "simultaneous up/down adjustment")
    expected = (cfg.UP_ADJUST_PRICE_MULTIPLIER * price[revision.start_slot:] @ revision.up_adjust
                - cfg.CANCEL_REFUND_MULTIPLIER * price[revision.start_slot:] @ revision.down_adjust)
    require(np.isfinite(revision.adjustment_cashflow_yuan) and abs(expected - revision.adjustment_cashflow_yuan) <= cfg.TOL,
            context, "adjustment cashflow mismatch")


def validate_lp(price, scenarios, plan, emergency, surplus, revision=None) -> dict:
    context = f"{plan.date} {plan.issue_hour}:00"
    validate_scenarios(scenarios)
    require((scenarios.target_date, scenarios.issue_hour) == (plan.date, plan.issue_hour), context, "scenario issue mismatch")
    soc_residual = validate_horizon(plan)
    shape = scenarios.net_load_kwh.shape
    array_check(emergency, shape, context, "scenario emergency", True)
    array_check(surplus, shape, context, "scenario surplus", True)
    supplied = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    balance = supplied + emergency - surplus - scenarios.net_load_kwh
    max_residual = float(np.max(np.abs(balance)))
    require(max_residual <= cfg.RESIDUAL_TOL, context, "scenario energy balance")
    q = price[cfg.ISSUE_SLOT[plan.issue_hour]:] if plan.horizon_price is None else plan.horizon_price
    if revision is None:
        require(plan.issue_hour == 0, context, "adjustment revision missing")
        transaction = q @ plan.grid_kwh
    else:
        validate_revision(price, revision)
        transaction = revision.adjustment_cashflow_yuan
        m = len(revision.old_grid)
        transaction += q[m:] @ plan.grid_kwh[m:]
    expected = (transaction + cfg.EMERGENCY_PRICE_MULTIPLIER * (scenarios.probability @ emergency) @ q
                + cfg.EPS_THROUGHPUT * (plan.charge_kwh.sum() + plan.discharge_kwh.sum()))
    require(abs(expected - plan.solver_objective) <= cfg.RESIDUAL_TOL, context, "solver objective mismatch")
    require(abs(scenarios.probability @ emergency.sum(axis=1) - plan.expected_emergency_kwh) <= cfg.RESIDUAL_TOL,
            context, "expected emergency total")
    return {"max_scenario_residual": max_residual, "max_soc_residual": soc_residual}


def validate_schedule(price: np.ndarray, schedule: DailySchedule, update_hours: tuple[int, ...]) -> None:
    context = str(schedule.date)
    initial = schedule.initial_plan
    validate_horizon(initial)
    if initial.horizon_price is not None:
        require(np.max(np.abs(initial.horizon_price-price)) <= cfg.TOL, context, "initial horizon prices differ")
    require(initial.issue_hour == 0, context, "missing initial plan")
    require(tuple(revision.issue_hour for revision in schedule.revisions) == update_hours[1:], context, "revision sequence mismatch")
    # 逐次重放全部版本，核对old必须为上一版剩余计划、过去区间保持冻结。
    current = {name: getattr(initial, name).copy() for name in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh")}
    for revision in schedule.revisions:
        validate_revision(price, revision)
        start = revision.start_slot
        require(revision.plan.date == schedule.date, context, "revision date differs")
        require(np.max(np.abs(revision.old_grid - current["grid_kwh"][start:])) <= cfg.RESIDUAL_TOL, context, "old_grid is not previous version")
        require(abs(revision.plan.initial_soc_kwh - current["soc_end_kwh"][start - 1]) <= cfg.RESIDUAL_TOL,
                context, "SOC boundary discontinuity")
        for name in current:
            current[name][start:] = getattr(revision.plan, name)[:144-start]
    for name, source in (("executed_grid", "grid_kwh"), ("executed_charge", "charge_kwh"),
                         ("executed_discharge", "discharge_kwh"), ("executed_soc_end", "soc_end_kwh")):
        values = getattr(schedule, name)
        array_check(values, (144,), context, name, True)
        require(np.max(np.abs(values - current[source])) <= cfg.RESIDUAL_TOL, context, f"{name}: frozen execution differs from revision replay")
    rebuilt = initial.initial_soc_kwh + np.cumsum(cfg.ETA_CHARGE * schedule.executed_charge - schedule.executed_discharge / cfg.ETA_DISCHARGE)
    require(np.max(np.abs(rebuilt - schedule.executed_soc_end)) <= cfg.RESIDUAL_TOL, context, "executed SOC reconstruction")


def validate_day(price: np.ndarray, result: DailyResult, update_hours: tuple[int, ...]) -> None:
    s = result.schedule
    context = str(s.date)
    validate_schedule(price, s, update_hours)
    array_check(result.actual_net_load, (144,), context, "actual net load")
    for name in ("real_emergency", "real_surplus"):
        array_check(getattr(result, name), (144,), context, name, True)
    supplied = s.executed_grid + s.executed_discharge - s.executed_charge
    require(np.max(np.abs(supplied + result.real_emergency - result.real_surplus - result.actual_net_load)) <= cfg.RESIDUAL_TOL,
            context, "actual energy balance")
    require(np.max(np.abs(result.real_emergency - np.maximum(result.actual_net_load - supplied, 0))) <= cfg.RESIDUAL_TOL,
            context, "actual emergency settlement")
    plan_cost = float(price @ s.initial_plan.grid_kwh)
    adjustment_cost = sum(revision.adjustment_cashflow_yuan for revision in s.revisions)
    emergency_cost = float(cfg.EMERGENCY_PRICE_MULTIPLIER * price @ result.real_emergency)
    initial_energy = float(s.initial_plan.grid_kwh.sum())
    executed_energy = float(s.executed_grid.sum())
    emergency_energy = float(result.real_emergency.sum())
    for name, expected in (("plan_cost", plan_cost), ("adjustment_cost", adjustment_cost), ("emergency_cost", emergency_cost),
                           ("total_cost", plan_cost + adjustment_cost + emergency_cost), ("initial_plan_kwh", initial_energy),
                           ("executed_adjusted_kwh", executed_energy), ("emergency_kwh", emergency_energy),
                           ("actual_grid_energy_kwh", executed_energy + emergency_energy)):
        actual = getattr(result, name)
        require(np.isfinite(actual) and abs(actual - expected) <= cfg.TOL, context, f"{name}: accounting mismatch")


def validate_complete(price, results, update_hours=cfg.Q3_FINAL_UPDATE_HOURS):
    require(tuple(item.schedule.date for item in results) == cfg.OUTPUT_DATES, "export", "expected all 334 output dates")
    for item in results:
        validate_day(price_for_date(price, item.schedule.date), item, update_hours)
    for previous, item in zip(results, results[1:]):
        require(item.schedule.initial_plan.soc_policy == previous.schedule.initial_plan.soc_policy, "annual", "mixed SOC policies")
        require(abs(item.schedule.initial_plan.initial_soc_kwh-previous.schedule.executed_soc_end[-1]) <= cfg.RESIDUAL_TOL,
                str(item.schedule.date), "cross-day SOC discontinuity")
