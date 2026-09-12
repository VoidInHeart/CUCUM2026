"""串行执行完整回测；计划成功冻结后才索引当天实际值。"""
import logging
from dataclasses import replace
import numpy as np

from . import config as cfg
from .types import AnnualActualData, DailyEvaluation, DailyPriceData, readonly
from .scenario_builder import build_rolling_scenarios, build_multiday_scenarios
from .optimizer import solve
from .evaluator import evaluate
from .validator import validate_complete
from ..pricing import PriceInput, price_for_date, continuation_price_for_date
from ..soc_initialization import control_start_soc


def solve_day(target_date, daily_price, annual: AnnualActualData, initial_soc_kwh=None,
              soc_policy="daily_closed", continuation_price=None, method="SAA", risk_weight=0.1,
              risk_alpha=0.95) -> DailyEvaluation:
    day_index = annual.dates.index(target_date)
    lookahead = soc_policy == "continuous_lookahead"
    scenarios = (build_multiday_scenarios if lookahead else build_rolling_scenarios)(annual, day_index)
    if method not in ("DET", "Q80", "SAA", "CVaR-SAA"):
        raise ValueError("unknown benchmark method")
    if method in ("DET", "Q80"):
        curve = scenarios.net_load_kwh.mean(axis=0) if method == "DET" else np.quantile(scenarios.net_load_kwh,.8,axis=0)
        # Equivalent identical scenarios preserve the shared LP/validation interface.
        scenarios = replace(scenarios,net_load_kwh=readonly(np.tile(curve,(len(scenarios.probability),1))))
    price = np.r_[daily_price, daily_price if continuation_price is None else continuation_price] if lookahead else daily_price
    plan = solve(price, scenarios, initial_soc_kwh, soc_policy, risk_weight if method == "CVaR-SAA" else 0., risk_alpha)
    if lookahead:
        arrays = {name: readonly(getattr(plan, name)[:144]) for name in
                  ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh")}
        emergency = np.maximum(scenarios.net_load_kwh[:, :144] - arrays["grid_kwh"]
                               - arrays["discharge_kwh"] + arrays["charge_kwh"], 0)
        expected = scenarios.probability @ emergency
        losses = cfg.EMERGENCY_PRICE_MULTIPLIER * emergency @ daily_price
        cvar = min(float(eta + scenarios.probability @ np.maximum(losses-eta,0)/(1-risk_alpha)) for eta in losses)
        risk = plan.risk_weight*cvar
        plan = replace(plan, **arrays, expected_emergency_kwh=float(expected.sum()), risk_penalty=risk,
                       expected_objective=float(daily_price @ arrays["grid_kwh"] +
                           cfg.EMERGENCY_PRICE_MULTIPLIER * daily_price @ expected +
                           cfg.EPS_THROUGHPUT * (arrays["charge_kwh"].sum() + arrays["discharge_kwh"].sum()) + risk))
    return evaluate(daily_price, plan, annual.net_load_kwh[day_index])


def run_annual(price: DailyPriceData | PriceInput, annual: AnnualActualData,
               soc_policy="daily_closed", initialization_mode="feb1_control_start", method="SAA",
               risk_weight=0.1, risk_alpha=0.95, price_information_mode="current_day_persistence") -> list[DailyEvaluation]:
    if initialization_mode not in ("feb1_control_start", "jan1_continuous"):
        raise ValueError("unknown initialization mode")
    prices = price.price if isinstance(price, DailyPriceData) else price
    results = []
    current_soc_kwh = control_start_soc(initialization_mode,annual)
    for day_index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
        target = annual.dates[day_index]
        try:
            daily_price = price_for_date(prices, target)
            result = solve_day(target, daily_price, annual, current_soc_kwh, soc_policy,
                               continuation_price=continuation_price_for_date(prices,target,price_information_mode),
                               method=method, risk_weight=risk_weight, risk_alpha=risk_alpha)
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 daily pipeline failed: {exc}") from exc
        results.append(result)
        current_soc_kwh = cfg.CONTROL_START_SOC_KWH if soc_policy == "daily_closed" else result.plan.terminal_soc_kwh
        logging.info("[%03d/334] %s solved: price_mean=%.4f plan_kWh=%.3f emergency_kWh=%.3f total_cost=%.3f",
                     len(results), target, daily_price.mean(), result.planned_grid_total, result.emergency_total, result.total_cost)
    validate_complete(prices, results)
    return results
