"""问题4-3：动态价格下复用问题3配对残差合同与因果储能策略。"""
from ..question3.rolling_controller import solve_day as solve_frozen, solve_day_causal
from ..question3.evaluator import evaluate_actual_day
from ..question3.analysis import evaluate_update_policy
from . import config as cfg
from .price_loader import get_daily_price, validate_alignment
from .validator import validate_q43


def solve_day(target_date, prices, actual, builder,
              storage_execution=cfg.Q4_STORAGE_EXECUTION):
    validate_alignment(prices, actual, builder.forecasts)
    if storage_execution not in cfg.Q4_STORAGE_EXECUTIONS:
        raise ValueError(f"Question4-3: unknown storage execution {storage_execution!r}")
    daily_price = get_daily_price(prices, target_date)
    index = builder.date_index[target_date]
    if actual.dates[index] != target_date:
        raise ValueError(f"{target_date}: actual date index mismatch")
    actual_net = actual.net_load_kwh[index]
    schedule = (solve_frozen(target_date, daily_price, builder, cfg.Q4_3_UPDATE_HOURS)
                if storage_execution == "frozen" else
                solve_day_causal(target_date, daily_price, builder, actual_net,
                                 cfg.Q4_3_UPDATE_HOURS))
    result = evaluate_actual_day(daily_price, schedule, actual_net, cfg.Q4_3_UPDATE_HOURS)
    validate_q43(prices, [result], complete=False)
    return result


def run_annual(prices, actual, builder, storage_execution=cfg.Q4_STORAGE_EXECUTION):
    validate_alignment(prices, actual, builder.forecasts)
    results = evaluate_update_policy(
        cfg.Q4_3_UPDATE_HOURS, prices.daily_prices(), actual, builder, storage_execution
    )
    validate_q43(prices, results)
    return results


def main():
    from .main import main as run
    return run(model="4-3")


if __name__ == "__main__":
    raise SystemExit(main())
