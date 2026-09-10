"""历史误差按需缓存，任何历史误差查询必须显式给出信息截止日期。"""
from datetime import date

from ..question2.types import AnnualActualData
from . import config as cfg
from .forecast_interpolator import interpolate_hourly_pv_forecast
from .types import DailyPVForecast, readonly


class HistoricalErrors:
    def __init__(self, annual: AnnualActualData, forecasts: dict[date, DailyPVForecast]):
        self.annual = annual
        self.forecasts = forecasts
        self.date_index = {day: i for i, day in enumerate(annual.dates)}
        self._cache = {}

    def get(self, historical_date: date, issue_hour: int, *, before: date):
        if historical_date >= before:
            raise ValueError(f"{before} {issue_hour}: forecast_error: history must precede target date")
        key = (historical_date, issue_hour)
        if key not in self._cache:
            index = self.date_index[historical_date]
            start = cfg.ISSUE_SLOT[issue_hour]
            anchor = self.annual.pv_kw[index, start - 1] if start else 0.0
            forecast = interpolate_hourly_pv_forecast(
                self.forecasts[historical_date].issues[issue_hour].hourly_power_kw, issue_hour, anchor)
            self._cache[key] = readonly(self.annual.pv_kw[index, start:] - forecast)
        return self._cache[key]
