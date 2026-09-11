"""python run_benchmark.py：先验证官方基线，再发布独立比较结果。"""
import argparse
import logging

from ..question2.data_loader import load_price, load_actual
from ..question3.forecast_loader import load_forecasts
from . import config as cfg
from .evaluator import run_method
from .exporter import export_results, provenance
from .validator import protected_snapshot, check_preserved, validate_baseline, require_baselines


def parse_methods(text):
    methods = tuple(item.strip().upper() for item in text.split(","))
    if not methods or any(item not in cfg.METHODS for item in methods) or len(set(methods)) != len(methods):
        raise argparse.ArgumentTypeError("methods must be unique comma-separated entries from DET,Q80,SAA,CVAR,MPC")
    return methods


def main(argv=None):
    parser = argparse.ArgumentParser(description="独立334日固定电价算法对比；不修改问题1—4正式结果")
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--methods", type=parse_methods, default=cfg.METHODS,
                        help="默认DET,Q80,SAA,CVAR,MPC；SAA/MPC仍会重算作强制基线验证")
    parser.add_argument("--skip-sensitivity", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO, format="%(levelname)s %(message)s")
    before = protected_snapshot()
    try:
        metadata = provenance()
        price = load_price()
        annual = load_actual(price=price)
        forecasts = load_forecasts()
        completed, reports = {}, {}
        # 无论选择哪些方法，均要通过两组334日官方基线门禁，不能用旧验证缓存出图。
        for method in ("SAA", "MPC"):
            run, raw = run_method(method, price.price, annual, forecasts)
            reports[method] = validate_baseline(method, raw)
            completed[method] = run
            logging.info("%s official annual and daily baseline reproduced", method)
        require_baselines(reports)
        for method in args.methods:
            if method not in completed:
                completed[method], _ = run_method(method, price.price, annual, forecasts)
        sensitivity = []
        if not args.skip_sensitivity:
            for alpha in cfg.SENSITIVITY_ALPHAS:
                for weight in cfg.SENSITIVITY_LAMBDAS:
                    if alpha == cfg.MAIN_ALPHA and weight == cfg.MAIN_LAMBDA and "CVAR" in completed:
                        run = completed["CVAR"]
                    else:
                        run, _ = run_method("CVAR", price.price, annual, alpha=alpha, risk_weight=weight)
                    sensitivity.append((alpha, weight, run))
        preservation = check_preserved(before)
        export_results([completed[method] for method in args.methods], sensitivity, reports, metadata, preservation,
                        no_plots=args.no_plots)
        check_preserved(before)
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        logging.error("Benchmark failed; paper outputs require reproducible baselines: %s", exc)
        return 1
    print(f"Benchmark completed: {len(args.methods)} methods, {len(cfg.OUTPUT_DATES)} days, {len(sensitivity)} CVaR sensitivity settings.")
    print(f"Results: {cfg.OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
