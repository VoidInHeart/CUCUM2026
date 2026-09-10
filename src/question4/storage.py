"""完整结果、价格快照及同策略比较存档；只重绘时检查输入哈希。"""
from datetime import date
import hashlib
import json
from pathlib import Path
import numpy as np

from ..question2.types import DailyPlan, DailyEvaluation, readonly
from ..question2.summary import build_summaries
from ..question3.summary import build_summary
from ..question3.storage import write_json, write_csv, save_daily_results, load_daily_results
from . import config as cfg
from .price_loader import get_daily_price
from .validator import validate_q42, validate_q43


def input_hashes(model):
    from ..question2.config import PRICE_XLSX as FIXED_PRICE_XLSX
    paths = [cfg.PRICE_XLSX, cfg.ACTUAL_XLSX, FIXED_PRICE_XLSX]
    if model == "4-3": paths.append(cfg.FORECAST_XLSX)
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def save_analysis(directory, model, prices, results, labels, dynamic_rows, fixed_rows, comparison):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    summary = build_summaries(results, labels) if model == "4-2" else build_summary(results, labels)
    for day, tables in summary["paper_dates"].items():
        tables["dynamic_price_yuan_per_kwh"] = get_daily_price(prices, date.fromisoformat(day))
        tables["price_slot_labels"] = prices.slot_labels
    summary["update_hours"] = comparison["update_hours"]
    write_json(directory / "summary.json", summary)
    save_daily_results(directory / "daily_results.jsonl", results)
    write_json(directory / "prices.json", {"dates": prices.dates, "slot_labels": prices.slot_labels,
                                         "price_yuan_per_kwh": prices.price_yuan_per_kwh})
    write_json(directory / "comparison.json", comparison)
    write_csv(directory / "comparison.csv", comparison["changes"])
    write_csv(directory / "daily_metrics.csv", dynamic_rows)
    write_csv(directory / "fixed_price_daily_metrics.csv", fixed_rows)
    write_json(directory / "daily_metrics.json", {"dynamic": dynamic_rows, "fixed": fixed_rows})
    write_json(directory / "manifest.json", {"schema": 1, "model": model, "update_hours": comparison["update_hours"],
                                            "input_sha256": input_hashes(model)})


def load_analysis(directory, model, prices):
    directory = Path(directory)
    def read(name): return json.loads((directory / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")
    hours = [0] if model == "4-2" else list(cfg.Q4_3_UPDATE_HOURS)
    if manifest != {"schema": 1, "model": model, "update_hours": hours, "input_sha256": input_hashes(model)}:
        raise ValueError("question4 stored input hashes / model / policy changed; rerun calculation")
    stored_prices = read("prices.json")
    if (stored_prices["dates"] != list(map(str, prices.dates)) or stored_prices["slot_labels"] != list(prices.slot_labels)
            or not np.array_equal(stored_prices["price_yuan_per_kwh"], prices.price_yuan_per_kwh)):
        raise ValueError("question4 stored daily prices differ from input")
    path = directory / "daily_results.jsonl"
    if model == "4-3":
        results = load_daily_results(path)
        validate_q43(prices, results)
    else:
        results = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                plan = record.pop("plan")
                plan["date"] = date.fromisoformat(plan["date"])
                for key in ("grid_kwh", "charge_kwh", "discharge_kwh", "soc_end_kwh"): plan[key] = readonly(plan[key])
                for key in ("actual_net_load_kwh", "emergency_kwh", "surplus_kwh"): record[key] = readonly(record[key])
                results.append(DailyEvaluation(plan=DailyPlan(**plan), **record))
        validate_q42(prices, results)
    rows = read("daily_metrics.json")
    return results, rows["dynamic"], rows["fixed"], read("comparison.json")
