"""问题4-2：目标日价格适配，完全复用问题2场景、LP及事后结算。"""
from ..question2 import pipeline
from .price_loader import get_daily_price, validate_alignment
from .validator import validate_q42


def solve_day(target_date, prices, actual, initial_soc_kwh=None, soc_policy="daily_closed"):
    validate_alignment(prices, actual)
    result = pipeline.solve_day(target_date, get_daily_price(prices, target_date), actual, initial_soc_kwh, soc_policy)
    validate_q42(prices, [result], complete=False)
    return result


def run_annual(prices, actual, soc_policy="daily_closed", initialization_mode="feb1_control_start",
               price_information_mode="current_day_persistence"):
    validate_alignment(prices, actual)
    results = pipeline.run_annual(prices.daily_prices(), actual, soc_policy, initialization_mode,
                                  price_information_mode=price_information_mode)
    validate_q42(prices, results)
    return results


def main():
    from .main import main as run
    return run(model="4-2")


if __name__ == "__main__":
    raise SystemExit(main())
