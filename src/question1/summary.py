"""论文表1、表2的数据接口；标签仅用于摘要查找。"""
import numpy as np

from . import config as cfg

TABLE1_LABELS = [f"{hour}:00-{hour}:10" for hour in (10, 12, 14, 16, 18, 20)]
BLOCK_LABELS = [f"{hour}:00-{hour + 4}:00" for hour in range(0, 24, 4)]


def build_table1_summary(interval_labels: list[str], grid_purchase_kwh: np.ndarray,
                         price: np.ndarray) -> dict[str, float]:
    if len(interval_labels) != cfg.N_SLOTS or len(set(interval_labels)) != cfg.N_SLOTS:
        raise ValueError("summary: expected 144 distinct template interval labels")
    label_to_index = {label: i for i, label in enumerate(interval_labels)}
    missing = set(TABLE1_LABELS) - label_to_index.keys()
    if missing:
        raise ValueError(f"summary: template missing labels: {sorted(missing)}")
    result = {label: float(grid_purchase_kwh[label_to_index[label]]) for label in TABLE1_LABELS}
    result["全天购电量"] = float(np.sum(grid_purchase_kwh))
    result["全天购电费"] = float(np.dot(price, grid_purchase_kwh))
    return result


def build_table2_summary(charge_kwh: np.ndarray, discharge_kwh: np.ndarray) -> dict:
    if np.shape(charge_kwh) != (cfg.N_SLOTS,) or np.shape(discharge_kwh) != (cfg.N_SLOTS,):
        raise ValueError("summary: expected 144 charge/discharge slots")
    result = {}
    for k, label in enumerate(BLOCK_LABELS):
        block = slice(k * cfg.BLOCK_SIZE, (k + 1) * cfg.BLOCK_SIZE)
        result[label] = {"累计充电量": float(charge_kwh[block].sum()),
                         "累计放电量": float(discharge_kwh[block].sum())}
    result["0:00 储电量"] = cfg.INITIAL_SOC_KWH
    result["24:00 储电量"] = cfg.FINAL_SOC_KWH
    return result
