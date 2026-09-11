"""仅对冻结后的实际日结果计算统计量，不向优化器传递评价指标。"""
from dataclasses import asdict
import numpy as np

from .config import OUTPUT_DATES


def empirical_cvar(values, alpha=0.95, probability=None):
    """离散分布最差1-alpha概率质量的均值，边界样本按剩余质量计入。"""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all() or not 0 < alpha < 1:
        raise ValueError("CVaR requires finite nonempty 1D values and 0 < alpha < 1")
    p = np.full(values.size, 1 / values.size) if probability is None else np.asarray(probability, dtype=float)
    if p.shape != values.shape or not np.isfinite(p).all() or (p < 0).any() or not np.isclose(p.sum(), 1, rtol=0, atol=1e-12):
        raise ValueError("invalid CVaR probabilities")
    order = np.argsort(values)[::-1]
    mass = p[order]
    before = np.r_[0.0, np.cumsum(mass)[:-1]]
    weights = np.minimum(mass, np.maximum(1 - alpha - before, 0))
    return float(weights @ values[order] / (1 - alpha))


def summarize(run):
    if tuple(row.date for row in run.daily) != tuple(map(str, OUTPUT_DATES)):
        raise ValueError("benchmark metrics require all 334 output dates")
    rows = [asdict(row) for row in run.daily]
    sums = ("plan_cost", "adjustment_cost", "contract_cost", "emergency_cost", "total_cost",
            "planned_grid_kwh", "contract_grid_kwh", "emergency_kwh", "total_grid_kwh",
            "charge_kwh", "discharge_kwh", "throughput_kwh")
    result = {"method": run.method, "days": len(rows),
              **{key: float(sum(row[key] for row in rows)) for key in sums},
              "emergency_days": sum(row["emergency_day"] for row in rows)}
    costs = np.array([row["total_cost"] for row in rows])
    emergencies = np.array([row["emergency_kwh"] for row in rows])
    result.update(mean_daily_cost=float(costs.mean()), max_daily_cost=float(costs.max()),
                  p95_daily_cost=float(np.quantile(costs, 0.95, method="linear")),
                  cvar95_daily_cost=empirical_cvar(costs),
                  p95_daily_emergency_kwh=float(np.quantile(emergencies, 0.95, method="linear")),
                  cvar95_daily_emergency_kwh=empirical_cvar(emergencies),
                  total_runtime_seconds=run.total_runtime_seconds,
                  mean_runtime_per_day_ms=1000 * run.total_runtime_seconds / len(rows))
    return result


def add_relative_changes(rows, references=None):
    """变化率=(方法-基线)/基线；零分母或缺失基线为None，负值表示减少。"""
    reference = {row["method"]: row for row in (references if references is not None else rows)}
    output = []
    for row in rows:
        out = dict(row)
        for name in ("SAA", "DET"):
            base = reference.get(name)
            for key, value in row.items():
                if key in ("days", "alpha", "lambda") or not isinstance(value, (float, int)):
                    continue
                denom = base.get(key) if base else None
                out[f"{key}_change_vs_{name.lower()}_pct"] = 100 * (value - denom) / denom if denom else None
        output.append(out)
    return output
