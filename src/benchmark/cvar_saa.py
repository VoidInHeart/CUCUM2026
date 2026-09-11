"""在原SAA稀疏等式约束上添加场景日紧急损失的CVaR线性化。"""
from dataclasses import dataclass, replace
import logging
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import hstack, lil_matrix, csr_matrix

from ..question2.scenario_builder import validate_scenarios
from ..question2.types import DailyPlan, readonly
from ..question2.validator import array_check, require, validate_lp
from . import adapters, config
from .metrics import empirical_cvar

cfg = config.physical


@dataclass(frozen=True)
class RiskSolution:
    plan: DailyPlan
    emergency: np.ndarray
    surplus: np.ndarray
    losses: np.ndarray
    eta: float
    excess: np.ndarray
    expected_loss: float
    cvar_loss: float
    alpha: float
    risk_weight: float


def validate_parameters(alpha, risk_weight):
    if not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("CVaR alpha must be in (0, 1)")
    if not np.isfinite(risk_weight) or not 0 <= risk_weight <= 1:
        raise ValueError("CVaR lambda must be in [0, 1]")


def validate_risk_solution(price, scenarios, result):
    plan = result.plan
    context = f"{plan.date}: CVaR"
    validate_parameters(result.alpha, result.risk_weight)
    penalty = cfg.EPS_THROUGHPUT * (plan.charge_kwh.sum() + plan.discharge_kwh.sum())
    losses = cfg.EMERGENCY_PRICE_MULTIPLIER * result.emergency @ price
    expected = float(scenarios.probability @ losses)
    # 原校验器负责储能、全部场景平衡和期望量；只替换其期望目标诊断值。
    saa_objective = float(price @ plan.grid_kwh + expected + penalty)
    report = validate_lp(price, scenarios, replace(plan, expected_objective=saa_objective),
                         result.emergency, result.surplus)
    array_check(result.losses, losses.shape, context, "scenario losses", True)
    array_check(result.excess, losses.shape, context, "CVaR excess", True)
    require(np.isfinite(result.eta), context, "invalid eta")
    require(np.allclose(result.losses, losses, rtol=0, atol=cfg.RESIDUAL_TOL), context, "loss definition")
    residual = float(np.max(losses - result.eta - result.excess))
    require(residual <= cfg.RESIDUAL_TOL, context, "CVaR epigraph constraint")
    cvar = result.eta + float(scenarios.probability @ result.excess) / (1 - result.alpha)
    exact_cvar = empirical_cvar(losses, result.alpha, scenarios.probability)
    require(abs(cvar - exact_cvar) <= cfg.RESIDUAL_TOL, context, "CVaR linearization mismatch")
    require(abs(result.expected_loss - expected) <= cfg.RESIDUAL_TOL, context, "expected loss mismatch")
    require(abs(result.cvar_loss - cvar) <= cfg.RESIDUAL_TOL, context, "CVaR diagnostic mismatch")
    objective = float(price @ plan.grid_kwh + (1 - result.risk_weight) * expected + result.risk_weight * cvar + penalty)
    require(abs(objective - plan.expected_objective) <= cfg.RESIDUAL_TOL, context, "risk objective mismatch")
    # lambda=1可能有非尾部退化二阶段变量；最低必要紧急量也必须给出同一最优风险目标。
    supplied = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    minimal_losses = cfg.EMERGENCY_PRICE_MULTIPLIER * np.maximum(scenarios.net_load_kwh - supplied, 0) @ price
    minimal_objective = float(price @ plan.grid_kwh + penalty + (1 - result.risk_weight) * (scenarios.probability @ minimal_losses)
                              + result.risk_weight * empirical_cvar(minimal_losses, result.alpha, scenarios.probability))
    require(abs(minimal_objective - objective) <= cfg.RESIDUAL_TOL, context, "nonminimal recourse objective")
    return {**report, "max_cvar_epigraph_residual": max(residual, 0.0)}


def solve_with_diagnostics(price, scenarios, *, alpha=config.MAIN_ALPHA, risk_weight=config.MAIN_LAMBDA):
    validate_parameters(alpha, risk_weight)
    validate_scenarios(scenarios)
    t, s = cfg.N_SLOTS, cfg.HISTORY_WINDOW_DAYS
    array_check(price, (t,), str(scenarios.target_date), "price", True)
    if risk_weight == 0:
        # 完全使用原模型的最优解选择和数值路径，确保所有第一阶段数组严格一致。
        plan = adapters.solve_saa(price, scenarios)
        supplied = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
        emergency = np.maximum(scenarios.net_load_kwh - supplied, 0)
        surplus = np.maximum(supplied - scenarios.net_load_kwh, 0)
        losses = cfg.EMERGENCY_PRICE_MULTIPLIER * emergency @ price
        eta = float(np.sort(losses)[max(0, int(np.ceil(alpha * s)) - 1)])
        excess = np.maximum(losses - eta, 0)
    else:
        matrix, bounds = adapters.saa_structure()
        n = matrix.shape[1]
        a_eq = hstack((matrix, csr_matrix((matrix.shape[0], 1 + s))), format="csr")
        a_ub = lil_matrix((s, n + 1 + s))
        for scenario in range(s):
            a_ub[scenario, 4 * t + scenario * t:4 * t + (scenario + 1) * t] = cfg.EMERGENCY_PRICE_MULTIPLIER * price
            a_ub[scenario, n] = -1
            a_ub[scenario, n + 1 + scenario] = -1
        objective = np.zeros(n + 1 + s)
        objective[:t] = price
        objective[t:3 * t] = cfg.EPS_THROUGHPUT
        objective[4 * t:(4 + s) * t] = ((1 - risk_weight) * cfg.EMERGENCY_PRICE_MULTIPLIER * scenarios.probability[:, None] * price).ravel()
        objective[n] = risk_weight
        objective[n + 1:] = risk_weight * scenarios.probability / (1 - alpha)
        rhs = np.r_[scenarios.net_load_kwh.ravel(), cfg.INITIAL_SOC_KWH, np.zeros(t - 1), cfg.FINAL_SOC_KWH]
        raw = linprog(objective, A_eq=a_eq, b_eq=rhs, A_ub=a_ub.tocsr(), b_ub=np.zeros(s),
                       bounds=bounds + [(None, None)] + [(0, None)] * s, method="highs",
                       options={"dual_feasibility_tolerance": 1e-9})
        if not raw.success:
            raise RuntimeError(f"CVaR optimization failed on {scenarios.target_date}: alpha={alpha} lambda={risk_weight}: HiGHS status {raw.status}: {raw.message}")
        grid, charge, discharge, soc = np.split(raw.x[:4 * t], 4)
        emergency = raw.x[4 * t:(4 + s) * t].reshape(s, t)
        surplus = raw.x[(4 + s) * t:n].reshape(s, t)
        losses = cfg.EMERGENCY_PRICE_MULTIPLIER * emergency @ price
        eta, excess = float(raw.x[n]), raw.x[n + 1:]
        plan = DailyPlan(scenarios.target_date, readonly(grid), readonly(charge), readonly(discharge), readonly(soc),
                         float(scenarios.probability @ emergency.sum(axis=1)), float(raw.fun))
    result = RiskSolution(plan, readonly(emergency), readonly(surplus), readonly(losses), eta, readonly(excess),
                          float(scenarios.probability @ losses), empirical_cvar(losses, alpha, scenarios.probability),
                          alpha, risk_weight)
    report = validate_risk_solution(price, scenarios, result)
    logging.debug("%s CVaR alpha=%s lambda=%s: %s", plan.date, alpha, risk_weight, report)
    return result


def solve(price, scenarios, *, alpha=config.MAIN_ALPHA, risk_weight=config.MAIN_LAMBDA):
    return solve_with_diagnostics(price, scenarios, alpha=alpha, risk_weight=risk_weight).plan
