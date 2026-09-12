"""真实代表日期回归、逐时价格目标系数、交易现金流和禁用18点更新。"""
from dataclasses import replace
from unittest import TestCase, main
from unittest.mock import patch
import numpy as np
from scipy.optimize import linprog

from src.question2.data_loader import load_price, load_actual
from src.question2.pipeline import solve_day as solve_q2
from src.question2.scenario_builder import build_scenarios
from src.question2.config import OFFICIAL_STRATEGY
from src.question3.forecast_loader import load_forecasts
from src.question3.rolling_scenario_builder import RollingScenarioBuilder
from src.question3.rolling_controller import solve_day_causal
from src.question3.evaluator import evaluate_actual_day
from src.question3.config import Q3_FINAL_UPDATE_HOURS
from src.question4 import config as cfg, question4_2, question4_3
from src.question4.price_loader import load_annual_price, get_daily_price, validate_alignment
from src.question4.validator import validate_q42, validate_q43


class Question4ModelTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = load_actual()
        cls.prices = load_annual_price(cls.actual)
        cls.fixed = load_price().price
        cls.constant = replace(cls.prices, price_yuan_per_kwh=np.tile(cls.fixed, (365, 1)))
        cls.forecasts = load_forecasts()
        cls.builder = RollingScenarioBuilder(
            cls.actual, cls.forecasts, cfg.Q4_3_SCENARIO_METHOD
        )
        cls.day = cfg.PAPER_DATES[1]
        cls.q = get_daily_price(cls.prices, cls.day)
        cls.r42 = question4_2.solve_day(cls.day, cls.prices, cls.actual)
        cls.r43 = question4_3.solve_day(cls.day, cls.prices, cls.actual, cls.builder)

    def test_q42_fixed_price_regression(self):
        for day in cfg.PAPER_DATES:
            with self.subTest(day=day):
                baseline = solve_q2(day, self.fixed, self.actual, OFFICIAL_STRATEGY)
                result = question4_2.solve_day(day, self.constant, self.actual)
                for key in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh"):
                    np.testing.assert_allclose(getattr(result.plan, key), getattr(baseline.plan, key), atol=1e-5, rtol=0)
                np.testing.assert_allclose(result.emergency_kwh, baseline.emergency_kwh, atol=1e-5, rtol=0)
                self.assertAlmostEqual(result.total_cost, baseline.total_cost, places=6)

    def test_q43_fixed_price_regression(self):
        for day in cfg.PAPER_DATES:
            with self.subTest(day=day):
                actual_net = self.actual.net_load_kwh[self.builder.date_index[day]]
                schedule = solve_day_causal(
                    day, self.fixed, self.builder, actual_net, Q3_FINAL_UPDATE_HOURS
                )
                baseline = evaluate_actual_day(
                    self.fixed, schedule, actual_net, Q3_FINAL_UPDATE_HOURS
                )
                result = question4_3.solve_day(day, self.constant, self.actual, self.builder)
                for key in ("executed_grid", "executed_charge", "executed_discharge", "executed_soc_end"):
                    np.testing.assert_allclose(getattr(result.schedule, key), getattr(schedule, key), atol=1e-5, rtol=0)
                np.testing.assert_allclose(result.schedule.initial_plan.grid_kwh, schedule.initial_plan.grid_kwh, atol=1e-5, rtol=0)
                np.testing.assert_allclose(result.real_emergency, baseline.real_emergency, atol=1e-5, rtol=0)
                self.assertAlmostEqual(result.total_cost, baseline.total_cost, places=6)

    def test_q42_dynamic_price_objective(self):
        with patch("src.question2.optimizer.linprog", wraps=linprog) as solver:
            question4_2.solve_day(self.day, self.prices, self.actual)
        objective = solver.call_args.args[0]
        np.testing.assert_array_equal(objective[:144], self.q)
        index = self.actual.dates.index(self.day)
        scenarios = build_scenarios(self.actual, index, "residual_weighted")
        np.testing.assert_allclose(
            objective[4*144:35*144].reshape(31,144),
            5 * scenarios.probability[:, None] * self.q,
        )

    def test_q43_initial_adjustment_price_and_horizon(self):
        with patch("src.question3.optimizer.linprog", wraps=linprog) as solver:
            question4_3.solve_day(self.day, self.prices, self.actual, self.builder)
        self.assertEqual(solver.call_count, 3)
        for hour, call in zip((0,6,12), solver.call_args_list):
            objective = call.args[0]
            q = self.q[6*hour:]
            h = len(q)
            scenarios = self.builder.build(self.day, hour)
            count = len(scenarios.history_dates)
            np.testing.assert_allclose(
                objective[4*h:(4+count)*h].reshape(count,h),
                5 * scenarios.probability[:, None] * q,
            )
            if hour:
                np.testing.assert_array_equal(objective[(4+2*count)*h:(5+2*count)*h], 1.5*q)
                np.testing.assert_array_equal(objective[(5+2*count)*h:], -0.5*q)
            else:
                np.testing.assert_array_equal(objective[:h], q)

    def test_q42_emergency_dynamic_price_and_cost_identity(self):
        r = self.r42
        self.assertAlmostEqual(r.emergency_cost, 5*self.q @ r.emergency_kwh, places=6)
        self.assertAlmostEqual(r.total_cost, self.q @ r.plan.grid_kwh + 5*self.q @ r.emergency_kwh, places=6)
        validate_q42(self.prices, [r], complete=False)
        with self.assertRaises(ValueError): validate_q42(self.prices, [replace(r, total_cost=r.total_cost+1)], complete=False)

    def test_q43_emergency_adjustment_and_cost_identity(self):
        r = self.r43
        cash = 0.0
        for revision in r.schedule.revisions:
            q = self.q[revision.start_slot:]
            expected = 1.5*q @ revision.up_adjust - 0.5*q @ revision.down_adjust
            self.assertAlmostEqual(expected, revision.adjustment_cashflow_yuan, places=6)
            cash += expected
        self.assertAlmostEqual(r.emergency_cost, 5*self.q @ r.real_emergency, places=6)
        self.assertAlmostEqual(r.total_cost, self.q @ r.schedule.initial_plan.grid_kwh + cash + 5*self.q @ r.real_emergency, places=6)
        with self.assertRaises(ValueError): validate_q43(self.prices, [replace(r, total_cost=r.total_cost+1)], complete=False)

    def test_q43_inherits_q3_update_hours_without_18_forecast(self):
        self.assertEqual(cfg.Q4_3_UPDATE_HOURS, Q3_FINAL_UPDATE_HOURS)
        self.assertEqual(cfg.Q4_3_UPDATE_HOURS, (0, 6, 12))
        forecasts = {day: replace(f, issues={h: issue for h, issue in f.issues.items() if h != 18}) for day, f in self.forecasts.items()}
        builder = RollingScenarioBuilder(
            self.actual, forecasts, cfg.Q4_3_SCENARIO_METHOD
        )
        with patch.object(builder, "build", wraps=builder.build) as build:
            result = question4_3.solve_day(self.day, self.prices, self.actual, builder)
        self.assertEqual([call.args[1] for call in build.call_args_list], [0,6,12])
        np.testing.assert_array_equal(result.schedule.executed_grid, self.r43.schedule.executed_grid)

    def test_forecast_date_alignment(self):
        bad = dict(self.forecasts)
        bad[self.day] = replace(bad[self.day], date=cfg.PAPER_DATES[0])
        with self.assertRaisesRegex(ValueError, "forecast dates"):
            validate_alignment(self.prices, self.actual, bad)

    def test_target_day_price_only(self):
        altered = self.prices.price_yuan_per_kwh.copy()
        index = self.prices.date_to_index[self.day]
        altered[:index] *= 3
        altered[index+1:] *= 2
        other = replace(self.prices, price_yuan_per_kwh=altered)
        for result, original in ((question4_2.solve_day(self.day, other, self.actual), self.r42),
                                 (question4_3.solve_day(self.day, other, self.actual, self.builder), self.r43)):
            self.assertAlmostEqual(result.total_cost, original.total_cost, places=6)


if __name__ == "__main__":
    main()
