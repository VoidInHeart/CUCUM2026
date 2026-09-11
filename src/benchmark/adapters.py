"""集中隔离原模型接口；求解、场景构造、结算与校验均直接复用。"""
from ..question2 import optimizer as q2_optimizer
from ..question2.pipeline import run_annual as run_saa
from ..question2.scenario_builder import build_rolling_scenarios
from ..question2.evaluator import evaluate as settle_static
from ..question2.validator import validate_complete as validate_static_year
from ..question3.analysis import evaluate_update_policy
from ..question3.rolling_scenario_builder import RollingScenarioBuilder
from . import config as cfg


def solve_saa(price, scenarios):
    return q2_optimizer.solve(price, scenarios)


def saa_structure():
    """CVaR仅扩展原矩阵，不复制储能或场景约束；升级原模型时检查布局。"""
    matrix, bounds = q2_optimizer._structure()
    t, s = cfg.physical.N_SLOTS, cfg.physical.HISTORY_WINDOW_DAYS
    if matrix.shape != (s * t + t + 1, (4 + 2 * s) * t):
        raise RuntimeError("question2 LP layout changed; update benchmark adapter")
    return matrix, list(bounds)


def run_mpc(price, annual, forecasts):
    if cfg.Q3_FINAL_UPDATE_HOURS != (0, 6, 12):
        raise ValueError("benchmark requires the official 0+6+12 policy")
    builder = RollingScenarioBuilder(annual, forecasts)
    return evaluate_update_policy(cfg.Q3_FINAL_UPDATE_HOURS, price, annual, builder)


def plan_static(method, target_date, price, annual, *, alpha=cfg.MAIN_ALPHA, risk_weight=cfg.MAIN_LAMBDA):
    """全年数据只交给原历史切片入口，所有静态优化器只能看到切片。"""
    from . import deterministic, quantile, cvar_saa
    scenarios = build_rolling_scenarios(annual, annual.dates.index(target_date))
    if method == "DET":
        return deterministic.solve(price, scenarios)
    if method == "Q80":
        return quantile.solve(price, scenarios)
    if method == "SAA":
        return solve_saa(price, scenarios)
    if method == "CVAR":
        return cvar_saa.solve(price, scenarios, alpha=alpha, risk_weight=risk_weight)
    raise ValueError(f"unknown static method: {method}")
