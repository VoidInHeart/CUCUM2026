"""运行入口：python -m src.question1.main。"""
import argparse
import json
import logging

from . import config as cfg
from .data_loader import load_input
from .exporter import export_result
from .optimizer import solve
from .validator import validate_solution


def main() -> int:
    parser = argparse.ArgumentParser(description="问题1：微网日前计划购电策略")
    parser.add_argument("--debug", action="store_true", help="显示求解状态及约束残差")
    parser.add_argument("--plot-only", action="store_true", help="求解并生成图表，不写入官方Excel")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(levelname)s %(message)s")
    try:
        logging.info("loading input: %s", cfg.INPUT_XLSX)
        data = load_input()
        logging.info("slots=%d, load=%.6f kWh, PV=%.6f kWh", len(data.price),
                     data.load_kwh.sum(), data.pv_kwh.sum())
        solution = solve(data)
        logging.info("validating solution")
        logging.debug("residuals: %s", validate_solution(data, solution))
        from .visualization import plot_results
        figures = plot_results(data, solution)
        logging.info("figures: %s", figures)
        if args.plot_only:
            print("Question 1 visualization completed.")
            return 0
        logging.info("exporting result")
        table1, table2 = export_result(data, solution)
    except (ValueError, RuntimeError, OSError) as exc:
        logging.error("%s", exc)
        return 1
    print("Question 1 solved successfully.\nSolver status: optimal")
    for label, value, unit in (
        ("Total grid purchase", solution.total_purchase_kwh, "kWh"),
        ("Total purchase cost", solution.total_purchase_cost_yuan, "yuan"),
        ("Initial SOC", cfg.INITIAL_SOC_KWH, "kWh"),
        ("Final SOC", solution.soc_end_kwh[-1], "kWh"),
        ("Minimum SOC", solution.soc_end_kwh.min(), "kWh"),
        ("Maximum SOC", solution.soc_end_kwh.max(), "kWh"),
        ("Total charge", solution.charge_kwh.sum(), "kWh"),
        ("Total discharge", solution.discharge_kwh.sum(), "kWh"),
        ("Total curtailment", solution.curtailment_kwh.sum(), "kWh"),
    ):
        print(f"{label}: {value:.6f} {unit}")
    print(f"Result written to: {cfg.RESULT_XLSX}")
    print("论文表1:\n" + json.dumps(table1, ensure_ascii=False, indent=2))
    print("论文表2:\n" + json.dumps(table2, ensure_ascii=False, indent=2))
    logging.info("completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
