"""按原始slot位置合并连续事件，保留官方标签中的 +1。"""
import re
import numpy as np

from . import config as cfg
from .types import EmergencyInterval
from .validator import array_check

LABEL_PATTERN = re.compile(r"^(?:[01]?\d|2[0-4]):[0-5]?\d(?:\+1)?-(?:[01]?\d|2[0-4]):[0-5]?\d(?:\+1)?$")


def validate_labels(slot_labels: list[str]) -> None:
    if len(slot_labels) != cfg.N_SLOTS or any(not isinstance(label, str) or not LABEL_PATTERN.fullmatch(label) for label in slot_labels):
        raise ValueError("emergency: expected 144 official interval labels")
    if len(set(slot_labels)) != cfg.N_SLOTS:
        raise ValueError("emergency: duplicate interval labels")


def merge_emergency_intervals(slot_labels: list[str], emergency_kwh: np.ndarray) -> list[EmergencyInterval]:
    validate_labels(slot_labels)
    array_check(emergency_kwh, (cfg.N_SLOTS,), "emergency", "emergency_kwh", True)
    active = emergency_kwh > cfg.EMERGENCY_TOL
    boundaries = np.diff(np.r_[False, active, False].astype(int))
    starts, ends = np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1)
    return [EmergencyInterval(int(start), int(end),
                              slot_labels[start].split("-")[0] + "-" + slot_labels[end - 1].split("-")[1],
                              float(emergency_kwh[start:end].sum())) for start, end in zip(starts, ends)]
