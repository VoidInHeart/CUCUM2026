"""过去窗口的逐slot均值，经问题1原储能LP形成确定性计划。"""
import numpy as np

from ..question1.data_loader import Question1Input
from ..question1.optimizer import solve as solve_physical_lp
from ..question1.validator import validate_solution
from ..question2.scenario_builder import validate_scenarios
from ..question2.types import DailyPlan, readonly
from ..question2.validator import array_check, validate_plan
from .config import physical as cfg


def forecast(scenarios):
    validate_scenarios(scenarios)
    # 同一历史值无论来自F/C布局数组都按相同次序归约，保证扰动隔离测试逐位一致。
    return readonly(np.mean(np.ascontiguousarray(scenarios.net_load_kwh), axis=0))


def solve_curve(price, target_date, net_load_kwh):
    """仅接受已生成的曲线；正负分解只是适配输入，不另行预测负载/PV。"""
    array_check(price, (cfg.N_SLOTS,), str(target_date), "price", True)
    array_check(net_load_kwh, (cfg.N_SLOTS,), str(target_date), "forecast")
    load = np.maximum(net_load_kwh, 0)
    pv = np.maximum(-net_load_kwh, 0)
    data = Question1Input(list(range(cfg.N_SLOTS)), price, load / cfg.TIME_STEP_HOURS,
                          pv / cfg.TIME_STEP_HOURS, load, pv)
    result = solve_physical_lp(data)
    validate_solution(data, result)
    plan = DailyPlan(target_date, readonly(result.grid_purchase_kwh), readonly(result.charge_kwh),
                     readonly(result.discharge_kwh), readonly(result.soc_end_kwh), 0.0,
                     result.solver_objective)
    validate_plan(plan)
    return plan


def solve(price, scenarios):
    return solve_curve(price, scenarios.target_date, forecast(scenarios))
