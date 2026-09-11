"""基线复现是强制门禁；只读取官方结果，绝不重写它们。"""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

from ..question2.exporter import read_template_labels as q2_labels
from ..question2.summary import build_summaries
from ..question3.exporter import read_template_labels as q3_labels
from ..question3.summary import build_summary
from ..question3.analysis import daily_metrics as q3_daily_metrics
from ..question2.summary import daily_metrics as q2_daily_metrics
from . import config as cfg


def sha256(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def protected_snapshot():
    """覆盖问题1—4结果、附件5、历史备份及既有日志。"""
    root = cfg.physical.PROJECT_ROOT
    return {str(path.relative_to(root)).replace("\\", "/"): sha256(path)
            for path in sorted((root / "target").rglob("*"))
            if path.is_file() and cfg.OUTPUT_DIR not in path.parents}


def check_preserved(before):
    after = protected_snapshot()
    if after != before:
        changed = [name for name in set(before) | set(after) if before.get(name) != after.get(name)]
        raise ValueError(f"protected official files changed: {changed}")
    return {"status": "passed", "file_count": len(before), "sha256": before}


def compare_numbers(actual, expected, context):
    details = {}
    for key, ref in expected.items():
        if not isinstance(ref, (float, int)):
            if key == "period" and actual.get(key) != ref:
                raise ValueError(f"{context}: baseline period mismatch")
            continue
        value = actual.get(key)
        if value is None or not np.isclose(value, ref, rtol=cfg.BASELINE_RTOL, atol=cfg.BASELINE_ATOL):
            raise ValueError(f"{context}: baseline mismatch for {key}: computed={value}, official={ref}")
        details[key] = {"computed": value, "official": ref, "absolute_error": abs(value - ref)}
    if not details:
        raise ValueError(f"{context}: no baseline metrics found")
    return details


def validate_baseline(method, raw, root=None):
    root = Path(root) if root is not None else cfg.physical.PROJECT_ROOT / "target"
    if method == "SAA":
        path = root / "question2" / "summary.json"
        current = build_summaries(raw, q2_labels())
        daily = [q2_daily_metrics(item) for item in raw]
        daily_path = root / "question2" / "daily_metrics.csv"
    elif method == "MPC":
        path = root / "question3" / "summary.json"
        current = build_summary(raw, q3_labels())
        daily = [q3_daily_metrics(item) for item in raw]
        daily_path = root / "question3" / "policy_daily_metrics.csv"
    else:
        raise ValueError("only SAA and MPC have official baselines")
    expected = json.loads(path.read_text(encoding="utf-8"))
    if method == "MPC" and (expected.get("update_hours") != list(cfg.Q3_FINAL_UPDATE_HOURS)
                             or expected.get("policy") != "0+6+12"
                             or current.get("update_hours") != list(cfg.Q3_FINAL_UPDATE_HOURS)):
        raise ValueError("MPC baseline must be the official 0+6+12 policy")
    annual = compare_numbers(current["annual"], expected["annual"], method)
    with daily_path.open(encoding="utf-8-sig", newline="") as handle:
        saved = list(csv.DictReader(handle))
    if method == "MPC":
        saved = [row for row in saved if row["policy"] == "0+6+12"]
    if [row["date"] for row in saved] != [str(day) for day in cfg.OUTPUT_DATES] or len(daily) != len(saved):
        raise ValueError(f"{method}: official daily baseline dates mismatch")
    max_daily_error = 0.0
    for actual_row, saved_row in zip(daily, saved):
        if actual_row["date"] != saved_row["date"]:
            raise ValueError(f"{method}: computed daily dates mismatch")
        refs = {key: float(saved_row[key]) for key in actual_row if key != "date"}
        errors = compare_numbers(actual_row, refs, f"{method} {actual_row['date']}")
        max_daily_error = max(max_daily_error, *(item["absolute_error"] for item in errors.values()))
    return {"status": "passed", "source": str(path), "summary_sha256": sha256(path),
            "daily_source": str(daily_path), "daily_sha256": sha256(daily_path),
            "rtol": cfg.BASELINE_RTOL, "atol": cfg.BASELINE_ATOL, "annual": annual,
            "daily_rows_checked": len(daily), "max_daily_absolute_error": max_daily_error}


def require_baselines(reports):
    for method in ("SAA", "MPC"):
        if reports.get(method, {}).get("status") != "passed":
            raise ValueError(f"{method}: baseline not reproduced; refusing to export paper results")
