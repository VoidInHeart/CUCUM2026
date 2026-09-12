"""输入、历史场景、冻结计划及实际结算数据对象。"""
from dataclasses import dataclass
from datetime import date
import numpy as np


@dataclass(frozen=True)
class DailyPriceData:
    slot_labels: tuple
    price: np.ndarray


@dataclass(frozen=True)
class AnnualActualData:
    dates: tuple[date, ...]
    load_kw: np.ndarray
    pv_kw: np.ndarray
    net_load_kwh: np.ndarray


@dataclass(frozen=True)
class ScenarioSet:
    target_date: date
    history_dates: tuple[date, ...]
    net_load_kwh: np.ndarray
    probability: np.ndarray
    method: str = "raw_equal"
    load_kw: np.ndarray | None = None
    pv_kw: np.ndarray | None = None


@dataclass(frozen=True)
class DailyPlan:
    date: date
    grid_kwh: np.ndarray
    charge_kwh: np.ndarray
    discharge_kwh: np.ndarray
    soc_end_kwh: np.ndarray
    expected_emergency_kwh: float
    expected_objective: float  # 包含微小吞吐量惩罚，仅用于诊断


@dataclass(frozen=True)
class DailyEvaluation:
    plan: DailyPlan
    actual_net_load_kwh: np.ndarray
    emergency_kwh: np.ndarray
    surplus_kwh: np.ndarray
    planned_grid_total: float
    emergency_total: float
    total_grid_purchase: float
    planned_cost: float
    emergency_cost: float
    total_cost: float
    scenario_method: str = "raw_equal"
    mean_scenario_load_kwh: float | None = None
    p80_scenario_load_kwh: float | None = None
    actual_load_kwh: float | None = None
    scenario_mean_bias_kwh: float | None = None
    scenario_p80_coverage: float | None = None


@dataclass(frozen=True)
class EmergencyInterval:
    start_slot: int
    end_slot: int  # Python 切片的右开端点
    label: str
    amount_kwh: float


def readonly(values) -> np.ndarray:
    result = np.array(values, dtype=float, copy=True)
    result.setflags(write=False)
    return result
