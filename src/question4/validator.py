"""复用物理约束验证，并按原始逐时动态价格独立核算全部费用。"""
import numpy as np
from ..question2.validator import validate_evaluation, require
from ..question3.validator import validate_day
from . import config as cfg
from .price_loader import get_daily_price


def validate_q42(prices, results, complete=True):
    if complete:
        require(tuple(r.plan.date for r in results) == cfg.OUTPUT_DATES, "Q4-2", "expected all 334 dates")
    for result in results:
        q = get_daily_price(prices, result.plan.date)
        validate_evaluation(q, result)
        cost = float(q @ result.plan.grid_kwh + (5 * q) @ result.emergency_kwh)
        require(abs(result.total_cost - cost) <= cfg.COST_TOL, str(result.plan.date), "Q4-2 dynamic cost identity")
    for a,b in zip(results,results[1:]):
        require(abs(a.plan.terminal_soc_kwh-b.plan.initial_soc_kwh)<=cfg.COST_TOL,"Q4-2","cross-day SOC discontinuity")


def validate_q43(prices, results, complete=True, update_hours=cfg.Q4_3_UPDATE_HOURS):
    if complete:
        require(tuple(r.schedule.date for r in results) == cfg.OUTPUT_DATES, "Q4-3", "expected all 334 dates")
    for result in results:
        q = get_daily_price(prices, result.schedule.date)
        validate_day(q, result, update_hours)
        cash = sum(float(1.5 * q[r.start_slot:] @ r.up_adjust - 0.5 * q[r.start_slot:] @ r.down_adjust)
                   for r in result.schedule.revisions)
        cost = float(q @ result.schedule.initial_plan.grid_kwh + cash + (5 * q) @ result.real_emergency)
        require(np.isfinite(cost) and abs(result.total_cost - cost) <= cfg.COST_TOL,
                str(result.schedule.date), "Q4-3 dynamic cost identity")
    for a,b in zip(results,results[1:]):
        require(abs(a.schedule.executed_soc_end[-1]-b.schedule.initial_plan.initial_soc_kwh)<=cfg.COST_TOL,"Q4-3","cross-day SOC discontinuity")
