"""问题2只使用目标日前附件2历史的无泄漏负荷与光伏预测。"""
import numpy as np

from . import config as cfg
from .types import AnnualActualData, readonly


def _check_target(annual: AnnualActualData, target_index: int) -> None:
    if not 0 < target_index < len(annual.dates):
        raise ValueError(f"forecast: target index {target_index} must have prior history and be in range")


def _ewma(values: np.ndarray) -> np.ndarray:
    """对按时间升序排列的日曲线作标准span EWMA，最近一天权重最大。"""
    if values.ndim != 2 or not len(values):
        raise ValueError("forecast: EWMA requires at least one daily curve")
    alpha = 2.0 / (len(values) + 1.0)
    weights = (1.0 - alpha) ** np.arange(len(values) - 1, -1, -1)
    weights /= weights.sum()
    return weights @ values


def build_weekday_load_profile(
    annual: AnnualActualData,
    target_index: int,
    lag_weights=cfg.WEEKDAY_LAG_WEIGHTS,
) -> np.ndarray:
    """用d-7/14/21/28构造目标星期曲线，冷启动时只取已有同星期日。"""
    _check_target(annual, target_index)
    indexes, weights = [], []
    for lag_number, weight in enumerate(lag_weights, 1):
        index = target_index - 7 * lag_number
        if index >= 0:
            indexes.append(index)
            weights.append(weight)
    if not indexes:
        return readonly(_ewma(annual.load_kw[:target_index]))
    normalized = np.asarray(weights, dtype=float)
    normalized /= normalized.sum()
    return readonly(normalized @ annual.load_kw[indexes])


def compute_recent_load_trend(
    annual: AnnualActualData,
    target_index: int,
    short_days=cfg.LOAD_TREND_SHORT_DAYS,
    long_days=cfg.LOAD_TREND_LONG_DAYS,
) -> np.ndarray:
    """近期EWMA减长期EWMA；两个窗口都严格截止于target_index。"""
    _check_target(annual, target_index)
    if not 0 < short_days <= long_days:
        raise ValueError("forecast: trend windows must satisfy 0 < short <= long")
    short = annual.load_kw[max(0, target_index - short_days):target_index]
    long = annual.load_kw[max(0, target_index - long_days):target_index]
    return readonly(_ewma(short) - _ewma(long))


def forecast_load_weekday_trend(
    annual: AnnualActualData,
    target_index: int,
    beta=cfg.LOAD_TREND_BETA,
) -> np.ndarray:
    if not np.isfinite(beta) or beta < 0:
        raise ValueError("forecast: trend beta must be finite and nonnegative")
    profile = build_weekday_load_profile(annual, target_index)
    trend = compute_recent_load_trend(annual, target_index)
    return readonly(np.maximum(profile + beta * trend, 0))


def forecast_load(annual: AnnualActualData, target_index: int) -> np.ndarray:
    """星期形态与最近7天EWMA融合，供伪实时残差 bootstrap 使用。"""
    _check_target(annual, target_index)
    weekday = build_weekday_load_profile(annual, target_index)
    recent = _ewma(annual.load_kw[max(0, target_index - cfg.LOAD_TREND_SHORT_DAYS):target_index])
    alpha = cfg.LOAD_FORECAST_WEEKDAY_BLEND
    if not 0 <= alpha <= 1:
        raise ValueError("forecast: weekday blend must be in [0, 1]")
    return readonly(np.maximum(alpha * weekday + (1 - alpha) * recent, 0))


def forecast_pv(annual: AnnualActualData, target_index: int) -> np.ndarray:
    """无天气预报时使用最近7天逐slot中位数，稳健处理阴雨异常日。"""
    _check_target(annual, target_index)
    start = max(0, target_index - cfg.PV_FORECAST_WINDOW_DAYS)
    return readonly(np.median(annual.pv_kw[start:target_index], axis=0))


def forecast_net_load(annual: AnnualActualData, target_index: int) -> np.ndarray:
    return readonly((forecast_load(annual, target_index) - forecast_pv(annual, target_index)) * cfg.TIME_STEP_HOURS)


def historical_pseudo_forecast(
    annual: AnnualActualData,
    history_index: int,
) -> tuple[np.ndarray, np.ndarray]:
    """模拟站在历史日0:00的预测；history_index及之后的数据均不可见。"""
    return forecast_load(annual, history_index), forecast_pv(annual, history_index)
