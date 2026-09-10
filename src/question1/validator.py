"""从原始输入及初始 SOC 独立重建物理约束。"""
import numpy as np

from . import config as cfg
from .data_loader import Question1Input
from .optimizer import Question1Solution


def validate_solution(data: Question1Input, solution: Question1Solution) -> dict[str, float]:
    def require(ok: bool, reason: str) -> None:
        if not ok:
            raise ValueError(f"validator: {reason}")

    for name in ("price", "load_kw", "pv_kw", "load_kwh", "pv_kwh"):
        values = np.asarray(getattr(data, name))
        require(values.shape == (cfg.N_SLOTS,), f"input {name}: wrong shape")
        require(np.isfinite(values).all(), f"input {name}: NaN / Inf")
    for name in ("grid_purchase_kwh", "charge_kwh", "discharge_kwh",
                 "curtailment_kwh", "soc_end_kwh"):
        values = np.asarray(getattr(solution, name))
        require(values.shape == (cfg.N_SLOTS,), f"{name}: wrong shape")
        require(np.isfinite(values).all(), f"{name}: NaN / Inf")
        require((values >= -cfg.TOL).all(), f"{name}: negative energy")
    g, c, d, w, soc = (solution.grid_purchase_kwh, solution.charge_kwh,
                       solution.discharge_kwh, solution.curtailment_kwh, solution.soc_end_kwh)
    for name, values in (("charge", c), ("discharge", d)):
        require(values.max() <= cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH + cfg.TOL,
                f"{name}: slot power limit exceeded")
    require(soc.min() >= cfg.SOC_MIN_KWH - cfg.TOL, "SOC below minimum")
    require(soc.max() <= cfg.SOC_MAX_KWH + cfg.TOL, "SOC above maximum")
    require(abs(soc[-1] - cfg.FINAL_SOC_KWH) <= cfg.RESIDUAL_TOL, "final SOC mismatch")
    balance = g + data.pv_kwh + d - data.load_kwh - c - w
    rebuilt = cfg.INITIAL_SOC_KWH + np.cumsum(cfg.ETA_CHARGE * c - d / cfg.ETA_DISCHARGE)
    report = {"max_balance_residual": float(np.max(np.abs(balance))),
              "max_soc_residual": float(np.max(np.abs(rebuilt - soc)))}
    for name, value in report.items():
        require(value <= cfg.RESIDUAL_TOL, f"{name}: {value} exceeds tolerance")
    require(not np.any((c > cfg.RESIDUAL_TOL) & (d > cfg.RESIDUAL_TOL)),
            "simultaneous charge and discharge")
    for name, expected in (("total_purchase_kwh", g.sum()),
                           ("total_purchase_cost_yuan", data.price @ g),
                           ("solver_objective", data.price @ g + cfg.EPS_THROUGHPUT * (c.sum() + d.sum()))):
        actual = getattr(solution, name)
        require(np.isfinite(actual) and abs(actual - expected) <= cfg.RESIDUAL_TOL,
                f"{name}: invalid total")
    return report
