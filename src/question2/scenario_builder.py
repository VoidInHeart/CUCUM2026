"""唯一的滚动场景入口：只截取目标日前31天。"""
from datetime import timedelta
import numpy as np

from . import config as cfg
from .types import AnnualActualData, ScenarioSet, readonly


def validate_scenarios(scenarios: ScenarioSet) -> None:
    prefix = f"{scenarios.target_date}: scenario_builder"
    expected = tuple(scenarios.target_date - timedelta(days=i) for i in range(cfg.HISTORY_WINDOW_DAYS, 0, -1))
    if scenarios.history_dates != expected or any(day >= scenarios.target_date for day in scenarios.history_dates):
        raise ValueError(f"{prefix}: history must be exactly the preceding 31 days; no lookahead allowed")
    if scenarios.net_load_kwh.shape != (cfg.HISTORY_WINDOW_DAYS, cfg.N_SLOTS) or not np.isfinite(scenarios.net_load_kwh).all():
        raise ValueError(f"{prefix}: invalid scenario matrix")
    if scenarios.probability.shape != (cfg.HISTORY_WINDOW_DAYS,) or not np.allclose(
        scenarios.probability, 1 / cfg.HISTORY_WINDOW_DAYS, rtol=0, atol=1e-12
    ):
        raise ValueError(f"{prefix}: expected 31 equal scenario probabilities")


def build_rolling_scenarios(annual_data: AnnualActualData, target_index: int) -> ScenarioSet:
    if not cfg.HISTORY_WINDOW_DAYS <= target_index < len(annual_data.dates):
        raise ValueError(f"scenario_builder: target index {target_index} lacks 31 days of history or is out of range")
    start = target_index - cfg.HISTORY_WINDOW_DAYS
    scenarios = ScenarioSet(annual_data.dates[target_index], annual_data.dates[start:target_index],
                            readonly(annual_data.net_load_kwh[start:target_index]),
                            readonly(np.full(cfg.HISTORY_WINDOW_DAYS, 1 / cfg.HISTORY_WINDOW_DAYS)))
    validate_scenarios(scenarios)
    return scenarios
