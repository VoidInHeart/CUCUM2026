"""离线价格统计与同策略固定/动态电价比较，不参与场景或优化器。"""
from dataclasses import replace
import numpy as np

from . import config as cfg
from .price_loader import get_daily_price


def fixed_price_baseline(model, prices, actual, builder=None):
    # 附件1只在离线固定价基线中使用，不是第四问正式模型的输入。
    from ..question2.data_loader import load_price
    from . import question4_2, question4_3
    fixed = load_price().price
    constant = replace(prices, price_yuan_per_kwh=np.tile(fixed, (365, 1)))
    results = (question4_2.run_annual(constant, actual) if model == "4-2" else
               question4_3.run_annual(constant, actual, builder))
    return constant, results


def daily_metrics(model, prices, results):
    rows = []
    for r in results:
        if model == "4-2":
            day = r.plan.date
            initial = executed = r.planned_grid_total
            emergency, total_grid = r.emergency_total, r.total_grid_purchase
            charge, discharge = r.plan.charge_kwh, r.plan.discharge_kwh
            plan_cost, adjustment = r.planned_cost, 0.0
            emergency_values = r.emergency_kwh
            up = down = 0.0
        else:
            day = r.schedule.date
            initial, executed = r.initial_plan_kwh, r.executed_adjusted_kwh
            emergency, total_grid = r.emergency_kwh, r.actual_grid_energy_kwh
            charge, discharge = r.schedule.executed_charge, r.schedule.executed_discharge
            plan_cost, adjustment = r.plan_cost, r.adjustment_cost
            emergency_values = r.real_emergency
            up = float(sum(v.up_adjust.sum() for v in r.schedule.revisions))
            down = float(sum(v.down_adjust.sum() for v in r.schedule.revisions))
        q = get_daily_price(prices, day)
        rows.append({"date": str(day), "initial_plan_kwh": initial, "executed_grid_kwh": executed,
                     "emergency_kwh": emergency, "total_grid_kwh": total_grid,
                     "plan_cost": plan_cost, "adjustment_cost": adjustment, "emergency_cost": r.emergency_cost,
                     "total_cost": r.total_cost, "charge_kwh": float(charge.sum()), "discharge_kwh": float(discharge.sum()),
                     "battery_throughput_kwh": float(charge.sum()+discharge.sum()),
                     "up_adjust_kwh": up, "down_adjust_kwh": down,
                     "emergency_day": int(np.any(emergency_values > 1e-6)),
                     "price_mean": float(q.mean()), "price_min": float(q.min()), "price_max": float(q.max()),
                     "price_range": float(np.ptp(q)), "price_std": float(q.std())})
    return rows


def annual_metrics(rows):
    totals = {key: float(sum(row[key] for row in rows)) for key in rows[0] if key not in ("date",) and not key.startswith("price_")}
    totals["days"] = len(rows)
    totals["max_daily_cost"] = max(row["total_cost"] for row in rows)
    totals["mean_price"] = float(np.mean([row["price_mean"] for row in rows]))
    return totals


def compare(model, dynamic_rows, fixed_rows):
    if tuple(row["date"] for row in dynamic_rows) != tuple(map(str, cfg.OUTPUT_DATES)) or \
            tuple(row["date"] for row in dynamic_rows) != tuple(row["date"] for row in fixed_rows):
        raise ValueError("comparison: expected identical 334 dates")
    dynamic, fixed = annual_metrics(dynamic_rows), annual_metrics(fixed_rows)
    changes = [{"metric": key, "fixed_price": fixed[key], "dynamic_price": dynamic[key],
                "absolute_change": dynamic[key]-fixed[key],
                "relative_change": (dynamic[key]-fixed[key])/fixed[key] if fixed[key] else None}
               for key in fixed]
    x = np.array([row["price_range"] for row in dynamic_rows])
    correlations = {}
    for key in ("battery_throughput_kwh", "total_cost", "emergency_cost"):
        y = np.array([row[key] for row in dynamic_rows])
        correlations[key] = float(np.corrcoef(x, y)[0, 1]) if x.std() and y.std() else None
    return {"model": model, "period": "2025-02-01 ~ 2025-12-31", "days": 334,
            "update_hours": [0] if model == "4-2" else list(cfg.Q4_3_UPDATE_HOURS),
            "baseline": ("Q2 A7 fixed price" if model == "4-2" else
                         "Q3 paired-residual causal fixed price, policy 0+6+12"),
            "scenario_method": (cfg.Q4_2_STRATEGY if model == "4-2" else
                                cfg.Q4_3_SCENARIO_METHOD),
            "storage_execution": cfg.Q4_STORAGE_EXECUTION,
            "price_assumption": "Attachment 4 full target-day settlement curve is given; no price prediction",
            "fixed_price": fixed, "dynamic_price": dynamic, "changes": changes,
            "price_range_pearson_correlation": correlations,
            "correlation_note": "Descriptive correlation only, not a causal effect of price range"}
