"""严格读取附件1，始终保持原始行顺序。"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as cfg

COLUMNS = ["时间", "电价", "小区负载", "光伏发电预测功率"]


@dataclass
class Question1Input:
    raw_time: list
    price: np.ndarray
    load_kw: np.ndarray
    pv_kw: np.ndarray
    load_kwh: np.ndarray
    pv_kwh: np.ndarray


def load_input(path: Path = cfg.INPUT_XLSX) -> Question1Input:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path}: input file does not exist")
    try:
        frame = pd.read_excel(path, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"{path}: data_loader: cannot read workbook: {exc}") from exc
    if list(frame.columns) != COLUMNS:
        raise ValueError(f"{path}: expected columns {COLUMNS}, got {list(frame.columns)}")
    if len(frame) != cfg.N_SLOTS:
        raise ValueError(f"{path}: expected {cfg.N_SLOTS} data rows, got {len(frame)}")
    if frame[COLUMNS[0]].isna().any():
        raise ValueError(f"{path}: 时间: missing value")
    arrays = []
    for name in COLUMNS[1:]:
        try:
            values = pd.to_numeric(frame[name], errors="raise").to_numpy(dtype=float)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{path}: {name}: non-numeric value") from exc
        if not np.isfinite(values).all():
            raise ValueError(f"{path}: {name}: NaN / Inf")
        if (values < 0).any():
            raise ValueError(f"{path}: {name}: negative values are unsupported by this model")
        arrays.append(values)
    price, load, pv = arrays
    return Question1Input(frame[COLUMNS[0]].tolist(), price, load, pv,
                          load * cfg.TIME_STEP_HOURS, pv * cfg.TIME_STEP_HOURS)
