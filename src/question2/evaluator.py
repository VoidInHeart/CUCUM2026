"""冻结0:00计划后，使用当天真实净负荷作事后评价，不再次优化。"""
import numpy as np

from . import config as cfg
from .types import DailyEvaluation, DailyPlan, readonly
from .validator import array_check, validate_evaluation


def evaluate(price: np.ndarray, plan: DailyPlan, actual_net_load_kwh: np.ndarray) -> DailyEvaluation:
    array_check(actual_net_load_kwh, (cfg.N_SLOTS,), str(plan.date), "actual net load")
    scheduled = plan.grid_kwh + plan.discharge_kwh - plan.charge_kwh
    emergency = readonly(np.maximum(actual_net_load_kwh - scheduled, 0))
    surplus = readonly(np.maximum(scheduled - actual_net_load_kwh, 0))
    planned_total = float(plan.grid_kwh.sum())
    emergency_total = float(emergency.sum())
    planned_cost = float(price @ plan.grid_kwh)
    emergency_cost = float(cfg.EMERGENCY_PRICE_MULTIPLIER * price @ emergency)
    evaluation = DailyEvaluation(plan, readonly(actual_net_load_kwh), emergency, surplus,
                                 planned_total, emergency_total, planned_total + emergency_total,
                                 planned_cost, emergency_cost, planned_cost + emergency_cost)
    validate_evaluation(price, evaluation)
    return evaluation
