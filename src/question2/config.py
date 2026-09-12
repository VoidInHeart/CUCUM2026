"""问题2固定配置；复用已经验证的储能参数。"""
from datetime import date, timedelta

from ..question1.config import (
    PROJECT_ROOT, N_SLOTS, BLOCK_SIZE, TIME_STEP_HOURS, SOC_MIN_KWH,
    SOC_MAX_KWH, INITIAL_SOC_KWH, FINAL_SOC_KWH, ETA_CHARGE, ETA_DISCHARGE,
    BATTERY_ENERGY_MAX_PER_SLOT_KWH, EPS_THROUGHPUT, TOL, RESIDUAL_TOL,
)

PRICE_XLSX = PROJECT_ROOT / "data" / "附件1.xlsx"
ACTUAL_XLSX = PROJECT_ROOT / "data" / "附件2.xlsx"
RESULT_XLSX = PROJECT_ROOT / "target" / "附件5" / "result2.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "target" / "question2"
HISTORY_WINDOW_DAYS = 31
EMERGENCY_PRICE_MULTIPLIER = 5.0
EMERGENCY_TOL = 1e-6
# FINAL_SOC_KWH belongs only to Q1 and the legacy daily_closed policy.
BATTERY_REFERENCE_SOC_KWH = 6000.0
CONTROL_START_SOC_KWH = 6000.0
SOC_POLICIES = ("daily_closed", "continuous_myopic", "continuous_lookahead")
START_DATE = date(2025, 2, 1)
END_DATE = date(2025, 12, 31)
ANNUAL_DATES = tuple(date(2025, 1, 1) + timedelta(days=i) for i in range(365))
OUTPUT_DATES = tuple(START_DATE + timedelta(days=i) for i in range((END_DATE - START_DATE).days + 1))
PAPER_DATES = (date(2025, 3, 20), date(2025, 6, 21), date(2025, 9, 23), date(2025, 12, 21))
