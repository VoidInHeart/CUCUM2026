"""不可变计划与交易记录；数组由 readonly() 防止意外覆盖。"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import numpy as np

from ..question2.types import readonly


@dataclass(frozen=True)
class ForecastIssue:
    issue_hour: int
    hourly_power_kw: np.ndarray


@dataclass(frozen=True)
class DailyPVForecast:
    date: date
    issues: dict[int, ForecastIssue]


@dataclass(frozen=True)
class RollingScenarios:
    target_date: date
    issue_hour: int
    history_dates: tuple[date, ...]
    forecast_kw: np.ndarray
    pv_scenario_kw: np.ndarray
    net_load_kwh: np.ndarray
    probability: np.ndarray
    horizon_mode: str = "calendar_day"


@dataclass(frozen=True)
class HorizonPlan:
    date: date
    issue_hour: int
    initial_soc_kwh: float
    grid_kwh: np.ndarray
    charge_kwh: np.ndarray
    discharge_kwh: np.ndarray
    soc_end_kwh: np.ndarray
    solver_objective: float
    expected_emergency_kwh: float
    soc_policy: str = "daily_closed"
    horizon_price: np.ndarray | None = None

    @property
    def terminal_soc_kwh(self): return float(self.soc_end_kwh[-1])

    @property
    def issue_datetime(self): return datetime.combine(self.date, time(self.issue_hour))

    @property
    def horizon_slot_datetimes(self):
        return tuple(self.issue_datetime + timedelta(minutes=10*i) for i in range(len(self.grid_kwh)))


@dataclass(frozen=True)
class AdjustmentRevision:
    issue_hour: int
    start_slot: int
    old_grid: np.ndarray
    plan: HorizonPlan
    up_adjust: np.ndarray
    down_adjust: np.ndarray
    adjustment_cashflow_yuan: float

    @property
    def new_grid(self) -> np.ndarray:
        return self.plan.grid_kwh[:len(self.old_grid)]


@dataclass(frozen=True)
class DailySchedule:
    initial_plan: HorizonPlan
    revisions: tuple[AdjustmentRevision, ...]
    executed_grid: np.ndarray
    executed_charge: np.ndarray
    executed_discharge: np.ndarray
    executed_soc_end: np.ndarray

    @property
    def date(self) -> date:
        return self.initial_plan.date


@dataclass(frozen=True)
class DailyResult:
    schedule: DailySchedule
    actual_net_load: np.ndarray
    real_emergency: np.ndarray
    real_surplus: np.ndarray
    plan_cost: float
    adjustment_cost: float
    emergency_cost: float
    total_cost: float
    initial_plan_kwh: float
    executed_adjusted_kwh: float
    emergency_kwh: float
    actual_grid_energy_kwh: float
