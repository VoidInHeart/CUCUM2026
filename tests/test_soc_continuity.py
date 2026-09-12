from dataclasses import replace
from unittest import TestCase
import numpy as np
from src.question2 import config as cfg
from src.question2.data_loader import load_actual, load_price
from src.question2.scenario_builder import build_rolling_scenarios, build_multiday_scenarios
from src.question2.optimizer import solve
from src.question2.pipeline import solve_day
from src.question2.validator import validate_plan


class ContinuousSOC(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.price = load_price()
        cls.actual = load_actual(price=cls.price)

    def test_initial_soc_parameter_is_used(self):
        scenarios = build_rolling_scenarios(self.actual, 31)
        for initial in (1200, 6000, 10800):
            plan = solve(self.price.price, scenarios, initial, "continuous_myopic")
            self.assertEqual(plan.initial_soc_kwh, initial)
            validate_plan(plan)
        with self.assertRaises(ValueError):
            solve(self.price.price, scenarios, soc_policy="continuous_myopic")

    def test_soc_continuity_question2(self):
        for policy in ("continuous_myopic", "continuous_lookahead"):
            first = solve_day(self.actual.dates[31], self.price.price, self.actual, 6000, policy)
            self.assertGreater(abs(first.plan.terminal_soc_kwh-6000), 1)
            second = solve_day(self.actual.dates[32], self.price.price, self.actual, first.plan.terminal_soc_kwh, policy)
            self.assertEqual(second.plan.initial_soc_kwh, first.plan.terminal_soc_kwh)
            validate_plan(second.plan)

    def test_terminal_soc_not_forced_in_continuous(self):
        scenarios = replace(build_rolling_scenarios(self.actual, 31), net_load_kwh=np.full((31,144),1000.))
        plan = solve(np.ones(144), scenarios, 6000, "continuous_myopic")
        self.assertAlmostEqual(plan.terminal_soc_kwh, 1200, places=5)

    def test_48h_scenario_uses_only_past_days(self):
        baseline = build_multiday_scenarios(self.actual, 31)
        self.assertEqual(baseline.net_load_kwh.shape, (30,288))
        np.testing.assert_array_equal(baseline.net_load_kwh[0], self.actual.net_load_kwh[:2].ravel())
        np.testing.assert_array_equal(baseline.net_load_kwh[-1], self.actual.net_load_kwh[29:31].ravel())
        modified = self.actual.net_load_kwh.copy()
        modified[31:] += 1e9
        other = build_multiday_scenarios(replace(self.actual, net_load_kwh=modified),31)
        np.testing.assert_array_equal(baseline.net_load_kwh,other.net_load_kwh)

    def test_soc_continuity_question3(self):
        from src.question3.forecast_loader import load_forecasts
        from src.question3.rolling_scenario_builder import RollingScenarioBuilder
        from src.question3.rolling_controller import solve_day as q3_day
        builder = RollingScenarioBuilder(self.actual, load_forecasts())
        first = q3_day(self.actual.dates[31], self.price.price, builder, (0,6,12,18), 6000, "continuous_lookahead")
        second = q3_day(self.actual.dates[32], self.price.price, builder, (0,6,12,18),
                        float(first.executed_soc_end[-1]), "continuous_lookahead")
        self.assertEqual(second.initial_plan.initial_soc_kwh, first.executed_soc_end[-1])
        self.assertEqual(first.revisions[-1].plan.grid_kwh.shape, (144,))
        self.assertEqual(first.revisions[-1].up_adjust.shape, (36,))
        self.assertEqual(first.revisions[-1].plan.horizon_slot_datetimes[-1].date(), self.actual.dates[32])

    def test_mpc_cross_midnight_no_future_actual(self):
        from src.question3.forecast_loader import load_forecasts
        from src.question3.rolling_scenario_builder import RollingScenarioBuilder
        forecasts = load_forecasts()
        for hour in (0,6,12,18):
            original = RollingScenarioBuilder(self.actual, forecasts).build(self.actual.dates[31], hour, "issue_relative")
            load, pv = self.actual.load_kw.copy(), self.actual.pv_kw.copy()
            load[31:].ravel()[hour*6:] = 1e9
            pv[31:].ravel()[hour*6:] = 1e9
            modified = RollingScenarioBuilder(replace(self.actual,load_kw=load,pv_kw=pv), forecasts).build(self.actual.dates[31],hour,"issue_relative")
            np.testing.assert_array_equal(original.net_load_kwh,modified.net_load_kwh)

    def test_cvar_lambda_zero_matches_new_saa(self):
        scenarios = build_multiday_scenarios(self.actual,31)
        q = np.tile(self.price.price,2)
        saa = solve(q,scenarios,1200,"continuous_lookahead")
        zero = solve(q,scenarios,1200,"continuous_lookahead",risk_weight=0.)
        np.testing.assert_array_equal(saa.grid_kwh,zero.grid_kwh)
        self.assertEqual(saa.expected_objective,zero.expected_objective)
        risk = solve(q,scenarios,1200,"continuous_lookahead",risk_weight=.1)
        self.assertGreaterEqual(risk.risk_penalty,0.)

    def test_soc_continuity_benchmark_adapter(self):
        for method in ("DET","Q80","SAA","CVaR-SAA"):
            first = solve_day(self.actual.dates[31],self.price.price,self.actual,6000,"continuous_lookahead",method=method)
            second = solve_day(self.actual.dates[32],self.price.price,self.actual,first.plan.terminal_soc_kwh,"continuous_lookahead",method=method)
            self.assertEqual(first.plan.terminal_soc_kwh,second.plan.initial_soc_kwh)

    def test_soc_continuity_question42_question43(self):
        from src.question4.price_loader import load_annual_price
        from src.question4.question4_2 import solve_day as q42
        from src.question4.question4_3 import solve_day as q43
        from src.question3.forecast_loader import load_forecasts
        from src.question3.rolling_scenario_builder import RollingScenarioBuilder
        prices = load_annual_price(self.actual)
        builder = RollingScenarioBuilder(self.actual,load_forecasts())
        a = q42(self.actual.dates[31],prices,self.actual,6000,"continuous_lookahead")
        b = q42(self.actual.dates[32],prices,self.actual,a.plan.terminal_soc_kwh,"continuous_lookahead")
        self.assertEqual(a.plan.terminal_soc_kwh,b.plan.initial_soc_kwh)
        a = q43(self.actual.dates[31],prices,self.actual,builder,6000,"continuous_lookahead",(0,6,18))
        b = q43(self.actual.dates[32],prices,self.actual,builder,float(a.schedule.executed_soc_end[-1]),"continuous_lookahead",(0,6,18))
        self.assertEqual(a.schedule.executed_soc_end[-1],b.schedule.initial_plan.initial_soc_kwh)

    def test_issue_18_forecast_isolation(self):
        from src.question3.forecast_loader import load_forecasts
        from src.question3.rolling_scenario_builder import RollingScenarioBuilder
        from src.question3.rolling_controller import solve_day as q3_day
        forecasts = load_forecasts()
        target = self.actual.dates[31]
        original = q3_day(target,self.price.price,RollingScenarioBuilder(self.actual,forecasts),(0,6,12),1200,"continuous_lookahead")
        changed = forecasts.copy()
        issues = changed[target].issues.copy()
        issues[18] = replace(issues[18],hourly_power_kw=np.full(24,1e9))
        changed[target] = replace(changed[target],issues=issues)
        other = q3_day(target,self.price.price,RollingScenarioBuilder(self.actual,changed),(0,6,12),1200,"continuous_lookahead")
        np.testing.assert_array_equal(original.executed_grid,other.executed_grid)
        np.testing.assert_array_equal(original.executed_soc_end,other.executed_soc_end)

    def test_price_continuation_information_boundary(self):
        from src.pricing import continuation_price_for_date
        target, tomorrow = self.actual.dates[31:33]
        prices = {target:self.price.price,tomorrow:np.full(144,1e9)}
        np.testing.assert_array_equal(continuation_price_for_date(prices,target),self.price.price)
        np.testing.assert_array_equal(continuation_price_for_date(prices,target,"advance_known_sensitivity"),prices[tomorrow])

    def test_jan1_initialization_no_future_actual(self):
        from src.soc_initialization import control_start_soc, warmup_rows
        modified = replace(self.actual,net_load_kwh=np.full((365,144),1e9))
        self.assertEqual(control_start_soc("jan1_continuous",modified),6000)
        self.assertEqual(control_start_soc("feb1_control_start",self.actual),6000)
        rows=warmup_rows(self.actual)
        self.assertEqual(len(rows),31)
        self.assertEqual(rows[0]["date"],"2025-01-01")
        self.assertEqual(rows[-1]["terminal_soc_kwh"],6000)


class ContinuousExport(TestCase):
    @classmethod
    def setUpClass(cls):
        from src.question2.pipeline import run_annual
        cls.price=load_price()
        cls.actual=load_actual(price=cls.price)
        cls.results=run_annual(cls.price,cls.actual,"continuous_myopic")

    def test_no_daily_reset_in_continuous_mode(self):
        for a,b in zip(self.results,self.results[1:]):
            self.assertEqual(a.plan.terminal_soc_kwh,b.plan.initial_soc_kwh)
        self.assertEqual(self.results[1].plan.initial_soc_kwh,1200)

    def test_excel_soc_boundary_continuity(self):
        import shutil
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from openpyxl import load_workbook
        from src.question2.exporter import export_result
        with TemporaryDirectory() as directory:
            path=Path(directory)/"result.xlsx"
            shutil.copy2(cfg.RESULT_XLSX,path)
            export_result(self.price.price,self.results,path)
            workbook=load_workbook(path,read_only=True,data_only=True)
            cells=list(workbook["充放电量"].values)
            for i,result in enumerate(self.results):
                self.assertAlmostEqual(cells[1+6*i][5],result.plan.initial_soc_kwh,places=6)
                self.assertAlmostEqual(cells[2+6*i][5],result.plan.terminal_soc_kwh,places=6)
            workbook.close()
