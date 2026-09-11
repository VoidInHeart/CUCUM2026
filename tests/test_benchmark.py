"""独立实验：人工最优解、时间因果、原基线复现和输出门禁。"""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import numpy as np
from scipy.optimize import linprog

from src.benchmark import adapters, config as cfg, deterministic, quantile, cvar_saa
from src.benchmark.evaluator import run_method
from src.benchmark.metrics import empirical_cvar, summarize, add_relative_changes
from src.benchmark.validator import validate_baseline, require_baselines, compare_numbers
from src.question2.data_loader import load_price, load_actual
from src.question2.scenario_builder import build_rolling_scenarios
from src.question2.types import ScenarioSet, readonly
from src.question3.forecast_loader import load_forecasts
from src.question3.rolling_scenario_builder import RollingScenarioBuilder
from src.question3.rolling_controller import solve_day

PHYS = cfg.physical
FIELDS = ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh")


def synthetic(values):
    day = cfg.OUTPUT_DATES[0]
    return ScenarioSet(day, tuple(day - timedelta(days=i) for i in range(PHYS.HISTORY_WINDOW_DAYS, 0, -1)),
                        readonly(values), readonly(np.full(PHYS.HISTORY_WINDOW_DAYS, 1 / PHYS.HISTORY_WINDOW_DAYS)))


class BenchmarkModelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.price = load_price().price
        cls.annual = load_actual()
        cls.day = cfg.OUTPUT_DATES[100]
        cls.index = cls.annual.dates.index(cls.day)
        cls.scenarios = build_rolling_scenarios(cls.annual, cls.index)

    def test_det_mean_and_known_optimum(self):
        values = np.arange(PHYS.HISTORY_WINDOW_DAYS)[:, None] + np.full((PHYS.HISTORY_WINDOW_DAYS, PHYS.N_SLOTS), 100.0)
        scenarios = synthetic(values)
        np.testing.assert_array_equal(deterministic.forecast(scenarios), values.mean(axis=0))
        plan = deterministic.solve(np.ones(PHYS.N_SLOTS), scenarios)
        self.assertAlmostEqual(plan.grid_kwh.sum(), values.mean(axis=0).sum(), places=5)
        self.assertAlmostEqual(plan.expected_objective, values.mean(axis=0).sum(), places=5)

    def test_q80_exact_linear_quantile_and_known_optimum(self):
        rng = np.random.default_rng(42)
        values = rng.uniform(-100, 1000, (PHYS.HISTORY_WINDOW_DAYS, PHYS.N_SLOTS))
        scenarios = synthetic(values)
        expected = np.quantile(values, 0.8, axis=0, method="linear")
        with patch("src.benchmark.quantile.np.quantile", wraps=np.quantile) as call:
            np.testing.assert_array_equal(quantile.forecast(scenarios), expected)
            self.assertEqual(call.call_args.kwargs["method"], "linear")
        constant = synthetic(np.full_like(values, 100.0))
        plan = quantile.solve(np.ones(PHYS.N_SLOTS), constant)
        self.assertAlmostEqual(plan.expected_objective, 100 * PHYS.N_SLOTS, places=5)

    def test_negative_net_load_uses_same_surplus_model(self):
        scenarios = synthetic(np.full((PHYS.HISTORY_WINDOW_DAYS, PHYS.N_SLOTS), -100.0))
        for solver in (deterministic.solve, quantile.solve):
            plan = solver(np.ones(PHYS.N_SLOTS), scenarios)
            self.assertAlmostEqual(plan.grid_kwh.sum(), 0.0, places=5)
            self.assertAlmostEqual(plan.soc_end_kwh[-1], PHYS.FINAL_SOC_KWH)

    def test_lambda_zero_is_exact_saa(self):
        expected = adapters.solve_saa(self.price, self.scenarios)
        for alpha in cfg.SENSITIVITY_ALPHAS:
            actual = cvar_saa.solve(self.price, self.scenarios, alpha=alpha, risk_weight=0)
            for field in FIELDS:
                np.testing.assert_array_equal(getattr(actual, field), getattr(expected, field))
            self.assertEqual(actual.expected_objective, expected.expected_objective)
            self.assertEqual(actual.expected_emergency_kwh, expected.expected_emergency_kwh)

    def test_cvar_fixed_loss_epigraph_matches_fractional_tail(self):
        losses = np.array([0., 10., 20., 100.])
        alpha = 0.6  # 最差1.6个样本，不能简单平均所有超过p60的样本。
        raw = linprog(np.r_[1., np.full(4, 1 / (4 * (1 - alpha)))],
                       A_ub=np.c_[-np.ones(4), -np.eye(4)], b_ub=-losses,
                       bounds=[(None, None)] + [(0, None)] * 4, method="highs")
        self.assertTrue(raw.success)
        self.assertAlmostEqual(raw.fun, (100 + 0.6 * 20) / 1.6)
        self.assertAlmostEqual(empirical_cvar(losses, alpha), raw.fun)
        self.assertAlmostEqual(empirical_cvar([7, 7, 7], 0.99), 7)

    def test_cvar_artificial_optimum_across_risk_weights(self):
        levels = np.r_[np.zeros(20), np.full(10, 100.), 400.]
        self.assertEqual(len(levels), PHYS.HISTORY_WINDOW_DAYS)
        scenarios = synthetic(np.repeat(levels[:, None], PHYS.N_SLOTS, axis=1))
        price = np.ones(PHYS.N_SLOTS)
        for alpha in cfg.SENSITIVITY_ALPHAS:
            for weight in (0.0, *cfg.SENSITIVITY_LAMBDAS):
                with self.subTest(alpha=alpha, risk_weight=weight):
                    result = cvar_saa.solve_with_diagnostics(price, scenarios, alpha=alpha, risk_weight=weight)
                    # 同序恒定负荷、恒价：最优确定性采购为某个样本断点，无套利价值。
                    candidates = []
                    for grid in np.unique(levels):
                        losses = PHYS.EMERGENCY_PRICE_MULTIPLIER * PHYS.N_SLOTS * np.maximum(levels - grid, 0)
                        candidates.append(PHYS.N_SLOTS * grid + (1 - weight) * losses.mean() + weight * empirical_cvar(losses, alpha))
                    self.assertAlmostEqual(result.plan.expected_objective, min(candidates), places=4)
                    cvar_saa.validate_risk_solution(price, scenarios, result)

    def test_cvar_validator_rejects_damaged_objective_and_epigraph(self):
        result = cvar_saa.solve_with_diagnostics(self.price, self.scenarios)
        damaged = (replace(result, eta=result.eta - 100),
                   replace(result, losses=result.losses + 100),
                   replace(result, plan=replace(result.plan, expected_objective=result.plan.expected_objective + 100)))
        for item in damaged:
            with self.assertRaises(ValueError):
                cvar_saa.validate_risk_solution(self.price, self.scenarios, item)

    def test_cvar_is_of_daily_loss_not_sum_of_slot_tail_risks(self):
        values = np.zeros((PHYS.HISTORY_WINDOW_DAYS, PHYS.N_SLOTS))
        values[:5, 0] = 100
        values[5:10, 1] = 100
        result = cvar_saa.solve_with_diagnostics(np.ones(PHYS.N_SLOTS), synthetic(values),
                                                alpha=.95, risk_weight=.10)
        # 两时段的缺口发生在不同场景。全天CVaR=500，逐slot CVaR求和却为1000。
        # 恒价下电池无套利价值；共享采购增加一对slot的边际成本高于风险下降。
        expected = .9 * (10 / PHYS.HISTORY_WINDOW_DAYS) * 500 + .1 * 500
        self.assertAlmostEqual(result.plan.grid_kwh.sum(), 0, places=5)
        self.assertAlmostEqual(result.cvar_loss, 500, places=5)
        self.assertAlmostEqual(result.plan.expected_objective, expected, places=5)

    def test_parameters_and_solver_failures_are_explicit(self):
        for alpha, weight in ((0, .5), (1, .5), (.95, -1), (.95, 2), (np.nan, .5)):
            with self.assertRaises(ValueError):
                cvar_saa.solve(self.price, self.scenarios, alpha=alpha, risk_weight=weight)
        from types import SimpleNamespace
        with patch("src.benchmark.cvar_saa.linprog", return_value=SimpleNamespace(success=False, status=2, message="infeasible")):
            with self.assertRaisesRegex(RuntimeError, "alpha=0.95 lambda=0.5.*status 2"):
                cvar_saa.solve(self.price, self.scenarios)

    def test_static_plans_ignore_target_load_pv_and_future_data(self):
        for method in ("DET", "Q80", "SAA", "CVAR"):
            original = adapters.plan_static(method, self.day, self.price, self.annual)
            settled = adapters.settle_static(self.price, original, self.annual.net_load_kwh[self.index])
            for case in ("target_load", "target_pv", "future"):
                load, pv = self.annual.load_kw.copy(), self.annual.pv_kw.copy()
                if case == "target_load": load[self.index] += 1e6
                elif case == "target_pv": pv[self.index] += 1e6
                else:
                    load[self.index + 1:] += 1e6
                    pv[self.index + 1:] *= 17
                changed = replace(self.annual, load_kw=readonly(load), pv_kw=readonly(pv),
                                   net_load_kwh=readonly((load - pv) * PHYS.TIME_STEP_HOURS))
                with self.subTest(method=method, case=case):
                    plan = adapters.plan_static(method, self.day, self.price, changed)
                    for field in FIELDS:
                        np.testing.assert_array_equal(getattr(plan, field), getattr(original, field))
                        self.assertFalse(getattr(plan, field).flags.writeable)
                    result = adapters.settle_static(self.price, plan, changed.net_load_kwh[self.index])
                    if case == "future": self.assertEqual(result.total_cost, settled.total_cost)
                    elif case == "target_load": self.assertGreater(result.emergency_cost, settled.emergency_cost)
                    else: self.assertEqual(result.emergency_total, 0)

    def test_history_poison_is_rejected(self):
        bad = replace(self.scenarios, history_dates=(*self.scenarios.history_dates[:-1], self.day))
        for solver in (deterministic.solve, quantile.solve, adapters.solve_saa, cvar_saa.solve):
            with self.assertRaisesRegex(ValueError, "no lookahead"):
                solver(self.price, bad)


class BenchmarkMPCTests(TestCase):
    def test_official_adapter_and_controller_never_use_18_forecasts(self):
        price = load_price().price
        annual = load_actual()
        forecasts = load_forecasts()
        day = cfg.OUTPUT_DATES[100]
        builder = RollingScenarioBuilder(annual, forecasts)
        original = solve_day(day, price, builder, cfg.Q3_FINAL_UPDATE_HOURS)
        # 删除所有日期的18:00预报，同时隔离目标日之后的完整预报记录。
        restricted = {d: replace(f, issues={h: issue for h, issue in f.issues.items() if h != 18})
                      for d, f in forecasts.items() if d <= day}
        changed = RollingScenarioBuilder(annual, restricted)
        with patch.object(changed, "build", wraps=changed.build) as build:
            actual = solve_day(day, price, changed, cfg.Q3_FINAL_UPDATE_HOURS)
        self.assertEqual([call.args[1] for call in build.call_args_list], [0, 6, 12])
        for field in ("executed_grid", "executed_charge", "executed_discharge", "executed_soc_end"):
            np.testing.assert_array_equal(getattr(actual, field), getattr(original, field))
        for a, b in zip(actual.revisions, original.revisions):
            for field in FIELDS:
                np.testing.assert_array_equal(getattr(a.plan, field), getattr(b.plan, field))
        with patch("src.benchmark.adapters.evaluate_update_policy", return_value=[]) as run:
            adapters.run_mpc(price, annual, forecasts)
            self.assertEqual(run.call_args.args[0], (0, 6, 12))


class BenchmarkBaselineTests(TestCase):
    @classmethod
    def setUpClass(cls):
        price = load_price().price
        annual = load_actual()
        forecasts = load_forecasts()
        cls.runs, cls.reports = {}, {}
        for method in ("SAA", "MPC"):
            run, raw = run_method(method, price, annual, forecasts)
            cls.runs[method] = run
            cls.reports[method] = validate_baseline(method, raw)

    def test_saa_and_mpc_full_334_day_regression(self):
        require_baselines(self.reports)
        for report in self.reports.values():
            self.assertEqual(report["daily_rows_checked"], len(cfg.OUTPUT_DATES))

    def test_metrics_cost_identities_and_offline_tail(self):
        for run in self.runs.values():
            row = summarize(run)
            self.assertAlmostEqual(row["total_cost"], row["contract_cost"] + row["emergency_cost"], places=5)
            self.assertAlmostEqual(row["contract_cost"], row["plan_cost"] + row["adjustment_cost"], places=5)
            self.assertAlmostEqual(row["throughput_kwh"], row["charge_kwh"] + row["discharge_kwh"], places=5)
            self.assertEqual(row["p95_daily_cost"], float(np.quantile([d.total_cost for d in run.daily], .95, method="linear")))
            self.assertGreater(row["total_runtime_seconds"], 0)
            self.assertAlmostEqual(row["mean_runtime_per_day_ms"], 1000 * run.total_runtime_seconds / len(cfg.OUTPUT_DATES))
        self.assertEqual(summarize(self.runs["SAA"])["adjustment_cost"], 0)

    def test_baseline_gate_rejects_missing_failed_or_mismatching_reference(self):
        with self.assertRaisesRegex(ValueError, "refusing"):
            require_baselines({"SAA": self.reports["SAA"]})
        with self.assertRaisesRegex(ValueError, "baseline mismatch"):
            compare_numbers({"total_cost": 3.}, {"total_cost": 4.}, "test")

    def test_relative_changes_zero_denominator_and_missing_det(self):
        rows = [{"method": "SAA", "total_cost": 100., "emergency_kwh": 0.},
                {"method": "DET", "total_cost": 200., "emergency_kwh": 1.}]
        result = add_relative_changes(rows)
        self.assertEqual(result[1]["total_cost_change_vs_saa_pct"], 100)
        self.assertEqual(result[0]["total_cost_change_vs_det_pct"], -50)
        self.assertIsNone(result[1]["emergency_kwh_change_vs_saa_pct"])
        self.assertIsNone(add_relative_changes(rows[:1])[0]["total_cost_change_vs_det_pct"])

    def test_exported_metrics_are_consistent_and_hashed(self):
        from src.benchmark.exporter import export_results, provenance
        from src.benchmark.validator import sha256
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            comparison, sensitivity = export_results(list(self.runs.values()), [], self.reports, provenance(),
                                                      {"status": "passed"}, no_plots=True, directory=directory)
            self.assertEqual(sensitivity, [])
            saved = json.loads((directory / "comparison.json").read_text(encoding="utf-8"))
            self.assertEqual(comparison, saved)
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            for name, digest in manifest["artifacts_sha256"].items():
                self.assertEqual(sha256(directory / name), digest)
            self.assertEqual(manifest["sensitivity_count"], 0)
            text = (directory / "experiment_summary.md").read_text(encoding="utf-8")
            self.assertIn("0+6+12", text)
            self.assertIn("信息", text)
            self.assertEqual(list((directory / "figures").iterdir()), [])

    def test_failed_baseline_or_plot_preserves_previous_outputs(self):
        from src.benchmark.exporter import export_results, provenance
        with TemporaryDirectory() as temporary:
            directory = Path(temporary)
            old = directory / "comparison.json"
            old.write_bytes(b"previous verified output")
            with self.assertRaisesRegex(ValueError, "refusing"):
                export_results(list(self.runs.values()), [], {}, {}, {}, directory=directory)
            self.assertEqual(old.read_bytes(), b"previous verified output")
            with patch("src.benchmark.visualization.plot_results", side_effect=RuntimeError("plot failed")):
                with self.assertRaisesRegex(RuntimeError, "plot failed"):
                    export_results(list(self.runs.values()), [], self.reports, provenance(), {}, directory=directory)
            self.assertEqual(old.read_bytes(), b"previous verified output")
            self.assertEqual(list(directory.glob(".staging-*")), [])

    def test_main_does_not_export_when_baseline_fails(self):
        from src.benchmark.main import main as benchmark_main, parse_methods
        import argparse
        for methods in ("DET,DET", "DET,UNKNOWN", ""):
            with self.assertRaises(argparse.ArgumentTypeError): parse_methods(methods)
        with patch("src.benchmark.main.run_method", return_value=(self.runs["SAA"], [])), \
             patch("src.benchmark.main.validate_baseline", side_effect=ValueError("baseline mismatch")), \
             patch("src.benchmark.main.export_results") as export:
            self.assertEqual(benchmark_main(["--no-plots", "--skip-sensitivity"]), 1)
            export.assert_not_called()

    def test_old_four_update_summary_cannot_be_the_mpc_baseline(self):
        source = PHYS.PROJECT_ROOT / "target" / "question3" / "summary.json"
        original = json.loads(source.read_text(encoding="utf-8"))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "question3").mkdir()
            changed = {**original, "update_hours": [0, 6, 12, 18], "policy": "0+6+12+18"}
            (root / "question3" / "summary.json").write_text(json.dumps(changed), encoding="utf-8")
            with patch("src.benchmark.validator.build_summary", return_value=original):
                with self.assertRaisesRegex(ValueError, "official 0\\+6\\+12"):
                    validate_baseline("MPC", [], root)


if __name__ == "__main__":
    main()
