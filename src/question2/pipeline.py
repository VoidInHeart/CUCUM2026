"""串行执行完整回测；计划成功冻结后才索引当天实际值。"""
import logging

from . import config as cfg
from .types import AnnualActualData, DailyEvaluation, DailyPriceData
from .scenario_builder import build_rolling_scenarios
from .optimizer import solve
from .evaluator import evaluate
from .validator import validate_complete
from ..pricing import PriceInput, price_for_date


def solve_day(target_date, daily_price, annual: AnnualActualData) -> DailyEvaluation:
    day_index = annual.dates.index(target_date)
    scenarios = build_rolling_scenarios(annual, day_index)
    plan = solve(daily_price, scenarios)
    return evaluate(daily_price, plan, annual.net_load_kwh[day_index])


def run_annual(price: DailyPriceData | PriceInput, annual: AnnualActualData) -> list[DailyEvaluation]:
    prices = price.price if isinstance(price, DailyPriceData) else price
    results = []
    for day_index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
        target = annual.dates[day_index]
        try:
            daily_price = price_for_date(prices, target)
            result = solve_day(target, daily_price, annual)
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 daily pipeline failed: {exc}") from exc
        results.append(result)
        logging.info("[%03d/334] %s solved: price_mean=%.4f plan_kWh=%.3f emergency_kWh=%.3f total_cost=%.3f",
                     len(results), target, daily_price.mean(), result.planned_grid_total, result.emergency_total, result.total_cost)
    validate_complete(prices, results)
    return results
