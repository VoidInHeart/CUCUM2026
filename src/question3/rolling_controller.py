"""先执行至下个更新点，再改剩余区间；已执行数组独立保存。"""
import logging
import numpy as np

from . import config as cfg
from .optimizer import solve_initial_plan, solve_adjustment
from .types import DailySchedule, readonly
from .validator import validate_schedule


def validate_policy(update_hours):
    if (not isinstance(update_hours, tuple) or not update_hours or update_hours[0] != 0
            or tuple(sorted(set(update_hours))) != update_hours or any(hour not in cfg.ISSUE_HOURS for hour in update_hours)):
        raise ValueError("rolling_controller: update hours must start at 0 and increase within (0,6,12,18)")


def solve_day(target_date, price, builder, update_hours=cfg.ISSUE_HOURS) -> DailySchedule:
    validate_policy(update_hours)
    plan0 = solve_initial_plan(price, builder.build(target_date, 0))
    logging.debug("%s 0:00 solved", target_date)
    fields = ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh")
    current = [getattr(plan0, name).copy() for name in fields]
    executed = [np.full(144, np.nan) for _ in fields]
    revisions = []
    for i, hour in enumerate(update_hours):
        start = cfg.ISSUE_SLOT[hour]
        stop = cfg.ISSUE_SLOT[update_hours[i + 1]] if i + 1 < len(update_hours) else 144
        if hour:
            # 界面输入只包含前版未来合同、已执行段末SOC和当前场景。
            boundary_soc = executed[3][start - 1]
            revision = solve_adjustment(price, builder.build(target_date, hour), current[0][start:].copy(), boundary_soc)
            revisions.append(revision)
            for values, field in zip(current, fields):
                values[start:] = getattr(revision.plan, field)
            logging.debug("%s %d:00 adjusted, cashflow=%.6f", target_date, hour, revision.adjustment_cashflow_yuan)
        for frozen, values in zip(executed, current):
            if not np.isnan(frozen[start:stop]).all():
                raise RuntimeError(f"{target_date} {hour}: rolling_controller: attempted to overwrite executed slots")
            frozen[start:stop] = values[start:stop]
    schedule = DailySchedule(plan0, tuple(revisions), *(readonly(values) for values in executed))
    validate_schedule(price, schedule, update_hours)
    return schedule
