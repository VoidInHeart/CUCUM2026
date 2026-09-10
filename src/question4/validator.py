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


def validate_q43(prices, results, complete=True):
    if complete:
        require(tuple(r.schedule.date for r in results) == cfg.OUTPUT_DATES, "Q4-3", "expected all 334 dates")
    for result in results:
        q = get_daily_price(prices, result.schedule.date)
        validate_day(q, result, cfg.Q4_3_UPDATE_HOURS)
        cash = sum(float(1.5 * q[r.start_slot:] @ r.up_adjust - 0.5 * q[r.start_slot:] @ r.down_adjust)
                   for r in result.schedule.revisions)
        cost = float(q @ result.schedule.initial_plan.grid_kwh + cash + (5 * q) @ result.real_emergency)
        require(np.isfinite(cost) and abs(result.total_cost - cost) <= cfg.COST_TOL,
                str(result.schedule.date), "Q4-3 dynamic cost identity")
