"""动态价格输入的形状、日期、数值及时间列验收。"""
from dataclasses import replace
from datetime import date
from unittest import TestCase, main
from unittest.mock import patch
import numpy as np
from src.question2.data_loader import load_actual
from src.question4.price_loader import load_annual_price, get_daily_price, AnnualPriceData, normalize_time, validate_alignment
from src.question4 import config as cfg


class Question4PriceTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.actual = load_actual()
        cls.prices = load_annual_price(cls.actual)

    def test_attachment4_shape_date_range_and_no_nan(self):
        self.assertEqual(self.prices.dates, cfg.ANNUAL_DATES)
        self.assertEqual(self.prices.price_yuan_per_kwh.shape, (365, 144))
        self.assertTrue(np.isfinite(self.prices.price_yuan_per_kwh).all())
        self.assertFalse(self.prices.price_yuan_per_kwh.flags.writeable)

    def test_daily_price_lookup(self):
        for day in cfg.PAPER_DATES:
            values = get_daily_price(self.prices, day)
            np.testing.assert_array_equal(values, self.prices.price_yuan_per_kwh[(day - date(2025, 1, 1)).days])
        with self.assertRaises(KeyError): get_daily_price(self.prices, date(2026, 1, 1))

    def test_attachment2_attachment4_date_alignment(self):
        validate_alignment(self.prices, self.actual)
        with self.assertRaisesRegex(ValueError, "dates differ"):
            validate_alignment(self.prices, replace(self.actual, dates=self.actual.dates[::-1]))

    def test_attachment4_time_alignment(self):
        self.assertEqual(self.prices.slot_labels[-1], "0:00+1")
        self.assertEqual(normalize_time("06:00:00"), "6:00")
        with self.assertRaisesRegex(ValueError, "time columns"):
            replace(self.prices, slot_labels=self.prices.slot_labels[::-1])

    def test_invalid_shape_dates_nan_inf_negative(self):
        for bad in (np.nan, np.inf, -0.01):
            values = self.prices.price_yuan_per_kwh.copy()
            values[20, 100] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                replace(self.prices, price_yuan_per_kwh=values)
        with self.assertRaises(ValueError): replace(self.prices, dates=self.prices.dates[::-1])
        with self.assertRaises(ValueError): replace(self.prices, price_yuan_per_kwh=np.ones((334, 144)))

    def test_no_attachment1_price_dependency(self):
        with patch("src.question2.data_loader.load_price", side_effect=AssertionError("fixed price forbidden")):
            prices = load_annual_price(self.actual)
        np.testing.assert_array_equal(prices.price_yuan_per_kwh, self.prices.price_yuan_per_kwh)


if __name__ == "__main__":
    main()
