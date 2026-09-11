"""实验设计预先固定；物理参数、窗口与日期由原模型提供。"""
from ..question2 import config as physical
from ..question3.config import Q3_FINAL_UPDATE_HOURS

OUTPUT_DIR = physical.PROJECT_ROOT / "target" / "benchmark"
OUTPUT_DATES = physical.OUTPUT_DATES
METHODS = ("DET", "Q80", "SAA", "CVAR", "MPC")
METHOD_NAMES = {"DET": "DET", "Q80": "Q80", "SAA": "SAA", "CVAR": "CVaR95-L50", "MPC": "SAA-MPC"}
MAIN_ALPHA = 0.95
MAIN_LAMBDA = 0.50
SENSITIVITY_ALPHAS = (0.90, 0.95, 0.99)
SENSITIVITY_LAMBDAS = (0.25, 0.50, 0.75, 1.00)
FIGURE_NAMES = ("annual_total_cost", "cost_components", "emergency_risk", "risk_return", "cvar_sensitivity", "runtime")
# Annual sums and daily/paper values must reproduce at numerical precision.
BASELINE_ATOL = physical.RESIDUAL_TOL
BASELINE_RTOL = 1e-10


def sensitivity_name(alpha, risk_weight):
    return f"CVaR{round(100 * alpha):02d}-L{round(100 * risk_weight):02d}"
