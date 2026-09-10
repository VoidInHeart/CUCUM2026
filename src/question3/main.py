"""完整策略和六组消融统一入口；全部求解成功后才替换正式Excel。"""
import argparse
import logging
import json

from ..question2.data_loader import load_price, load_actual
from . import config as cfg
from .forecast_loader import load_forecasts
from .rolling_scenario_builder import RollingScenarioBuilder
from .analysis import evaluate_update_policy, summarize_policies, forecast_accuracy
from .exporter import read_template_labels, export_result
from .summary import build_summary
from .storage import save_analysis, load_analysis
from .validator import validate_complete


def main():
    parser = argparse.ArgumentParser(description="问题3：日内滚动优化、预报时刻消融与中文可视化")
    parser.add_argument("--debug", action="store_true", help="显示每次LP校验残差和滚动状态")
    parser.add_argument("--no-plots", action="store_true", help="完成全部计算和数据输出，跳过绘图")
    parser.add_argument("--plots-only", action="store_true", help="只重绘已保存的分析结果，不修改正式Excel")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    try:
        price = load_price()
        if args.plots_only:
            from .visualization import plot_results
            results, ablations, rows, accuracy = load_analysis(cfg.OUTPUT_DIR)
            validate_complete(price.price, results)
            plot_results(results, ablations, rows, accuracy)
            return 0
        labels = read_template_labels()
        annual = load_actual(price=price)
        forecasts = load_forecasts()
        builder = RollingScenarioBuilder(annual, forecasts)
        # 主策略先完成；其它策略仅输出分析，不生成额外官方Excel。
        policies = [cfg.ISSUE_HOURS] + [hours for hours in cfg.POLICIES if hours != cfg.ISSUE_HOURS]
        policy_results = {hours: evaluate_update_policy(hours, price.price, annual, builder) for hours in policies}
        policy_results = {hours: policy_results[hours] for hours in cfg.POLICIES}
        results = policy_results[cfg.ISSUE_HOURS]
        ablations = summarize_policies(policy_results)
        accuracy = forecast_accuracy(annual, forecasts)
        summary = build_summary(results, labels)
        save_analysis(cfg.OUTPUT_DIR, results, policy_results, summary, ablations, accuracy)
        if not args.no_plots:
            from .visualization import plot_results
            from .analysis import daily_metrics, policy_name
            rows = [{"policy": policy_name(hours), **daily_metrics(result)} for hours, values in policy_results.items() for result in values]
            plot_results(results, ablations, rows, accuracy)
        export_result(price.price, results)
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        logging.error("Question3 failed: %s", exc)
        return 1
    print("Question 3 solved: 334 days, 6 update policies, all LP and accounting checks passed.")
    print(json.dumps({"annual": summary["annual"], "ablation": ablations, "forecast_accuracy": accuracy}, ensure_ascii=False, indent=2))
    print(f"Official result: {cfg.RESULT_XLSX}\nFigures and summaries: {cfg.OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
