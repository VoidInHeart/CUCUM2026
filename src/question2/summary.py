"""全年指标、逐日指标与论文表1/2/3结构化摘要。"""
from dataclasses import asdict
import numpy as np

from ..question1.summary import TABLE1_LABELS, build_table2_summary
from . import config as cfg
from .emergency import merge_emergency_intervals, validate_labels
from .types import DailyEvaluation

METRICS = ("planned_grid_total", "emergency_total", "total_grid_purchase",
           "planned_cost", "emergency_cost", "total_cost")


def daily_metrics(item: DailyEvaluation) -> dict:
    return {"date": item.plan.date.isoformat(), **{name: getattr(item, name) for name in METRICS},
            "surplus_kwh": float(item.surplus_kwh.sum()),
            "scenario_method": item.scenario_method,
            "mean_scenario_load_kwh": item.mean_scenario_load_kwh,
            "p80_scenario_load_kwh": item.p80_scenario_load_kwh,
            "actual_load_kwh": item.actual_load_kwh,
            "scenario_mean_bias_kwh": item.scenario_mean_bias_kwh,
            "scenario_p80_coverage": item.scenario_p80_coverage}


def _strategy_metrics(evaluations: list[DailyEvaluation]) -> dict:
    totals = {name: float(sum(getattr(item, name) for item in evaluations)) for name in METRICS}
    totals.update({
        "surplus_kwh": float(sum(item.surplus_kwh.sum() for item in evaluations)),
        "emergency_days": sum(bool(np.any(item.emergency_kwh > cfg.EMERGENCY_TOL)) for item in evaluations),
        "max_daily_emergency_kwh": max(item.emergency_total for item in evaluations),
        "max_daily_total_cost": max(item.total_cost for item in evaluations),
    })
    if all(item.mean_scenario_load_kwh is not None for item in evaluations):
        totals.update({
            "mean_scenario_load_kwh": float(sum(item.mean_scenario_load_kwh for item in evaluations)),
            "p80_scenario_load_kwh": float(sum(item.p80_scenario_load_kwh for item in evaluations)),
            "actual_load_kwh": float(sum(item.actual_load_kwh for item in evaluations)),
            "scenario_mean_bias_kwh": float(sum(item.scenario_mean_bias_kwh for item in evaluations)),
            "scenario_p80_coverage": float(np.mean([item.scenario_p80_coverage for item in evaluations])),
        })
    return totals


def build_ablation_summary(results: dict[str, list[DailyEvaluation]]) -> dict:
    """A0—A8年度结算及相对基线变化；排序只使用真实结算总费用。"""
    if "baseline" not in results or not results:
        raise ValueError("question2 ablation: baseline is required")
    baseline = _strategy_metrics(results["baseline"])
    strategies = []
    labels = {"baseline": "A0", "causal_mpc": "A1", "weekday_corrected": "A2",
              "weekday_trend_corrected": "A3", "weekday_trend_weighted": "A4",
              "residual_equal": "A5", "weekday_trend_causal": "A6",
              "residual_weighted_causal": "A7", "level_scaled": "level-scale"}
    labels["grid_recourse_residual_causal"] = "A8"
    for name, evaluations in results.items():
        values = _strategy_metrics(evaluations)
        values.update({
            "strategy": name,
            "ablation": labels.get(name, name),
            "delta_total_cost_vs_A0": values["total_cost"] - baseline["total_cost"],
            "saving_vs_A0": baseline["total_cost"] - values["total_cost"],
            "saving_ratio_vs_A0": ((baseline["total_cost"] - values["total_cost"]) / baseline["total_cost"]),
            "delta_plan_cost": values["planned_cost"] - baseline["planned_cost"],
            "delta_emergency_cost": values["emergency_cost"] - baseline["emergency_cost"],
        })
        strategies.append(values)
    return {
        "experiment": "Question2 A0-A8 causal-control and no-lookahead scenario ablation",
        "period": f"{cfg.START_DATE} ~ {cfg.END_DATE}",
        "ranking_metric": "actual settlement total_cost",
        "deferred_ablations": [{
            "ablation": "A9",
            "status": "gated_out",
            "reason": "A9 is low priority and depends on A8; A8 was 1,447,369.14 yuan worse than A7",
        }],
        "strategies": strategies,
        "selected_strategy": min(strategies, key=lambda item: item["total_cost"])["strategy"],
    }


def build_summaries(evaluations: list[DailyEvaluation], labels: list[str]) -> dict:
    validate_labels(labels)
    index = {label: i for i, label in enumerate(labels)}
    missing = set(TABLE1_LABELS) - index.keys()
    if missing:
        raise ValueError(f"summary: official template missing paper labels: {sorted(missing)}")
    annual = {name: float(sum(getattr(item, name) for item in evaluations)) for name in METRICS}
    annual["period"] = f"{cfg.START_DATE} ~ {cfg.END_DATE}"
    annual["emergency_days"] = sum(bool(np.any(item.emergency_kwh > cfg.EMERGENCY_TOL)) for item in evaluations)
    annual["emergency_intervals"] = sum(len(merge_emergency_intervals(labels, item.emergency_kwh)) for item in evaluations)
    annual["emergency_energy_ratio"] = annual["emergency_total"] / annual["total_grid_purchase"] if annual["total_grid_purchase"] else 0.0
    annual["emergency_cost_ratio"] = annual["emergency_cost"] / annual["total_cost"] if annual["total_cost"] else 0.0
    annual["daily_mean_emergency_kwh"] = annual["emergency_total"] / len(evaluations)
    annual["max_daily_emergency_kwh"] = max(item.emergency_total for item in evaluations)
    annual["max_daily_total_cost"] = max(item.total_cost for item in evaluations)
    paper = {}
    for item in evaluations:
        if item.plan.date not in cfg.PAPER_DATES:
            continue
        table1 = {}
        for label in TABLE1_LABELS:
            t = index[label]
            planned, emergency = float(item.plan.grid_kwh[t]), float(item.emergency_kwh[t])
            table1[label] = {"计划购电量": planned, "实际紧急购电量": emergency, "合计": planned + emergency}
        paper[item.plan.date.isoformat()] = {
            "表1": table1, "全天指标": daily_metrics(item),
            "表2": build_table2_summary(item.plan.charge_kwh, item.plan.discharge_kwh),
            "表3": [asdict(event) for event in merge_emergency_intervals(labels, item.emergency_kwh)],
        }
    if len(paper) != len(cfg.PAPER_DATES):
        raise ValueError("summary: missing specified paper dates")
    return {"units": {"energy": "kWh", "cost": "yuan", "ratios": "0..1"},
            "annual": annual, "paper_dates": paper}
