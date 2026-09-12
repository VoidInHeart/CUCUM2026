"""问题4-3：同日动态价格贯穿0/6/12点的既有滚动模型。"""
from ..question3.rolling_controller import solve_day as solve_schedule
from ..question3.evaluator import evaluate_actual_day
from ..question3.analysis import evaluate_update_policy
from . import config as cfg
from .price_loader import get_daily_price, validate_alignment
from .validator import validate_q43


def solve_day(target_date, prices, actual, builder, initial_soc_kwh=None, soc_policy="daily_closed",
              update_hours=cfg.Q4_3_UPDATE_HOURS):
    validate_alignment(prices, actual, builder.forecasts)
    daily_price = get_daily_price(prices, target_date)
    schedule = solve_schedule(target_date, daily_price, builder, update_hours, initial_soc_kwh, soc_policy)
    index = builder.date_index[target_date]
    if actual.dates[index] != target_date:
        raise ValueError(f"{target_date}: actual date index mismatch")
    result = evaluate_actual_day(daily_price, schedule, actual.net_load_kwh[index], update_hours)
    validate_q43(prices, [result], complete=False, update_hours=update_hours)
    return result


def run_annual(prices, actual, builder, soc_policy="daily_closed", update_hours=cfg.Q4_3_UPDATE_HOURS,
               initialization_mode="feb1_control_start", price_information_mode="current_day_persistence"):
    validate_alignment(prices, actual, builder.forecasts)
    results = evaluate_update_policy(update_hours, prices.daily_prices(), actual, builder, soc_policy, initialization_mode,price_information_mode)
    validate_q43(prices, results, update_hours=update_hours)
    return results


def main():
    from .main import main as run
    return run(model="4-3")


if __name__ == "__main__":
    raise SystemExit(main())
