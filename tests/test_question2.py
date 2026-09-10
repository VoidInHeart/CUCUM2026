"""问题2防泄漏、LP物理约束、事后结算及导出回归测试。"""
from dataclasses import replace
from datetime import date
from unittest import TestCase, main
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

from src.question2 import config as cfg
from src.question2.data_loader import load_actual, load_price
from src.question2.scenario_builder import build_rolling_scenarios, validate_scenarios
from src.question2.optimizer import solve
from src.question2.evaluator import evaluate
from src.question2.validator import validate_plan, validate_evaluation, validate_lp


class Question2Tests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.price = load_price()
        cls.actual = load_actual(price=cls.price)
        cls.scenarios = build_rolling_scenarios(cls.actual, 31)
        cls.plan = solve(cls.price.price, cls.scenarios)

    def test_attachment2_shape_and_net_load_conversion(self):
        self.assertEqual(self.actual.load_kw.shape, (365, 144))
        self.assertEqual(self.actual.pv_kw.shape, (365, 144))
        np.testing.assert_allclose(self.actual.net_load_kwh, (self.actual.load_kw - self.actual.pv_kw) / 6)

    def test_scenario_dates_and_probabilities(self):
        for index in (31, 171, 364):
            scenarios = build_rolling_scenarios(self.actual, index)
            self.assertEqual(scenarios.history_dates, self.actual.dates[index - 31:index])
            self.assertTrue(all(day < scenarios.target_date for day in scenarios.history_dates))
            self.assertEqual(scenarios.net_load_kwh.shape, (31, 144))
            self.assertAlmostEqual(scenarios.probability.sum(), 1)
        self.assertEqual(self.scenarios.history_dates[0], date(2025, 1, 1))
        self.assertEqual(build_rolling_scenarios(self.actual, 364).history_dates[-1], date(2025, 12, 30))
        for index in (0, 30, 365):
            with self.assertRaises(ValueError):
                build_rolling_scenarios(self.actual, index)

    def test_future_actuals_do_not_change_plan(self):
        index = 171
        original = build_rolling_scenarios(self.actual, index)
        net = self.actual.net_load_kwh.copy()
        net[index:] += 1e6
        modified = build_rolling_scenarios(replace(self.actual, net_load_kwh=net), index)
        np.testing.assert_array_equal(original.net_load_kwh, modified.net_load_kwh)
        first, second = solve(self.price.price, original), solve(self.price.price, modified)
        np.testing.assert_allclose(first.grid_kwh, second.grid_kwh)
        before = first.grid_kwh.copy()
        settlement = evaluate(self.price.price, first, net[index])
        self.assertGreater(settlement.emergency_total, 1e6)
        np.testing.assert_array_equal(first.grid_kwh, before)
        with self.assertRaises(ValueError):
            first.grid_kwh[0] = 0

    def test_lookahead_and_nonuniform_weights_rejected(self):
        with self.assertRaisesRegex(ValueError, "no lookahead"):
            validate_scenarios(replace(self.scenarios, history_dates=self.scenarios.history_dates[1:] + (self.scenarios.target_date,)))
        with self.assertRaisesRegex(ValueError, "equal"):
            validate_scenarios(replace(self.scenarios, probability=np.ones(31)))

    def test_lp_feasible_and_terminal_soc(self):
        self.assertLessEqual(validate_plan(self.plan), 1e-5)
        self.assertAlmostEqual(self.plan.soc_end_kwh[-1], 6000, places=5)
        net = self.scenarios.net_load_kwh
        scheduled = self.plan.grid_kwh + self.plan.discharge_kwh - self.plan.charge_kwh
        emergency, surplus = np.maximum(net - scheduled, 0), np.maximum(scheduled - net, 0)
        validate_lp(self.price.price, self.scenarios, self.plan, emergency, surplus)
        emergency[0, 0] += 1
        with self.assertRaisesRegex(ValueError, "balance"):
            validate_lp(self.price.price, self.scenarios, self.plan, emergency, surplus)

    def test_emergency_multiplier_and_actual_balance(self):
        scheduled = self.plan.grid_kwh + self.plan.discharge_kwh - self.plan.charge_kwh
        actual = scheduled + np.where(np.arange(144) % 2 == 0, 100, -50)
        result = evaluate(self.price.price, self.plan, actual)
        self.assertTrue((result.emergency_kwh >= 0).all())
        self.assertAlmostEqual(result.emergency_total, 7200)
        self.assertAlmostEqual(result.emergency_cost, 500 * self.price.price[::2].sum())
        np.testing.assert_allclose(scheduled + result.emergency_kwh - result.surplus_kwh, actual)
        with self.assertRaises(ValueError):
            validate_evaluation(self.price.price, replace(result, total_cost=result.total_cost + 1))

    def test_solver_failure_has_date_status_message(self):
        with patch("src.question2.optimizer.linprog", return_value=SimpleNamespace(success=False, status=2, message="infeasible")):
            with self.assertRaisesRegex(RuntimeError, "2025-02-01.*status 2.*infeasible"):
                solve(self.price.price, self.scenarios)

    def test_constant_scenario_known_cost(self):
        scenarios = replace(self.scenarios, net_load_kwh=np.full((31, 144), 100.0))
        price = np.ones(144)
        plan = solve(price, scenarios)
        self.assertAlmostEqual(plan.expected_objective, 14400, places=5)
        self.assertAlmostEqual(plan.expected_emergency_kwh, 0, places=5)


if __name__ == "__main__":
    main()
