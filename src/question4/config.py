"""第四问仅改变价格，并继承第三问消融选定的更新时间。"""
from ..question3.config import (
    PROJECT_ROOT, ACTUAL_XLSX, FORECAST_XLSX, ANNUAL_DATES, OUTPUT_DATES,
    PAPER_DATES, Q3_FINAL_UPDATE_HOURS,
)

PRICE_XLSX = PROJECT_ROOT / "data" / "附件4.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "target" / "question4"
RESULT42_XLSX = PROJECT_ROOT / "target" / "附件5" / "result4-2.xlsx"
RESULT43_XLSX = PROJECT_ROOT / "target" / "附件5" / "result4-3.xlsx"
Q4_3_UPDATE_HOURS = Q3_FINAL_UPDATE_HOURS
assert Q4_3_UPDATE_HOURS == (0, 6, 12)
COST_TOL = 1e-6
