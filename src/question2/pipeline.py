"""串行执行完整回测；计划成功冻结后才索引当天实际值。"""
import logging
import numpy as np

from . import config as cfg
from .types import AnnualActualData, DailyEvaluation, DailyPriceData
from .scenario_builder import build_rolling_scenarios
from .optimizer import solve
from .evaluator import evaluate_causal_storage, evaluate_frozen_storage
from .validator import validate_complete
from ..pricing import PriceInput, price_for_date


STRATEGIES = ("baseline", "causal_mpc")


def solve_day(target_date, daily_price, annual: AnnualActualData, strategy="baseline") -> DailyEvaluation:
    if strategy not in STRATEGIES:
        raise ValueError(f"question2: unknown strategy {strategy!r}")
    day_index = annual.dates.index(target_date)
    scenarios = build_rolling_scenarios(annual, day_index)
    plan = solve(daily_price, scenarios)
    actual = annual.net_load_kwh[day_index]
    return (evaluate_frozen_storage(daily_price, plan, actual) if strategy == "baseline" else
            evaluate_causal_storage(daily_price, plan, scenarios, actual))


def run_annual(price: DailyPriceData | PriceInput, annual: AnnualActualData, strategy="baseline") -> list[DailyEvaluation]:
    if strategy not in STRATEGIES:
        raise ValueError(f"question2: unknown strategy {strategy!r}")
    prices = price.price if isinstance(price, DailyPriceData) else price
    results = []
    for day_index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
        target = annual.dates[day_index]
        try:
            daily_price = price_for_date(prices, target)
            result = solve_day(target, daily_price, annual, strategy)
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 daily pipeline failed: {exc}") from exc
        results.append(result)
        logging.info("[%03d/334] %s %s solved: price_mean=%.4f plan_kWh=%.3f emergency_kWh=%.3f total_cost=%.3f",
                     len(results), target, strategy, daily_price.mean(), result.planned_grid_total,
                     result.emergency_total, result.total_cost)
    validate_complete(prices, results)
    return results


def run_ablation(price: DailyPriceData | PriceInput, annual: AnnualActualData) -> dict[str, list[DailyEvaluation]]:
    """每一天只求一次0:00计划，再并列执行A0/A1，避免合同数值出现求解差异。"""
    prices = price.price if isinstance(price, DailyPriceData) else price
    results = {name: [] for name in STRATEGIES}
    for day_index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
        target = annual.dates[day_index]
        try:
            daily_price = price_for_date(prices, target)
            scenarios = build_rolling_scenarios(annual, day_index)
            plan = solve(daily_price, scenarios)
            actual = annual.net_load_kwh[day_index]
            baseline = evaluate_frozen_storage(daily_price, plan, actual)
            causal = evaluate_causal_storage(daily_price, plan, scenarios, actual)
            if not np.array_equal(baseline.plan.grid_kwh, causal.plan.grid_kwh):
                raise RuntimeError("A0/A1 grid contracts differ")
            results["baseline"].append(baseline)
            results["causal_mpc"].append(causal)
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 ablation failed: {exc}") from exc
        logging.info("[%03d/334] %s A0=%.3f A1=%.3f saving=%.3f",
                     len(results["baseline"]), target, baseline.total_cost, causal.total_cost,
                     baseline.total_cost - causal.total_cost)
    for values in results.values():
        validate_complete(prices, values)
    return results
