"""串行执行完整回测；计划成功冻结后才索引当天实际值。"""
from dataclasses import dataclass
import logging
import numpy as np

from . import config as cfg
from .types import AnnualActualData, DailyEvaluation, DailyPriceData
from .scenario_builder import build_scenarios
from .optimizer import solve, solve_grid_first_stage_storage_recourse
from .evaluator import attach_scenario_diagnostics, evaluate_causal_storage, evaluate_frozen_storage
from .validator import validate_complete
from ..pricing import PriceInput, price_for_date


@dataclass(frozen=True)
class StrategySpec:
    code: str
    scenario_method: str
    storage_execution: str
    label: str
    contract_optimizer: str = "shared_storage"


STRATEGY_SPECS = {
    spec.code: spec for spec in (
        StrategySpec("baseline", "raw_equal", "frozen", "A0"),
        StrategySpec("causal_mpc", "raw_equal", "causal_mpc", "A1"),
        StrategySpec("weekday_corrected", "weekday_corrected", "frozen", "A2"),
        StrategySpec("weekday_trend_corrected", "weekday_trend_corrected", "frozen", "A3"),
        StrategySpec("weekday_trend_weighted", "weekday_trend_weighted", "frozen", "A4"),
        StrategySpec("residual_equal", "residual_equal", "frozen", "A5"),
        StrategySpec("weekday_trend_causal", "weekday_trend_corrected", "causal_mpc", "A6"),
        StrategySpec("residual_weighted_causal", "residual_weighted", "causal_mpc", "A7"),
        StrategySpec("grid_recourse_residual_causal", "residual_weighted", "causal_mpc", "A8", "grid_recourse"),
        StrategySpec("level_scaled", "level_scaled", "frozen", "level-scale"),
    )
}
STRATEGIES = tuple(STRATEGY_SPECS)


def _evaluate(spec, daily_price, plan, scenarios, actual_net, actual_load):
    result = (evaluate_frozen_storage(daily_price, plan, actual_net)
              if spec.storage_execution == "frozen"
              else evaluate_causal_storage(daily_price, plan, scenarios, actual_net))
    return attach_scenario_diagnostics(result, scenarios, actual_load)


def solve_day(target_date, daily_price, annual: AnnualActualData, strategy="baseline") -> DailyEvaluation:
    if strategy not in STRATEGIES:
        raise ValueError(f"question2: unknown strategy {strategy!r}")
    spec = STRATEGY_SPECS[strategy]
    day_index = annual.dates.index(target_date)
    scenarios = build_scenarios(annual, day_index, spec.scenario_method)
    plan = (solve(daily_price, scenarios) if spec.contract_optimizer == "shared_storage" else
            solve_grid_first_stage_storage_recourse(daily_price, scenarios))
    return _evaluate(spec, daily_price, plan, scenarios, annual.net_load_kwh[day_index], annual.load_kw[day_index])


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
            actual_net = annual.net_load_kwh[day_index]
            actual_load = annual.load_kw[day_index]
            plans = {}
            for spec in STRATEGY_SPECS.values():
                key = (spec.scenario_method, spec.contract_optimizer)
                if key not in plans:
                    scenarios = build_scenarios(annual, day_index, spec.scenario_method)
                    planner = (solve if spec.contract_optimizer == "shared_storage"
                               else solve_grid_first_stage_storage_recourse)
                    plans[key] = (scenarios, planner(daily_price, scenarios))
                scenarios, plan = plans[key]
                results[spec.code].append(
                    _evaluate(spec, daily_price, plan, scenarios, actual_net, actual_load)
                )
            baseline = results["baseline"][-1]
            causal = results["causal_mpc"][-1]
            if not np.array_equal(baseline.plan.grid_kwh, causal.plan.grid_kwh):
                raise RuntimeError("A0/A1 grid contracts differ")
        except Exception as exc:
            raise RuntimeError(f"{target}: question2 ablation failed: {exc}") from exc
        logging.info("[%03d/334] %s A0=%.3f A1=%.3f current_best=%s %.3f",
                     len(results["baseline"]), target, baseline.total_cost, causal.total_cost,
                     min(results, key=lambda name: results[name][-1].total_cost),
                     min(values[-1].total_cost for values in results.values()))
    for values in results.values():
        validate_complete(prices, values)
    return results
