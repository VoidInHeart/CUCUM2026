"""Shared executed-state diagnostics; no model inputs are inferred from settlement."""
import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
import numpy as np


def encode(value):
    if is_dataclass(value): return asdict(value)
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, np.generic): return value.item()
    raise TypeError(type(value).__name__)


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=encode, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def boundary_rows(results):
    rows = []
    for r in results:
        if hasattr(r, "plan"):
            plan, soc = r.plan, r.plan.soc_end_kwh
            policy = "day_ahead"
        else:
            plan, soc = r.schedule.initial_plan, r.schedule.executed_soc_end
            policy = "+".join(map(str, (0, *(rev.issue_hour for rev in r.schedule.revisions))))
        rows.append(dict(date=str(plan.date), soc_00=plan.initial_soc_kwh, soc_06=float(soc[35]),
                         soc_12=float(soc[71]), soc_18=float(soc[107]), soc_24=float(soc[-1]), selected_policy=policy))
    return rows


def diagnostics(results, price):
    rows = boundary_rows(results)
    starts = np.array([r["soc_00"] for r in rows])
    ends = np.array([r["soc_24"] for r in rows])
    q2 = hasattr(results[0], "plan")
    soc = np.concatenate([r.plan.soc_end_kwh if q2 else r.schedule.executed_soc_end for r in results])
    charge = sum(float((r.plan.charge_kwh if q2 else r.schedule.executed_charge).sum()) for r in results)
    discharge = sum(float((r.plan.discharge_kwh if q2 else r.schedule.executed_discharge).sum()) for r in results)
    emergency = [r.emergency_kwh if q2 else r.real_emergency for r in results]
    plan = results[0].plan if q2 else results[0].schedule.initial_plan
    raw = sum(r.total_cost for r in results)
    error = float(np.max(np.abs(starts[1:]-ends[:-1]))) if len(rows)>1 else 0.0
    if error > 1e-5: raise ValueError(f"cross-day SOC discontinuity: {error}")
    result = dict(soc_policy=plan.soc_policy, terminal_mode="daily_reference" if plan.soc_policy=="daily_closed" else "free",
                  initial_soc_policy="feb1_control_start", initial_soc_first_day=float(starts[0]), final_soc_last_day=float(ends[-1]),
                  mean_daily_start_soc=float(starts.mean()), mean_daily_end_soc=float(ends.mean()),
                  min_soc=float(min(soc.min(), starts.min())), max_soc=float(max(soc.max(), starts.max())),
                  mean_soc=float(soc.mean()), terminal_soc_mean=float(ends.mean()), terminal_soc_median=float(np.median(ends)),
                  terminal_soc_min=float(ends.min()), terminal_soc_max=float(ends.max()),
                  terminal_soc_p05=float(np.quantile(ends,.05)), terminal_soc_p95=float(np.quantile(ends,.95)),
                  days_terminal_soc_near_min=int((ends<=1320).sum()), days_terminal_soc_near_max=int((ends>=10680).sum()),
                  soc_start_end_delta_mean=float((ends-starts).mean()), soc_continuity_max_error=error,
                  charge_kwh=charge, discharge_kwh=discharge, throughput_kwh=charge+discharge,
                  emergency_days=sum(bool((e>1e-6).any()) for e in emergency), emergency_slots=sum(int((e>1e-6).sum()) for e in emergency),
                  raw_total_cost=raw, total_cost=raw, daily_cost_p95=float(np.quantile([r.total_cost for r in results],.95)))
    result["days_end_near_min"] = result["days_terminal_soc_near_min"]
    result["days_end_near_max"] = result["days_terminal_soc_near_max"]
    result.update(mean_terminal_soc=result["terminal_soc_mean"], min_terminal_soc=result["terminal_soc_min"],
                  max_terminal_soc=result["terminal_soc_max"], days_near_soc_min=result["days_end_near_min"],
                  days_near_soc_max=result["days_end_near_max"])
    for label, value in (("low", np.min(price)), ("mean", np.mean(price)), ("high", np.max(price))):
        result[f"salvage_{label}_yuan_per_kwh"] = float(value*.9)
        result[f"terminal_energy_adjusted_cost_{label}"] = float(raw - value*.9*(ends[-1]-starts[0]))
    result["terminal_energy_adjusted_cost"] = result["terminal_energy_adjusted_cost_mean"]
    return result


def save_results(directory, results, metrics, price):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    write_csv(directory/"daily_metrics.csv", [metrics(r) for r in results])
    rows = boundary_rows(results)
    write_csv(directory/"soc_continuity.csv", rows)
    diag = diagnostics(results, price)
    write_json(directory/"soc_boundary_diagnostics.json", diag)
    with (directory/"daily_results.jsonl").open("w", encoding="utf-8") as stream:
        for r in results: stream.write(json.dumps(r, default=encode, ensure_ascii=False, allow_nan=False)+"\n")
    from .plotting import plt, configure_chinese, save_figure
    configure_chinese()
    fig, ax = plt.subplots(figsize=(12,4))
    dates = [date.fromisoformat(r["date"]) for r in rows]
    ax.plot(dates, [r["soc_00"] for r in rows], label="0:00 SOC", alpha=.8)
    ax.plot(dates, [r["soc_24"] for r in rows], label="24:00 SOC", alpha=.8)
    ax.axhline(1200, color="gray", ls="--", label="SOC_MIN")
    ax.axhline(10800, color="black", ls="--", label="SOC_MAX")
    ax.set(ylabel="SOC (kWh)", title=diag["soc_policy"])
    ax.legend(ncol=4)
    save_figure(fig, directory/"figures", "soc_daily_boundary")
    return diag
