"""问题2滚动历史、星期趋势校正与伪实时预测误差场景。"""
from datetime import timedelta
import numpy as np

from . import config as cfg
from .forecast import (
    build_weekday_load_profile,
    forecast_load,
    forecast_load_weekday_trend,
    forecast_pv,
    historical_pseudo_forecast,
)
from .types import AnnualActualData, ScenarioSet, readonly


SCENARIO_METHODS = (
    "raw_equal",
    "weekday_corrected",
    "weekday_trend_corrected",
    "weekday_trend_weighted",
    "level_scaled",
    "residual_equal",
    "residual_weighted",
)


def validate_scenarios(scenarios: ScenarioSet) -> None:
    prefix = f"{scenarios.target_date}: scenario_builder"
    if scenarios.method not in SCENARIO_METHODS:
        raise ValueError(f"{prefix}: unknown method {scenarios.method!r}")
    count = len(scenarios.history_dates)
    if not count or scenarios.net_load_kwh.shape != (count, cfg.N_SLOTS):
        raise ValueError(f"{prefix}: invalid scenario matrix")
    if not np.isfinite(scenarios.net_load_kwh).all():
        raise ValueError(f"{prefix}: scenario matrix contains NaN / Inf")
    earliest = scenarios.target_date - timedelta(days=cfg.HISTORY_WINDOW_DAYS)
    if (tuple(sorted(scenarios.history_dates)) != scenarios.history_dates
            or len(set(scenarios.history_dates)) != count
            or any(day < earliest or day >= scenarios.target_date for day in scenarios.history_dates)):
        raise ValueError(f"{prefix}: history must be inside the preceding 31 days; no lookahead allowed")
    probability = scenarios.probability
    if (probability.shape != (count,) or not np.isfinite(probability).all()
            or (probability <= 0).any() or not np.isclose(probability.sum(), 1, rtol=0, atol=1e-12)):
        raise ValueError(f"{prefix}: invalid scenario probabilities")
    if scenarios.method == "raw_equal":
        expected = tuple(scenarios.target_date - timedelta(days=i)
                         for i in range(cfg.HISTORY_WINDOW_DAYS, 0, -1))
        if scenarios.history_dates != expected:
            raise ValueError(f"{prefix}: raw history must be exactly the preceding 31 days; no lookahead allowed")
        if not np.allclose(probability, 1 / count, rtol=0, atol=1e-12):
            raise ValueError(f"{prefix}: raw_equal requires equal scenario probabilities")
    for name, values in (("load_kw", scenarios.load_kw), ("pv_kw", scenarios.pv_kw)):
        if values is None or values.shape != (count, cfg.N_SLOTS) or not np.isfinite(values).all() or (values < 0).any():
            raise ValueError(f"{prefix}: invalid {name} scenarios")
    rebuilt = (scenarios.load_kw - scenarios.pv_kw) * cfg.TIME_STEP_HOURS
    if np.max(np.abs(rebuilt - scenarios.net_load_kwh)) > cfg.RESIDUAL_TOL:
        raise ValueError(f"{prefix}: load/PV and net-load scenarios differ")


def _target_and_history(annual_data: AnnualActualData, target_index: int) -> tuple[int, np.ndarray]:
    if not cfg.HISTORY_WINDOW_DAYS <= target_index < len(annual_data.dates):
        raise ValueError(f"scenario_builder: target index {target_index} lacks 31 days of history or is out of range")
    return target_index, np.arange(target_index - cfg.HISTORY_WINDOW_DAYS, target_index)


def _make_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
    history_indexes: np.ndarray,
    load_kw: np.ndarray,
    pv_kw: np.ndarray,
    probability: np.ndarray,
    method: str,
) -> ScenarioSet:
    if np.any(history_indexes >= target_index):
        raise ValueError("scenario_builder: target/future index reached scenario construction")
    scenarios = ScenarioSet(
        annual_data.dates[target_index],
        tuple(annual_data.dates[int(index)] for index in history_indexes),
        readonly((load_kw - pv_kw) * cfg.TIME_STEP_HOURS),
        readonly(probability),
        method,
        readonly(load_kw),
        readonly(pv_kw),
    )
    validate_scenarios(scenarios)
    return scenarios


def compute_scenario_weights(
    annual_data: AnnualActualData,
    target_index: int,
    history_indexes: np.ndarray,
    recency_tau_days=cfg.RECENCY_TAU_DAYS,
    same_weekday_weight=cfg.SAME_WEEKDAY_WEIGHT,
) -> np.ndarray:
    if np.any(history_indexes >= target_index):
        raise ValueError("scenario_builder: weights received target/future history")
    if not np.isfinite(recency_tau_days) or recency_tau_days <= 0:
        raise ValueError("scenario_builder: recency tau must be positive")
    if not np.isfinite(same_weekday_weight) or same_weekday_weight <= 0:
        raise ValueError("scenario_builder: weekday weight must be positive")
    ages = target_index - history_indexes
    weights = np.exp(-ages / recency_tau_days)
    target_weekday = annual_data.dates[target_index].weekday()
    weekdays = np.array([annual_data.dates[int(index)].weekday() for index in history_indexes])
    weights *= np.where(weekdays == target_weekday, same_weekday_weight, 1.0)
    weights /= weights.sum()
    return readonly(weights)


def build_rolling_scenarios(annual_data: AnnualActualData, target_index: int) -> ScenarioSet:
    """A0原始基线：严格前31天绝对曲线、等概率。"""
    _, indexes = _target_and_history(annual_data, target_index)
    return _make_scenarios(
        annual_data,
        target_index,
        indexes,
        annual_data.load_kw[indexes],
        annual_data.pv_kw[indexes],
        np.full(len(indexes), 1 / len(indexes)),
        "raw_equal",
    )


def _weekday_profile_excluding(
    annual_data: AnnualActualData,
    target_index: int,
    weekday: int,
    excluded_index: int,
) -> np.ndarray:
    candidates = [index for index in range(target_index)
                  if index != excluded_index and annual_data.dates[index].weekday() == weekday]
    if not candidates:
        candidates = [index for index in range(target_index) if index != excluded_index]
    candidates = candidates[-len(cfg.WEEKDAY_LAG_WEIGHTS):][::-1]
    weights = np.asarray(cfg.WEEKDAY_LAG_WEIGHTS[:len(candidates)], dtype=float)
    weights /= weights.sum()
    return weights @ annual_data.load_kw[candidates]


def _corrected_load_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
    beta: float,
) -> tuple[np.ndarray, np.ndarray]:
    _, indexes = _target_and_history(annual_data, target_index)
    center = (build_weekday_load_profile(annual_data, target_index) if beta == 0 else
              forecast_load_weekday_trend(annual_data, target_index, beta))
    corrected = []
    for history_index in indexes:
        weekday = annual_data.dates[int(history_index)].weekday()
        historical_center = _weekday_profile_excluding(
            annual_data, target_index, weekday, int(history_index)
        )
        residual = annual_data.load_kw[history_index] - historical_center
        corrected.append(np.maximum(center + residual, 0))
    return indexes, np.asarray(corrected)


def build_weekday_corrected_load_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
) -> ScenarioSet:
    indexes, load = _corrected_load_scenarios(annual_data, target_index, beta=0)
    return _make_scenarios(annual_data, target_index, indexes, load, annual_data.pv_kw[indexes],
                           np.full(len(indexes), 1 / len(indexes)), "weekday_corrected")


def build_weekday_trend_corrected_load_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
    weighted=False,
) -> ScenarioSet:
    indexes, load = _corrected_load_scenarios(annual_data, target_index, cfg.LOAD_TREND_BETA)
    probability = (compute_scenario_weights(annual_data, target_index, indexes) if weighted else
                   np.full(len(indexes), 1 / len(indexes)))
    method = "weekday_trend_weighted" if weighted else "weekday_trend_corrected"
    return _make_scenarios(annual_data, target_index, indexes, load, annual_data.pv_kw[indexes],
                           probability, method)


def build_level_scaled_load_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
) -> ScenarioSet:
    _, indexes = _target_and_history(annual_data, target_index)
    target_energy = float(forecast_load_weekday_trend(annual_data, target_index).sum())
    history_energy = annual_data.load_kw[indexes].sum(axis=1)
    ratio = np.clip(target_energy / history_energy, cfg.LEVEL_SCALE_MIN, cfg.LEVEL_SCALE_MAX)
    load = annual_data.load_kw[indexes] * ratio[:, None]
    return _make_scenarios(annual_data, target_index, indexes, load, annual_data.pv_kw[indexes],
                           np.full(len(indexes), 1 / len(indexes)), "level_scaled")


def build_residual_scenarios(
    annual_data: AnnualActualData,
    target_index: int,
    weighted=False,
) -> ScenarioSet:
    _, raw_indexes = _target_and_history(annual_data, target_index)
    # 2025-01-01没有更早附件2历史，不能构造其伪实时误差，故仅在窗口含index=0时排除它。
    indexes = raw_indexes[raw_indexes > 0]
    target_load = forecast_load(annual_data, target_index)
    target_pv = forecast_pv(annual_data, target_index)
    load_scenarios, pv_scenarios = [], []
    for history_index in indexes:
        pseudo_load, pseudo_pv = historical_pseudo_forecast(annual_data, int(history_index))
        load_scenarios.append(np.maximum(
            target_load + annual_data.load_kw[history_index] - pseudo_load, 0
        ))
        pv_scenarios.append(np.maximum(
            target_pv + annual_data.pv_kw[history_index] - pseudo_pv, 0
        ))
    probability = (compute_scenario_weights(annual_data, target_index, indexes) if weighted else
                   np.full(len(indexes), 1 / len(indexes)))
    method = "residual_weighted" if weighted else "residual_equal"
    return _make_scenarios(annual_data, target_index, indexes, np.asarray(load_scenarios),
                           np.asarray(pv_scenarios), probability, method)


def build_scenarios(annual_data: AnnualActualData, target_index: int, method=cfg.SCENARIO_METHOD) -> ScenarioSet:
    builders = {
        "raw_equal": build_rolling_scenarios,
        "weekday_corrected": build_weekday_corrected_load_scenarios,
        "weekday_trend_corrected": build_weekday_trend_corrected_load_scenarios,
        "weekday_trend_weighted": lambda data, index: build_weekday_trend_corrected_load_scenarios(data, index, True),
        "level_scaled": build_level_scaled_load_scenarios,
        "residual_equal": build_residual_scenarios,
        "residual_weighted": lambda data, index: build_residual_scenarios(data, index, True),
    }
    if method not in builders:
        raise ValueError(f"scenario_builder: unknown method {method!r}")
    return builders[method](annual_data, target_index)
