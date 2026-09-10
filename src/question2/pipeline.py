"""串行执行完整回测；计划成功冻结后才索引当天实际值。"""
import logging

from . import config as cfg
from .types import AnnualActualData, DailyEvaluation, DailyPriceData
from .scenario_builder import build_rolling_scenarios
from .optimizer import solve
from .evaluator import evaluate
from .validator import validate_complete


def run_annual(price: DailyPriceData, annual: AnnualActualData) -> list[DailyEvaluation]:
    results = []
    for day_index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
        target = annual.dates[day_index]
        try:
            scenarios = build_rolling_scenarios(annual, day_index)
            plan = solve(price.price, scenarios)
            actual_today = annual.net_load_kwh[day_index]
            result = evaluate(price.price, plan, actual_today)
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 daily pipeline failed: {exc}") from exc
        results.append(result)
        logging.info("[%03d/334] %s solved: plan_kWh=%.3f emergency_kWh=%.3f total_cost=%.3f",
                     len(results), target, result.planned_grid_total, result.emergency_total, result.total_cost)
    validate_complete(price.price, results)
    return results
