"""Isolated SOC experiments. Never writes target/附件5 or legacy analyses."""
import argparse
import logging
import shutil
import json
from pathlib import Path
from src.question2 import config as cfg
from src.question2.data_loader import load_actual, load_price
from src.question2.pipeline import run_annual
from src.question2.summary import daily_metrics, build_summaries
from src.question2.exporter import export_result, read_template_labels
from src.soc_diagnostics import save_results, write_json, write_csv

ROOT = cfg.PROJECT_ROOT / "target" / "revised_soc"


def run_q2(price, actual):
    comparisons = []
    for policy in cfg.SOC_POLICIES:
        results = run_annual(price, actual, soc_policy=policy)
        directory = ROOT / "question2" / policy
        diag = save_results(directory, results, daily_metrics, price.price)
        summary = build_summaries(results, read_template_labels())
        summary["annual"].update(diag)
        write_json(directory/"summary.json", summary)
        candidate = ROOT/"question2"/f"result2_{policy}.xlsx"
        shutil.copy2(cfg.RESULT_XLSX, candidate)
        export_result(price.price, results, candidate)
        comparisons.append(summary["annual"])
        write_json(ROOT/"question2"/"comparison.json", comparisons)
        write_csv(ROOT/"question2"/"comparison.csv", comparisons)
        logging.info("Q2 %s: cost=%.6f near_min=%d", policy, diag["total_cost"], diag["days_end_near_min"])
    shutil.copy2(ROOT/"question2"/"result2_continuous_lookahead.xlsx", ROOT/"result2.xlsx")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["q2", "q3", "q4", "benchmark", "all"], default="all")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    price = load_price()
    actual = load_actual(price=price)
    if args.phase in ("q2", "all"): run_q2(price, actual)
    if args.phase in ("q3", "all"): run_q3(price, actual)
    if args.phase in ("q4", "all"): run_q4(price, actual)
    if args.phase in ("benchmark", "all"): run_benchmark(price, actual)


def run_q3(price, actual):
    from src.question3.forecast_loader import load_forecasts
    from src.question3.rolling_scenario_builder import RollingScenarioBuilder
    from src.question3.analysis import evaluate_update_policy, daily_metrics as metrics, summarize_policies, forecast_accuracy
    from src.question3.summary import build_summary
    from src.question3.exporter import read_template_labels, export_result
    forecasts = load_forecasts()
    builder = RollingScenarioBuilder(actual, forecasts)
    policies = ((0,), (0,6), (0,6,12), (0,6,12,18), (0,12,18), (0,6,18))
    results_by_policy = {}
    for hours in policies:
        results = evaluate_update_policy(hours, price.price, actual, builder, "continuous_lookahead")
        results_by_policy[hours] = results
        directory = ROOT/"question3"/"policies"/"_".join(map(str,hours))
        diag = save_results(directory, results, metrics, price.price)
        write_json(directory/"summary.json", {**diag, "update_hours": hours})
    ablations = summarize_policies(results_by_policy)
    for row, (hours, results) in zip(ablations, results_by_policy.items()):
        from src.soc_diagnostics import diagnostics
        row.update(diagnostics(results,price.price))
    selected = min(results_by_policy, key=lambda h: sum(r.total_cost for r in results_by_policy[h]))
    results = results_by_policy[selected]
    directory = ROOT/"question3"
    diag = save_results(directory, results, metrics, price.price)
    summary = build_summary(results, read_template_labels())
    summary["annual"].update(diag)
    summary["selection_caveat"] = "Retrospective 2025 ablation selection; not out-of-sample policy validation."
    write_json(directory/"summary.json", summary)
    write_json(directory/"ablation_summary.json", ablations)
    write_csv(directory/"ablation_summary.csv", ablations)
    write_csv(directory/"policy_daily_metrics.csv", [{"policy":"+".join(map(str,h)),**metrics(r)} for h,rs in results_by_policy.items() for r in rs])
    accuracy = forecast_accuracy(actual, forecasts)
    write_csv(directory/"forecast_accuracy.csv", accuracy)
    write_json(directory/"forecast_accuracy.json", accuracy)
    candidate = ROOT/"result3.xlsx"
    shutil.copy2(cfg.PROJECT_ROOT/"target"/"附件5"/"result3.xlsx", candidate)
    export_result(price.price, results, candidate, update_hours=selected)
    legacy = evaluate_update_policy((0,6,12),price.price,actual,builder,"daily_closed")
    diag = save_results(directory/"daily_closed",legacy,metrics,price.price)
    write_json(directory/"daily_closed"/"summary.json",diag)


def run_q4(price, actual):
    from src.question3.forecast_loader import load_forecasts
    from src.question3.rolling_scenario_builder import RollingScenarioBuilder
    from src.question3.analysis import evaluate_update_policy, daily_metrics as metrics3
    from src.question3.exporter import export_result as export3
    from src.question4.price_loader import load_annual_price
    from src.question4.question4_2 import run_annual as run42
    from src.question4.question4_3 import run_annual as run43
    prices = load_annual_price(actual)
    builder = RollingScenarioBuilder(actual, load_forecasts())
    selected = tuple(json.loads((ROOT/"question3"/"summary.json").read_text(encoding="utf-8"))["update_hours"])
    for model in ("question4_2", "question4_3"):
        rows = []
        for policy in ("daily_closed", "continuous_lookahead"):
            hours = (0,6,12) if policy=="daily_closed" else selected
            for dynamic in (False, True):
                if model=="question4_2":
                    results = run42(prices, actual, policy) if dynamic else run_annual(price,actual,policy)
                    metrics = daily_metrics
                else:
                    results = run43(prices,actual,builder,policy,hours) if dynamic else evaluate_update_policy(hours,price.price,actual,builder,policy)
                    metrics = metrics3
                directory = ROOT/"question4"/model/policy/("dynamic" if dynamic else "fixed")
                diag = save_results(directory,results,metrics,prices.price_yuan_per_kwh if dynamic else price.price)
                row = {"price_mode":"dynamic" if dynamic else "fixed", "update_hours":"+".join(map(str,hours)) if model=="question4_3" else "0", **diag}
                row.update({key:sum(metrics(r)[key] for r in results) for key in metrics(results[0]) if key!="date"})
                write_json(directory/"summary.json",row)
                rows.append(row)
                if dynamic and policy=="continuous_lookahead":
                    name = "result4-2.xlsx" if model=="question4_2" else "result4-3.xlsx"
                    candidate=ROOT/name
                    shutil.copy2(cfg.PROJECT_ROOT/"target"/"附件5"/name,candidate)
                    if model=="question4_2": export_result(prices.daily_prices(),results,candidate)
                    else: export3(prices.daily_prices(),results,candidate,update_hours=hours)
        write_json(ROOT/"question4"/model/"comparison.json",rows)
        write_csv(ROOT/"question4"/model/"comparison.csv",rows)
        if model=="question4_2":
            sensitivity=run42(prices,actual,"continuous_lookahead",price_information_mode="advance_known_sensitivity")
            metrics=daily_metrics
        else:
            sensitivity=run43(prices,actual,builder,"continuous_lookahead",selected,price_information_mode="advance_known_sensitivity")
            metrics=metrics3
        directory=ROOT/"question4"/model/"advance_known_sensitivity"
        diag=save_results(directory,sensitivity,metrics,prices.price_yuan_per_kwh)
        diag.update(price_information_mode="advance_known_sensitivity", caveat="Conditional future-price knowledge; Dec 31 continuation uses persistence.")
        diag.update({key:sum(metrics(r)[key] for r in sensitivity) for key in metrics(sensitivity[0]) if key!="date"})
        write_json(directory/"summary.json",diag)


def run_benchmark(price,actual):
    from src.question3.forecast_loader import load_forecasts
    from src.question3.rolling_scenario_builder import RollingScenarioBuilder
    from src.question3.analysis import evaluate_update_policy, daily_metrics as metrics3
    selected = tuple(json.loads((ROOT/"question3"/"summary.json").read_text(encoding="utf-8"))["update_hours"])
    rows=[]
    for policy, label in (("daily_closed","legacy_daily_closed"),("continuous_lookahead","continuous_soc")):
        for method in ("DET","Q80","SAA","CVaR-SAA","SAA-MPC"):
            if method=="SAA-MPC":
                builder=RollingScenarioBuilder(actual,load_forecasts())
                results=evaluate_update_policy((0,6,12) if policy=="daily_closed" else selected,price.price,actual,builder,policy)
                metrics=metrics3
            else:
                results=run_annual(price,actual,policy,method=method,risk_weight=.1,risk_alpha=.95)
                metrics=daily_metrics
            diag=save_results(ROOT/"benchmark"/label/method,results,metrics,price.price)
            row={"method":method,"experiment":label,**diag,
                 "emergency_kwh":sum(r.emergency_kwh if method=="SAA-MPC" else r.emergency_total for r in results),
                 "risk_weight":.1 if method=="CVaR-SAA" else 0.,"risk_alpha":.95,
                 "provenance":"reconstructed; no original benchmark available"}
            rows.append(row)
            write_json(ROOT/"benchmark"/label/method/"summary.json",row)
            write_json(ROOT/"benchmark"/"comparison.json",rows)
            write_csv(ROOT/"benchmark"/"comparison.csv",rows)


if __name__ == "__main__": main()
