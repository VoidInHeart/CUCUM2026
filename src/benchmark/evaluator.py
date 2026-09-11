"""串行年度执行；计时覆盖构造场景、求解、结算、校验与统一日记录。"""
import logging
import time
import numpy as np

from . import adapters, config as cfg
from .types import DailyMetrics, MethodRun


def static_metrics(method, item):
    c = float(item.plan.charge_kwh.sum())
    d = float(item.plan.discharge_kwh.sum())
    return DailyMetrics(method, str(item.plan.date), item.planned_cost, 0.0, item.planned_cost,
                         item.emergency_cost, item.total_cost, item.planned_grid_total, item.planned_grid_total,
                         item.emergency_total, item.total_grid_purchase,
                         bool(np.any(item.emergency_kwh > cfg.physical.EMERGENCY_TOL)), c, d, c + d)


def mpc_metrics(item):
    c = float(item.schedule.executed_charge.sum())
    d = float(item.schedule.executed_discharge.sum())
    return DailyMetrics(cfg.METHOD_NAMES["MPC"], str(item.schedule.date), item.plan_cost, item.adjustment_cost,
                         item.plan_cost + item.adjustment_cost, item.emergency_cost, item.total_cost,
                         item.initial_plan_kwh, item.executed_adjusted_kwh, item.emergency_kwh,
                         item.actual_grid_energy_kwh, bool(np.any(item.real_emergency > cfg.physical.EMERGENCY_TOL)),
                         c, d, c + d)


def run_method(method, price, annual, forecasts=None, *, alpha=cfg.MAIN_ALPHA, risk_weight=cfg.MAIN_LAMBDA):
    if method not in cfg.METHODS:
        raise ValueError(f"unknown method: {method}")
    name = cfg.sensitivity_name(alpha, risk_weight) if method == "CVAR" else cfg.METHOD_NAMES[method]
    start = time.perf_counter()
    if method == "MPC":
        if forecasts is None:
            raise ValueError("MPC requires forecasts")
        raw = adapters.run_mpc(price, annual, forecasts)
        daily = tuple(mpc_metrics(item) for item in raw)
    else:
        if method == "SAA":
            raw = adapters.run_saa(price, annual)
        else:
            raw = []
            for i, day in enumerate(cfg.OUTPUT_DATES):
                plan = adapters.plan_static(method, day, price, annual, alpha=alpha, risk_weight=risk_weight)
                # 计划冻结后才读取当天实际值；净负荷、PV和未来数据不传入优化器。
                item = adapters.settle_static(price, plan, annual.net_load_kwh[annual.dates.index(day)])
                raw.append(item)
                if i % 30 == 0 or i + 1 == len(cfg.OUTPUT_DATES):
                    logging.info("%s [%03d/%d] %s total_cost=%.3f", name, i + 1, len(cfg.OUTPUT_DATES), day, item.total_cost)
            adapters.validate_static_year(price, raw)
        daily = tuple(static_metrics(name, item) for item in raw)
    elapsed = time.perf_counter() - start
    logging.info("%s complete: %d days in %.3f seconds", name, len(daily), elapsed)
    return MethodRun(name, daily, elapsed), raw
