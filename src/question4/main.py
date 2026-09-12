"""两个独立入口及联合运行；所有选定模型求解、比较成功后才导出。"""
import argparse
import json
import logging

from ..question2.data_loader import load_actual
from ..question2 import exporter as exporter2
from ..question3 import exporter as exporter3
from ..question3.forecast_loader import load_forecasts
from ..question3.rolling_scenario_builder import RollingScenarioBuilder
from . import config as cfg, question4_2, question4_3
from .price_loader import load_annual_price, validate_alignment
from .comparison import fixed_price_baseline, daily_metrics, compare
from .storage import save_analysis, load_analysis


def main(model=None):
    parser = argparse.ArgumentParser(description="问题4：动态电价下重算问题2/3并比较固定电价基线")
    if model is None: parser.add_argument("--model", choices=("both", "4-2", "4-3"), default="both")
    parser.add_argument("--debug", action="store_true", help="显示LP残差和每次滚动更新")
    parser.add_argument("--no-plots", action="store_true", help="完成计算和数据输出，跳过绘图")
    parser.add_argument("--plots-only", action="store_true", help="验证存档并重绘，不求解或修改正式Excel")
    args = parser.parse_args()
    model = model or args.model
    models = ("4-2", "4-3") if model == "both" else (model,)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    try:
        actual = load_actual()
        prices = load_annual_price(actual)
        builder = None
        if "4-3" in models and not args.plots_only:
            forecasts = load_forecasts()
            validate_alignment(prices, actual, forecasts)
            builder = RollingScenarioBuilder(actual, forecasts, cfg.Q4_3_SCENARIO_METHOD)
        completed = {}
        for selected in models:
            directory = cfg.OUTPUT_DIR / ("question" + selected.replace("-", "_"))
            if args.plots_only:
                completed[selected] = load_analysis(directory, selected, prices)
                continue
            path = cfg.RESULT42_XLSX if selected == "4-2" else cfg.RESULT43_XLSX
            labels = (exporter2 if selected == "4-2" else exporter3).read_template_labels(path)
            logging.info("Question %s: dynamic price, update hours=%s", selected, (0,) if selected == "4-2" else cfg.Q4_3_UPDATE_HOURS)
            results = (question4_2.run_annual(prices, actual) if selected == "4-2" else
                       question4_3.run_annual(prices, actual, builder))
            logging.info("Question %s: recomputing fixed-price baseline with the identical policy", selected)
            fixed_prices, fixed_results = fixed_price_baseline(selected, prices, actual, builder)
            dynamic_rows = daily_metrics(selected, prices, results)
            fixed_rows = daily_metrics(selected, fixed_prices, fixed_results)
            comparison = compare(selected, dynamic_rows, fixed_rows)
            save_analysis(directory, selected, prices, results, labels, dynamic_rows, fixed_rows, comparison)
            completed[selected] = results, dynamic_rows, fixed_rows, comparison
        if not args.no_plots:
            from .visualization import plot_results
            for selected, data in completed.items():
                directory = cfg.OUTPUT_DIR / ("question" + selected.replace("-", "_")) / "figures"
                plot_results(selected, prices, *data, directory)
        if not args.plots_only:
            for selected, (results, _, _, _) in completed.items():
                if selected == "4-2":
                    exporter2.export_result(prices.daily_prices(), results, cfg.RESULT42_XLSX)
                else:
                    exporter3.export_result(prices.daily_prices(), results, cfg.RESULT43_XLSX, update_hours=cfg.Q4_3_UPDATE_HOURS)
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        logging.error("Question4 failed: %s", exc)
        return 1
    for selected, (_, _, _, comparison) in completed.items():
        print(json.dumps({"model": selected, "update_hours": comparison["update_hours"],
                          "cost_comparison": next(row for row in comparison["changes"] if row["metric"] == "total_cost")},
                         ensure_ascii=False, indent=2))
    print(f"Question4 completed. Analysis: {cfg.OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
