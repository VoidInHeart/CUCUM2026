"""保留历史负载与同日误差的配对；仅访问当前发布的目标日预报。"""
from datetime import timedelta
import numpy as np

from . import config as cfg
from .forecast_error import HistoricalErrors
from .forecast_interpolator import interpolate_hourly_pv_forecast
from .types import RollingScenarios, readonly


def validate_scenarios(scenarios: RollingScenarios) -> None:
    context = f"{scenarios.target_date} {scenarios.issue_hour}: scenario_builder"
    if scenarios.issue_hour not in cfg.ISSUE_HOURS:
        raise ValueError(f"{context}: invalid issue hour")
    expected = tuple(scenarios.target_date - timedelta(days=i) for i in range(31, 0, -1))
    if scenarios.history_dates != expected:
        raise ValueError(f"{context}: expected preceding 31 calendar days, no lookahead")
    continuous = scenarios.horizon_mode == "issue_relative"
    h, s = (144, 30) if continuous else (6 * (24 - scenarios.issue_hour), 31)
    if scenarios.horizon_mode not in ("calendar_day", "issue_relative"):
        raise ValueError("invalid horizon mode")
    for name, shape in (("forecast_kw", (h,)), ("pv_scenario_kw", (s, h)), ("net_load_kwh", (s, h)), ("probability", (s,))):
        values = getattr(scenarios, name)
        if values.shape != shape or not np.isfinite(values).all():
            raise ValueError(f"{context}: {name}: invalid shape or NaN / Inf")
    if (scenarios.pv_scenario_kw < 0).any() or (scenarios.forecast_kw < 0).any():
        raise ValueError(f"{context}: negative PV")
    if not np.allclose(scenarios.probability, 1 / s, rtol=0, atol=1e-12):
        raise ValueError(f"{context}: expected equal probabilities")


class RollingScenarioBuilder:
    def __init__(self, annual, forecasts):
        self.annual = annual
        self.forecasts = forecasts
        self.date_index = {day: i for i, day in enumerate(annual.dates)}
        self.errors = HistoricalErrors(annual, forecasts)

    def build(self, target_date, issue_hour, horizon_mode="calendar_day") -> RollingScenarios:
        index = self.date_index[target_date]
        if issue_hour not in cfg.ISSUE_HOURS or index < cfg.HISTORY_WINDOW_DAYS:
            raise ValueError(f"{target_date} {issue_hour}: scenario_builder: invalid issue or insufficient history")
        start = cfg.ISSUE_SLOT[issue_hour]
        # 唯一读取的目标日实际值：当前时刻之前最后一个已结束slot。
        anchor = self.annual.pv_kw[index, start - 1] if start else 0.0
        issue = self.forecasts[target_date].issues[issue_hour]
        if horizon_mode == "issue_relative":
            # 30 complete historical issue-relative trajectories within the past 31 days.
            # Exclude yesterday's issue: its next-day errors are not yet fully observed.
            offsets = (np.arange(144)+.5)/6
            prediction = lambda values, anchor: np.interp(offsets, np.arange(25), np.r_[anchor, values])
            target_forecast = prediction(issue.hourly_power_kw, anchor)
            loads, errors = [], []
            for j in range(index-31, index-1):
                historic_anchor = self.annual.pv_kw[j,start-1] if start else 0.
                historic_forecast = prediction(self.forecasts[self.annual.dates[j]].issues[issue_hour].hourly_power_kw, historic_anchor)
                historical_pv = self.annual.pv_kw[j:j+2].ravel()[start:start+144]
                loads.append(self.annual.load_kw[j:j+2].ravel()[start:start+144])
                errors.append(historical_pv-historic_forecast)
            pv = np.maximum(target_forecast+np.asarray(errors), 0)
            scenarios = RollingScenarios(target_date, issue_hour, self.annual.dates[index-31:index],
                readonly(target_forecast), readonly(pv), readonly((np.asarray(loads)-pv)/6),
                readonly(np.full(30,1/30)), "issue_relative")
            validate_scenarios(scenarios)
            return scenarios
        if horizon_mode != "calendar_day":
            raise ValueError("unknown horizon mode")
        target_forecast = interpolate_hourly_pv_forecast(issue.hourly_power_kw, issue_hour, anchor)
        history = self.annual.dates[index - 31:index]
        errors = np.array([self.errors.get(day, issue_hour, before=target_date) for day in history])
        pv = np.maximum(target_forecast + errors, 0)
        load = self.annual.load_kw[index - 31:index, start:]
        scenarios = RollingScenarios(target_date, issue_hour, history, readonly(target_forecast), readonly(pv),
                                    readonly((load - pv) * cfg.TIME_STEP_HOURS), readonly(np.full(31, 1 / 31)))
        validate_scenarios(scenarios)
        return scenarios
