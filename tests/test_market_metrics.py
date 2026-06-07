import unittest

from src.market_metrics import calculate_metrics, significant_moves


class MarketMetricsTests(unittest.TestCase):
    def test_calculates_return_and_drawdown(self):
        bars = [
            {"date": "2026-01-01", "high": 100, "low": 99, "close": 100, "volume": 10},
            {"date": "2026-01-02", "high": 121, "low": 100, "close": 120, "volume": 20},
            {"date": "2026-01-03", "high": 120, "low": 89, "close": 90, "volume": 30},
        ]
        metrics = calculate_metrics(bars)
        self.assertEqual(metrics["period_return_percent"], -10.0)
        self.assertEqual(metrics["max_drawdown_percent"], -25.0)
        self.assertEqual(significant_moves(bars)[0]["date"], "2026-01-03")


if __name__ == "__main__":
    unittest.main()
