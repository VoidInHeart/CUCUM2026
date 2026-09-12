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
    return {"date": item.plan.date.isoformat(), **{name: getattr(item, name) for name in METRICS}}


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
        paper[item.plan.date.isoformat()]["表2"].update({"0:00 储电量": item.plan.initial_soc_kwh,
                                                   "24:00 储电量": item.plan.terminal_soc_kwh})
    if len(paper) != len(cfg.PAPER_DATES):
        raise ValueError("summary: missing specified paper dates")
    return {"units": {"energy": "kWh", "cost": "yuan", "ratios": "0..1"},
            "annual": annual, "paper_dates": paper}
