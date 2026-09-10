"""只读取附件1电价与附件2，不排序日内列。"""
from pathlib import Path
from datetime import time
import numpy as np
import pandas as pd

from . import config as cfg
from .types import AnnualActualData, DailyPriceData, readonly


def _numeric(frame: pd.DataFrame, path: Path, field: str) -> np.ndarray:
    try:
        values = frame.apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{path}: {field}: non-numeric data") from exc
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{path}: {field}: NaN / Inf or negative data")
    return values


def _read(path: Path, **kwargs) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"{path}: data_loader: file does not exist")
    try:
        return pd.read_excel(path, engine="openpyxl", **kwargs)
    except Exception as exc:
        raise ValueError(f"{path}: data_loader: {exc}") from exc


def load_price(path: Path = cfg.PRICE_XLSX) -> DailyPriceData:
    path = Path(path)
    frame = _read(path, usecols=[0, 1])
    if list(frame.columns) != ["时间", "电价"] or frame.shape != (cfg.N_SLOTS, 2):
        raise ValueError(f"{path}: price: expected 144 rows with 时间, 电价 columns")
    if frame["时间"].isna().any():
        raise ValueError(f"{path}: 时间: missing slot label")
    return DailyPriceData(tuple(frame["时间"]), readonly(_numeric(frame[["电价"]], path, "电价")[:, 0]))


def load_actual(path: Path = cfg.ACTUAL_XLSX, price: DailyPriceData | None = None) -> AnnualActualData:
    path = Path(path)
    sheets = ["小区负载", "光伏发电实际功率"]
    frames = [_read(path, sheet_name=name) for name in sheets]
    dates, arrays = [], []
    for name, frame in zip(sheets, frames):
        if frame.shape != (365, 145) or frame.columns[0] != "日期\\时间":
            raise ValueError(f"{path}: {name}: expected 365 x 145 table with 日期\\时间 header, got {frame.shape}")
        try:
            parsed = pd.to_datetime(frame.iloc[:, 0], errors="raise")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path}: {name}: invalid dates") from exc
        days = tuple(parsed.dt.date)
        if days != cfg.ANNUAL_DATES:
            raise ValueError(f"{path}: {name}: expected consecutive dates 2025-01-01 through 2025-12-31")
        dates.append(days)
        arrays.append(_numeric(frame.iloc[:, 1:], path, name))
    if dates[0] != dates[1] or list(frames[0].columns) != list(frames[1].columns):
        raise ValueError(f"{path}: load/PV dates or time columns differ")
    def label(value):
        return f"{value.hour}:{value.minute:02d}" if isinstance(value, time) else str(value).strip()
    if price is not None and tuple(map(label, frames[0].columns[1:])) != tuple(map(label, price.slot_labels)):
        raise ValueError(f"{path}: time columns do not match attachment 1 row order")
    load, pv = arrays
    return AnnualActualData(dates[0], readonly(load), readonly(pv), readonly((load - pv) * cfg.TIME_STEP_HOURS))
