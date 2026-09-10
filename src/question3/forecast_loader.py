"""附件3固定四行分组；仅解析每组首行日期。"""
from pathlib import Path
from datetime import time
import numpy as np
import pandas as pd

from . import config as cfg
from .types import DailyPVForecast, ForecastIssue, readonly


def load_forecasts(path: Path = cfg.FORECAST_XLSX) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: forecast_loader: file missing")
    try:
        frame = pd.read_excel(path, sheet_name="Sheet1", engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"{path}: forecast_loader: {exc}") from exc
    expected = ["日期", "预报时刻"] + [f"预报{i}小时" for i in range(1, 25)]
    if list(frame.columns) != expected or frame.shape != (1460, 26):
        raise ValueError(f"{path}: forecast_loader: expected 1460 x 26 data and official headers")
    try:
        numbers = frame.iloc[:, 2:].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{path}: forecast_loader: non-numeric power") from exc
    if not np.isfinite(numbers).all() or (numbers < 0).any():
        raise ValueError(f"{path}: forecast_loader: NaN / Inf or negative power")
    result = {}
    for i, expected_date in enumerate(cfg.ANNUAL_DATES):
        start = 4 * i
        try:
            day = pd.Timestamp(frame.iloc[start, 0]).date()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path}: row {start + 2}: invalid first-row date") from exc
        if day != expected_date:
            raise ValueError(f"{path}: row {start + 2}: expected date {expected_date}, got {day}")
        hours = [f"{value.hour}:{value.minute:02d}" if isinstance(value, time) else str(value).strip()
                 for value in frame.iloc[start:start + 4, 1]]
        if hours != [f"{hour}:00" for hour in cfg.ISSUE_HOURS]:
            raise ValueError(f"{path}: {day}: expected issue sequence 0/6/12/18, got {hours}")
        result[day] = DailyPVForecast(day, {hour: ForecastIssue(hour, readonly(numbers[start + j]))
                                          for j, hour in enumerate(cfg.ISSUE_HOURS)})
    return result
