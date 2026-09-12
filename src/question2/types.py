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


@dataclass(frozen=True)
class DailyPlan:
    date: date
    grid_kwh: np.ndarray
    charge_kwh: np.ndarray
    discharge_kwh: np.ndarray
    soc_end_kwh: np.ndarray
    expected_emergency_kwh: float
    expected_objective: float  # 包含微小吞吐量惩罚，仅用于诊断
    initial_soc_kwh: float = 6000.0
    soc_policy: str = "daily_closed"
    risk_weight: float = 0.0
    risk_alpha: float = 0.95
    risk_penalty: float = 0.0

    @property
    def terminal_soc_kwh(self) -> float:
        return float(self.soc_end_kwh[-1])


@dataclass(frozen=True)
class MultiDayScenarioSet:
    target_date: date
    history_dates: tuple[date, ...]
    net_load_kwh: np.ndarray
    probability: np.ndarray


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
