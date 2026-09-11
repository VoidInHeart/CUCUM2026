"""统一日记录与方法运行结果；优化器沿用原来的不可变计划类型。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DailyMetrics:
    method: str
    date: str
    plan_cost: float
    adjustment_cost: float
    contract_cost: float
    emergency_cost: float
    total_cost: float
    planned_grid_kwh: float
    contract_grid_kwh: float
    emergency_kwh: float
    total_grid_kwh: float
    emergency_day: bool
    charge_kwh: float
    discharge_kwh: float
    throughput_kwh: float


@dataclass(frozen=True)
class MethodRun:
    method: str
    daily: tuple[DailyMetrics, ...]
    total_runtime_seconds: float
