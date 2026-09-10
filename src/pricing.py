"""日价格选择：固定144点向量或以日期为键的映射，保持原始时段顺序。"""
from collections.abc import Mapping
from datetime import date
import numpy as np

PriceInput = np.ndarray | Mapping[date, np.ndarray]


def price_for_date(prices: PriceInput, target: date) -> np.ndarray:
    values = prices[target] if isinstance(prices, Mapping) else prices
    values = np.asarray(values, dtype=float)
    if values.shape != (144,) or not np.isfinite(values).all() or (values < 0).any():
        raise ValueError(f"{target}: expected 144 finite nonnegative daily prices")
    return values
