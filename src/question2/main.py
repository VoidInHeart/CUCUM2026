"""编排完整求解、图表、官方Excel与论文摘要输出。"""
import argparse
import csv
import json
import logging

from . import config as cfg
from .data_loader import load_actual, load_price
from .exporter import export_result, read_template_labels
from .pipeline import run_ablation, run_annual
from .summary import build_ablation_summary, build_summaries, daily_metrics


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="问题2：31天等权历史场景随机LP，2025年2—12月")
    parser.add_argument("--strategy", choices=("baseline", "causal_mpc", "compare"), default="causal_mpc",
                        help="baseline精确复现A0；causal_mpc执行A1；compare用同一合同并列回测A0/A1")
    parser.add_argument("--debug", action="store_true", help="输出独立校验残差")
    parser.add_argument("--no-plots", action="store_true", help="只生成Excel、JSON、CSV，跳过绘图")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    try:
        labels = read_template_labels()
        logging.info("loading price and annual actual data")
        price = load_price()
        actual = load_actual(price=price)
        ablation = None
        if args.strategy == "compare":
            all_results = run_ablation(price, actual)
            ablation = build_ablation_summary(all_results)
            selected = ablation["selected_strategy"]
            results = all_results[selected]
        else:
            selected = args.strategy
            results = run_annual(price, actual, args.strategy)
        summary = build_summaries(results, labels)
        summary["strategy"] = selected
        if not args.no_plots:
            from .visualization import plot_results
            logging.info("rendering Chinese visualizations")
            plot_results(results)
        logging.info("exporting all 334 days to %s", cfg.RESULT_XLSX)
        export_result(price.price, results)
        cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (cfg.OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        rows = [daily_metrics(item) for item in results]
        _write_csv(cfg.OUTPUT_DIR / "daily_metrics.csv", rows)
        if ablation is not None:
            (cfg.OUTPUT_DIR / "ablation_summary.json").write_text(
                json.dumps(ablation, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
            )
            _write_csv(cfg.OUTPUT_DIR / "ablation_summary.csv", ablation["strategies"])
            for name, values in all_results.items():
                _write_csv(cfg.OUTPUT_DIR / f"{name}_daily_metrics.csv", [daily_metrics(item) for item in values])
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("Question2 failed: %s", exc)
        return 1
    print(f"Question 2 solved successfully: strategy={selected}, 334 days, HiGHS optimal, validation passed.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if ablation is not None:
        print(json.dumps(ablation, ensure_ascii=False, indent=2))
    print(f"Official result: {cfg.RESULT_XLSX}\nSummaries and figures: {cfg.OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
