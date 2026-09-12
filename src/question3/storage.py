"""结果存档用于复核与复画，不作为无校验的求解缓存。"""
from dataclasses import asdict
from datetime import date
from pathlib import Path
import csv
import json
import numpy as np

from .analysis import daily_metrics, policy_name
from .types import HorizonPlan, AdjustmentRevision, DailySchedule, DailyResult, readonly


def _json_default(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, date): return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value)}")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=_json_default), encoding="utf-8")


def write_csv(path, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_analysis(directory, main_results, policy_results, summary, ablations, accuracy):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_json(directory / "summary.json", summary)
    write_csv(directory / "ablation_summary.csv", ablations)
    write_json(directory / "ablation_summary.json", ablations)
    write_csv(directory / "forecast_accuracy.csv", accuracy)
    write_json(directory / "forecast_accuracy.json", accuracy)
    write_csv(directory / "policy_daily_metrics.csv", [
        {"policy": policy_name(hours), **daily_metrics(result)} for hours, results in policy_results.items() for result in results])
    save_daily_results(directory / "daily_results.jsonl", main_results)


def save_daily_results(path, results):
    """每行保留完整计划与结算；问题4也复用这一无损JSON记录格式。"""
    with Path(path).open("w", encoding="utf-8") as stream:
        for result in results:
            stream.write(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False, default=_json_default) + "\n")


def load_daily_results(path):
    """恢复问题3/4-3的不可变完整计划；调用者仍须验证价格及策略。"""
    def plan_from(record):
        return HorizonPlan(date.fromisoformat(record["date"]), record["issue_hour"], record["initial_soc_kwh"],
                           *(readonly(record[key]) for key in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh")),
                           record["solver_objective"], record["expected_emergency_kwh"])
    results = []
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            s = record["schedule"]
            revisions = tuple(AdjustmentRevision(r["issue_hour"], r["start_slot"], readonly(r["old_grid"]), plan_from(r["plan"]),
                                                  readonly(r["up_adjust"]), readonly(r["down_adjust"]), r["adjustment_cashflow_yuan"])
                              for r in s["revisions"])
            schedule = DailySchedule(plan_from(s["initial_plan"]), revisions, *(readonly(s[key]) for key in
                                      ("executed_grid", "executed_charge", "executed_discharge", "executed_soc_end")),
                                     s.get("storage_execution", "frozen"))
            results.append(DailyResult(schedule, *(readonly(record[key]) for key in ("actual_net_load", "real_emergency", "real_surplus")),
                                       *(record[key] for key in ("plan_cost", "adjustment_cost", "emergency_cost", "total_cost",
                                          "initial_plan_kwh", "executed_adjusted_kwh", "emergency_kwh", "actual_grid_energy_kwh"))))
    return results


def load_analysis(directory):
    """只用于重绘已保存结果，不用于继续或跳过优化。"""
    directory = Path(directory)
    results = load_daily_results(directory / "daily_results.jsonl")
    with (directory / "policy_daily_metrics.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return results, json.loads((directory / "ablation_summary.json").read_text(encoding="utf-8")), rows, \
        json.loads((directory / "forecast_accuracy.json").read_text(encoding="utf-8"))
