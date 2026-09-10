"""问题4-3：同日动态价格贯穿0/6/12点的既有滚动模型。"""
from ..question3.rolling_controller import solve_day as solve_schedule
from ..question3.evaluator import evaluate_actual_day
from ..question3.analysis import evaluate_update_policy
from . import config as cfg
from .price_loader import get_daily_price, validate_alignment
from .validator import validate_q43


def solve_day(target_date, prices, actual, builder):
    validate_alignment(prices, actual, builder.forecasts)
    daily_price = get_daily_price(prices, target_date)
    schedule = solve_schedule(target_date, daily_price, builder, cfg.Q4_3_UPDATE_HOURS)
    index = builder.date_index[target_date]
    if actual.dates[index] != target_date:
        raise ValueError(f"{target_date}: actual date index mismatch")
    result = evaluate_actual_day(daily_price, schedule, actual.net_load_kwh[index], cfg.Q4_3_UPDATE_HOURS)
    validate_q43(prices, [result], complete=False)
    return result


def run_annual(prices, actual, builder):
    validate_alignment(prices, actual, builder.forecasts)
    results = evaluate_update_policy(cfg.Q4_3_UPDATE_HOURS, prices.daily_prices(), actual, builder)
    validate_q43(prices, results)
    return results


def main():
    from .main import main as run
    return run(model="4-3")


if __name__ == "__main__":
    raise SystemExit(main())
