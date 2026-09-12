"""问题4-2：动态价格下复用问题2选定的A7合同与因果储能策略。"""
from ..question2 import pipeline
from . import config as cfg
from .price_loader import get_daily_price, validate_alignment
from .validator import validate_q42


def solve_day(target_date, prices, actual, strategy=cfg.Q4_2_STRATEGY):
    validate_alignment(prices, actual)
    result = pipeline.solve_day(
        target_date, get_daily_price(prices, target_date), actual, strategy
    )
    validate_q42(prices, [result], complete=False)
    return result


def run_annual(prices, actual, strategy=cfg.Q4_2_STRATEGY):
    validate_alignment(prices, actual)
    results = pipeline.run_annual(prices.daily_prices(), actual, strategy)
    validate_q42(prices, results)
    return results


def main():
    from .main import main as run
    return run(model="4-2")


if __name__ == "__main__":
    raise SystemExit(main())
