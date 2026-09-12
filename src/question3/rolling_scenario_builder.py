"""保留历史负载与同日误差的配对；仅访问当前发布的目标日预报。"""
from datetime import timedelta
import numpy as np

from . import config as cfg
from .forecast_error import HistoricalErrors
from .forecast_interpolator import interpolate_hourly_pv_forecast
from .types import RollingScenarios, readonly
from ..question2.forecast import forecast_load
from ..question2.scenario_builder import compute_scenario_weights


def validate_scenarios(scenarios: RollingScenarios) -> None:
    context = f"{scenarios.target_date} {scenarios.issue_hour}: scenario_builder"
    if scenarios.method not in cfg.SCENARIO_METHODS:
        raise ValueError(f"{context}: unknown scenario method {scenarios.method!r}")
    if scenarios.issue_hour not in cfg.ISSUE_HOURS:
        raise ValueError(f"{context}: invalid issue hour")
    count = len(scenarios.history_dates)
    earliest = scenarios.target_date - timedelta(days=cfg.HISTORY_WINDOW_DAYS)
    if (not count or tuple(sorted(scenarios.history_dates)) != scenarios.history_dates
            or len(set(scenarios.history_dates)) != count
            or any(day < earliest or day >= scenarios.target_date for day in scenarios.history_dates)):
        raise ValueError(f"{context}: history must be inside preceding 31 days, no lookahead")
    h = 6 * (24 - scenarios.issue_hour)
    for name, shape in (("forecast_kw", (h,)), ("load_forecast_kw", (h,)),
                        ("pv_scenario_kw", (count, h)), ("load_scenario_kw", (count, h)),
                        ("net_load_kwh", (count, h)), ("probability", (count,))):
        values = getattr(scenarios, name)
        if values.shape != shape or not np.isfinite(values).all():
            raise ValueError(f"{context}: {name}: invalid shape or NaN / Inf")
    if any((values < 0).any() for values in (scenarios.pv_scenario_kw, scenarios.forecast_kw,
                                              scenarios.load_scenario_kw, scenarios.load_forecast_kw)):
        raise ValueError(f"{context}: negative load or PV")
    if ((scenarios.probability <= 0).any()
            or not np.isclose(scenarios.probability.sum(), 1, rtol=0, atol=1e-12)):
        raise ValueError(f"{context}: invalid probabilities")
    rebuilt = (scenarios.load_scenario_kw - scenarios.pv_scenario_kw) * cfg.TIME_STEP_HOURS
    if np.max(np.abs(rebuilt - scenarios.net_load_kwh)) > cfg.RESIDUAL_TOL:
        raise ValueError(f"{context}: load/PV and net-load scenarios differ")
    if scenarios.method == "raw_equal":
        expected = tuple(scenarios.target_date - timedelta(days=i)
                         for i in range(cfg.HISTORY_WINDOW_DAYS, 0, -1))
        if scenarios.history_dates != expected:
            raise ValueError(f"{context}: raw history must be exactly preceding 31 days")
        if not np.allclose(scenarios.probability, 1 / count, rtol=0, atol=1e-12):
            raise ValueError(f"{context}: raw_equal requires equal probabilities")


class RollingScenarioBuilder:
    def __init__(self, annual, forecasts, method="raw_equal"):
        if method not in cfg.SCENARIO_METHODS:
            raise ValueError(f"scenario_builder: unknown method {method!r}")
        self.annual = annual
        self.forecasts = forecasts
        self.method = method
        self.date_index = {day: i for i, day in enumerate(annual.dates)}
        self.errors = HistoricalErrors(annual, forecasts)

    def build(self, target_date, issue_hour, method=None) -> RollingScenarios:
        index = self.date_index[target_date]
        if issue_hour not in cfg.ISSUE_HOURS or index < cfg.HISTORY_WINDOW_DAYS:
            raise ValueError(f"{target_date} {issue_hour}: scenario_builder: invalid issue or insufficient history")
        selected = self.method if method is None else method
        if selected not in cfg.SCENARIO_METHODS:
            raise ValueError(f"{target_date} {issue_hour}: scenario_builder: unknown method {selected!r}")
        start = cfg.ISSUE_SLOT[issue_hour]
        # 唯一读取的目标日实际值：当前时刻之前最后一个已结束slot。
        anchor = self.annual.pv_kw[index, start - 1] if start else 0.0
        issue = self.forecasts[target_date].issues[issue_hour]
        target_forecast = interpolate_hourly_pv_forecast(issue.hourly_power_kw, issue_hour, anchor)
        history_indexes = np.arange(index - cfg.HISTORY_WINDOW_DAYS, index)
        if selected == "paired_residual_weighted":
            # 1月1日没有更早的附件2负荷，无法构造伪实时负荷残差。
            history_indexes = history_indexes[history_indexes > 0]
        history = tuple(self.annual.dates[int(i)] for i in history_indexes)
        errors = np.array([self.errors.get(day, issue_hour, before=target_date) for day in history])
        pv = np.maximum(target_forecast + errors, 0)
        if selected == "raw_equal":
            target_load = forecast_load(self.annual, index)[start:]
            load = self.annual.load_kw[history_indexes, start:]
            probability = np.full(len(history_indexes), 1 / len(history_indexes))
        else:
            target_load = forecast_load(self.annual, index)[start:]
            load = np.array([
                np.maximum(
                    target_load + self.annual.load_kw[history_index, start:]
                    - forecast_load(self.annual, int(history_index))[start:],
                    0,
                )
                for history_index in history_indexes
            ])
            probability = compute_scenario_weights(self.annual, index, history_indexes)
        scenarios = RollingScenarios(
            target_date, issue_hour, history, readonly(target_forecast), readonly(pv),
            readonly((load - pv) * cfg.TIME_STEP_HOURS), readonly(probability),
            readonly(target_load), readonly(load), selected,
        )
        validate_scenarios(scenarios)
        return scenarios
