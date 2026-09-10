"""正式策略年度指标和论文表1/2/3；调整费用保留退款负号。"""
from dataclasses import asdict
import numpy as np

from ..question1.summary import TABLE1_LABELS, build_table2_summary
from ..question2.emergency import merge_emergency_intervals
from . import config as cfg
from .analysis import daily_metrics


def build_summary(results, labels):
    label_to_index = {label: i for i, label in enumerate(labels)}
    if set(TABLE1_LABELS) - label_to_index.keys():
        raise ValueError("question3 summary: paper interval missing from template")
    rows = [daily_metrics(result) for result in results]
    annual = {key: float(sum(row[key] for row in rows)) for key in rows[0] if key != "date"}
    annual["period"] = f"{cfg.START_DATE} ~ {cfg.END_DATE}"
    annual["emergency_days"] = sum(bool(np.any(result.real_emergency > cfg.EMERGENCY_TOL)) for result in results)
    annual["emergency_intervals"] = sum(len(merge_emergency_intervals(labels, result.real_emergency)) for result in results)
    papers = {}
    for result in results:
        s = result.schedule
        if s.date not in cfg.PAPER_DATES:
            continue
        table1 = {}
        for label in TABLE1_LABELS:
            index = label_to_index[label]
            table1[label] = {"初始计划购电量": float(s.initial_plan.grid_kwh[index]),
                             "执行合同购电量": float(s.executed_grid[index]),
                             "紧急购电量": float(result.real_emergency[index]),
                             "实际外网购电量": float(s.executed_grid[index] + result.real_emergency[index])}
        papers[str(s.date)] = {"表1": table1, "全天指标": daily_metrics(result),
                               "表2": build_table2_summary(s.executed_charge, s.executed_discharge),
                               "表3": [asdict(event) for event in merge_emergency_intervals(labels, result.real_emergency)],
                               "调整交易": [{"issue_hour": r.issue_hour, "cashflow_yuan": r.adjustment_cashflow_yuan,
                                             "up_kwh": float(r.up_adjust.sum()), "down_kwh": float(r.down_adjust.sum())} for r in s.revisions]}
    if len(papers) != 4:
        raise ValueError("question3 summary: missing specified dates")
    return {"units": {"energy": "kWh", "cost": "yuan", "power": "kW"}, "annual": annual, "paper_dates": papers}
