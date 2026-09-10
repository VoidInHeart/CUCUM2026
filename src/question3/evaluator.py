"""所有决策冻结后独立结算真实负荷，累计全部revision的交易现金流。"""
import numpy as np

from ..question2.validator import array_check
from . import config as cfg
from .types import DailyResult, readonly
from .validator import validate_day


def evaluate_actual_day(price, schedule, actual_net_load, update_hours=cfg.ISSUE_HOURS):
    array_check(actual_net_load, (144,), str(schedule.date), "actual net load")
    supplied = schedule.executed_grid + schedule.executed_discharge - schedule.executed_charge
    emergency = readonly(np.maximum(actual_net_load - supplied, 0))
    surplus = readonly(np.maximum(supplied - actual_net_load, 0))
    plan_cost = float(price @ schedule.initial_plan.grid_kwh)
    adjustment_cost = float(sum(revision.adjustment_cashflow_yuan for revision in schedule.revisions))
    emergency_cost = float(cfg.EMERGENCY_PRICE_MULTIPLIER * price @ emergency)
    initial_energy = float(schedule.initial_plan.grid_kwh.sum())
    executed_energy, emergency_energy = float(schedule.executed_grid.sum()), float(emergency.sum())
    result = DailyResult(schedule, readonly(actual_net_load), emergency, surplus, plan_cost, adjustment_cost, emergency_cost,
                         plan_cost + adjustment_cost + emergency_cost, initial_energy, executed_energy, emergency_energy,
                         executed_energy + emergency_energy)
    validate_day(price, result, update_hours)
    return result
