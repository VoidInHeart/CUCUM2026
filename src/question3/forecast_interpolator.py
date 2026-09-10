"""在区间中点采样，从当前已观测锚点线性插值至未来整点。"""
import numpy as np

from . import config as cfg


def interpolate_hourly_pv_forecast(hourly_forecast_kw: np.ndarray, issue_hour: int,
                                   current_observed_pv_kw: float, end_hour: int = 24) -> np.ndarray:
    if issue_hour not in cfg.ISSUE_HOURS or not issue_hour < end_hour <= 24:
        raise ValueError("forecast_interpolator: invalid issue/end hour")
    values = np.asarray(hourly_forecast_kw, dtype=float)
    if values.shape != (24,) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("forecast_interpolator: expected 24 finite nonnegative hourly values")
    if not np.isfinite(current_observed_pv_kw) or current_observed_pv_kw < 0:
        raise ValueError("forecast_interpolator: invalid observed anchor")
    offsets = (np.arange(6 * (end_hour - issue_hour)) + 0.5) * cfg.TIME_STEP_HOURS
    return np.interp(offsets, np.arange(25), np.r_[current_observed_pv_kw, values])
