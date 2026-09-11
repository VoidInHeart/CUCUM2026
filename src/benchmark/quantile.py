"""Q80是分位数启发式，不等价于完整随机规划。"""
import numpy as np

from ..question2.scenario_builder import validate_scenarios
from ..question2.types import readonly
from .deterministic import solve_curve


def forecast(scenarios):
    validate_scenarios(scenarios)
    return readonly(np.quantile(scenarios.net_load_kwh, 0.8, axis=0, method="linear"))


def solve(price, scenarios):
    return solve_curve(price, scenarios.target_date, forecast(scenarios))
