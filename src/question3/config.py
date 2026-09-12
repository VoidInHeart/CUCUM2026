"""复用前两问物理参数，固定问题3交易及时间口径。"""
from ..question2.config import (
    PROJECT_ROOT, PRICE_XLSX, ACTUAL_XLSX, N_SLOTS, BLOCK_SIZE, TIME_STEP_HOURS,
    SOC_MIN_KWH, SOC_MAX_KWH, INITIAL_SOC_KWH, FINAL_SOC_KWH, ETA_CHARGE,
    ETA_DISCHARGE, BATTERY_ENERGY_MAX_PER_SLOT_KWH, EPS_THROUGHPUT, TOL,
    RESIDUAL_TOL, HISTORY_WINDOW_DAYS, EMERGENCY_PRICE_MULTIPLIER, EMERGENCY_TOL,
    START_DATE, END_DATE, ANNUAL_DATES, OUTPUT_DATES, PAPER_DATES,
)

FORECAST_XLSX = PROJECT_ROOT / "data" / "附件3.xlsx"
RESULT_XLSX = PROJECT_ROOT / "target" / "附件5" / "result3.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "target" / "question3"
# 附件3全部预报发布时间；18点仍用于消融对照和预报精度分析。
ISSUE_HOURS = (0, 6, 12, 18)
ISSUE_SLOT = {hour: hour * 6 for hour in ISSUE_HOURS}
UP_ADJUST_PRICE_MULTIPLIER = 1.5
CANCEL_REFUND_MULTIPLIER = 0.5
POLICIES = ((0,), (0, 6), (0, 6, 12), (0, 6, 12, 18), (0, 12, 18), (0, 6, 18))
# 消融选定的官方主策略，同时供第三问主运行和第四问比较使用。
Q3_FINAL_UPDATE_HOURS = (0, 6, 12)
SCENARIO_METHODS = ("raw_equal", "paired_residual_weighted")
SCENARIO_METHOD = "paired_residual_weighted"
