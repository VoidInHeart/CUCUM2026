"""以交流侧电量建立稀疏 LP，使用 HiGHS 求解。"""
from dataclasses import dataclass
import logging

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import lil_matrix

from . import config as cfg
from .data_loader import Question1Input


def idx_grid(t: int) -> int:
    return t


def idx_charge(t: int) -> int:
    return cfg.N_SLOTS + t


def idx_discharge(t: int) -> int:
    return 2 * cfg.N_SLOTS + t


def idx_curtail(t: int) -> int:
    return 3 * cfg.N_SLOTS + t


def idx_soc(t: int) -> int:
    return 4 * cfg.N_SLOTS + t


@dataclass
class Question1Solution:
    grid_purchase_kwh: np.ndarray
    charge_kwh: np.ndarray
    discharge_kwh: np.ndarray
    curtailment_kwh: np.ndarray
    soc_end_kwh: np.ndarray
    total_purchase_kwh: float
    total_purchase_cost_yuan: float
    solver_objective: float


def solve(data: Question1Input) -> Question1Solution:
    logging.info("building LP")
    n = cfg.N_SLOTS
    objective = np.zeros(5 * n)
    objective[:n] = data.price
    objective[n:3 * n] = cfg.EPS_THROUGHPUT
    matrix = lil_matrix((2 * n + 1, 5 * n))
    rhs = np.zeros(2 * n + 1)
    rhs[:n] = data.load_kwh - data.pv_kwh
    for t in range(n):
        matrix[t, idx_grid(t)] = 1
        matrix[t, idx_charge(t)] = -1
        matrix[t, idx_discharge(t)] = 1
        matrix[t, idx_curtail(t)] = -1
        matrix[n + t, idx_soc(t)] = 1
        matrix[n + t, idx_charge(t)] = -cfg.ETA_CHARGE
        matrix[n + t, idx_discharge(t)] = 1 / cfg.ETA_DISCHARGE
        if t:
            matrix[n + t, idx_soc(t - 1)] = -1
        else:
            rhs[n] = cfg.INITIAL_SOC_KWH
    matrix[-1, idx_soc(n - 1)] = 1
    rhs[-1] = cfg.FINAL_SOC_KWH
    bounds = ([(0, None)] * n
              + [(0, cfg.BATTERY_ENERGY_MAX_PER_SLOT_KWH)] * (2 * n)
              + [(0, None)] * n
              + [(cfg.SOC_MIN_KWH, cfg.SOC_MAX_KWH)] * n)
    logging.info("solving LP")
    result = linprog(objective, A_eq=matrix.tocsr(), b_eq=rhs,
                     bounds=bounds, method="highs",
                     options={"dual_feasibility_tolerance": 1e-9})
    if not result.success:
        raise RuntimeError(f"optimizer: Question 1 optimization failed: {result.message}")
    logging.debug("HiGHS: %s", result.message)
    grid, charge, discharge, curtail, soc = np.split(result.x, 5)
    return Question1Solution(grid, charge, discharge, curtail, soc,
                             float(grid.sum()), float(data.price @ grid), float(result.fun))
