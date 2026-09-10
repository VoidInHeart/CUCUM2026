"""公平比较同一334天的更新策略；预测精度是离线评价，不回流优化器。"""
import logging
import numpy as np

from . import config as cfg
from .rolling_controller import solve_day, validate_policy
from .evaluator import evaluate_actual_day
from .validator import validate_complete
from .forecast_interpolator import interpolate_hourly_pv_forecast
from ..pricing import price_for_date


def policy_name(hours):
    return "+".join(str(hour) for hour in hours)


def evaluate_update_policy(update_hours, price, annual, builder):
    validate_policy(update_hours)
    results = []
    for i, target in enumerate(cfg.OUTPUT_DATES):
        try:
            daily_price = price_for_date(price, target)
            schedule = solve_day(target, daily_price, builder, update_hours)
            actual = annual.net_load_kwh[builder.date_index[target]]
            result = evaluate_actual_day(daily_price, schedule, actual, update_hours)
        except Exception as exc:
            raise RuntimeError(f"{target} policy {policy_name(update_hours)} failed: {exc}") from exc
        results.append(result)
        logging.info("[%03d/334] policy=%s %s solved %s: price_mean=%.4f emergency=%.3f adjustment_cost=%.3f total_cost=%.3f",
                     i + 1, policy_name(update_hours), target, update_hours, daily_price.mean(), result.emergency_kwh,
                     result.adjustment_cost, result.total_cost)
    validate_complete(price, results, update_hours)
    return results


def daily_metrics(result):
    metrics = {name: getattr(result, name) for name in (
        "initial_plan_kwh", "executed_adjusted_kwh", "emergency_kwh", "actual_grid_energy_kwh",
        "plan_cost", "adjustment_cost", "emergency_cost", "total_cost")}
    metrics["up_adjust_kwh"] = float(sum(revision.up_adjust.sum() for revision in result.schedule.revisions))
    metrics["down_adjust_kwh"] = float(sum(revision.down_adjust.sum() for revision in result.schedule.revisions))
    return {"date": str(result.schedule.date), **metrics}


def summarize_policies(policy_results):
    summaries = []
    for hours, results in policy_results.items():
        rows = [daily_metrics(result) for result in results]
        totals = {key: float(sum(row[key] for row in rows)) for key in rows[0] if key != "date"}
        summaries.append({"policy": policy_name(hours), **totals})
    baseline = next(row for row in summaries if row["policy"] == "0")["total_cost"]
    for row in summaries:
        row["savings_vs_0_yuan"] = baseline - row["total_cost"]
        row["savings_vs_0_ratio"] = (baseline - row["total_cost"]) / baseline if baseline else 0.0
    return summaries


def forecast_accuracy(annual, forecasts):
    results = []
    for hour in cfg.ISSUE_HOURS:
        errors = []
        start = cfg.ISSUE_SLOT[hour]
        for index in range(cfg.HISTORY_WINDOW_DAYS, len(annual.dates)):
            target = annual.dates[index]
            anchor = annual.pv_kw[index, start - 1] if start else 0.0
            prediction = interpolate_hourly_pv_forecast(forecasts[target].issues[hour].hourly_power_kw, hour, anchor)
            errors.append(annual.pv_kw[index, start:] - prediction)
        values = np.concatenate(errors)
        # 对18—24时段另给相同剩余时域指标，避免把不同长度误差简单等同。
        common = np.concatenate([values[-36:] for values in errors])
        results.append({"issue_hour": hour, "samples": int(values.size), "MAE_kW": float(np.mean(np.abs(values))),
                        "RMSE_kW": float(np.sqrt(np.mean(values ** 2))), "common_18_24_samples": int(common.size),
                        "common_18_24_MAE_kW": float(np.mean(np.abs(common))),
                        "common_18_24_RMSE_kW": float(np.sqrt(np.mean(common ** 2)))})
    return results
