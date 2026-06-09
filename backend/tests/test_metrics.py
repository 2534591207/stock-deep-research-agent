"""Tests for services/metrics.py — T1.1 (AC-B1, AC-B2, AC-B3).

固定日线手算对拍 + 边界测试。
"""
from __future__ import annotations

import math
import pytest
from models import Bar, Metrics
from services.metrics import compute_metrics, flag_significant_move, normalized_series


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bar(date: str, adj_close: float) -> Bar:
    return Bar(
        date=date,
        open=adj_close,
        high=adj_close,
        low=adj_close,
        close=adj_close,
        adjusted_close=adj_close,
        volume=1_000_000,
    )


# ---------------------------------------------------------------------------
# Fixture: 5-bar sequence with known hand-calculated values
#
# adj_closes = [100.0, 102.0, 101.0, 105.0, 103.0]
# daily_returns = [0.02, -0.00980392, 0.03960396, -0.01904762]
#   r0 = 102/100 - 1 =  0.02
#   r1 = 101/102 - 1 = -0.009803921568...
#   r2 = 105/101 - 1 =  0.039603960396...
#   r3 = 103/105 - 1 = -0.019047619047...
#
# mean = (0.02 - 0.009803921568 + 0.039603960396 - 0.019047619047) / 4
#      = 0.030752419781 / 4 = 0.007688104945
#
# sample variance (ddof=1):
#   deviations:
#     d0 = 0.02       - 0.007688104945 =  0.012311895055
#     d1 = -0.009803921568 - 0.007688104945 = -0.017492026513
#     d2 = 0.039603960396 - 0.007688104945 =  0.031915855451
#     d3 = -0.019047619047 - 0.007688104945 = -0.026735723992
#   sum_sq = 0.012311895055^2 + 0.017492026513^2 + 0.031915855451^2 + 0.026735723992^2
#          = 0.000151582815 + 0.000305772995 + 0.001018621657 + 0.000714798597
#          = 0.002190776064
#   variance = 0.002190776064 / 3 = 0.000730258688
#   daily_vol = sqrt(0.000730258688) = 0.027023299...
#
# annualized_vol = 0.027023299 * sqrt(252) = 0.027023299 * 15.874507866... = 0.428869...
#
# period_return = 103/100 - 1 = 0.03
#
# max_drawdown:
#   running_max = [100, 102, 102, 105, 105]
#   drawdowns   = [0, 0, (101-102)/102, 0, (103-105)/105]
#               =  [0, 0, -0.009803921568, 0, -0.019047619047]
#   max_drawdown = min = -0.019047619047
#
# max_single_day_move: abs values = [0.02, 0.00980392, 0.03960396, 0.01904762]
#   max abs is r2 = 0.039603960396  (positive, significant >=2%)
#
# up_days = 2, down_days = 2
# data_coverage = 5 / 7 (inject expected=7)
# ---------------------------------------------------------------------------

ADJ_CLOSES_5 = [100.0, 102.0, 101.0, 105.0, 103.0]
BARS_5 = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate(ADJ_CLOSES_5)]
EXPECTED_TRADING_DAYS_5 = 7

# Hand-calculated reference values (rounded to match numpy float64)
import numpy as np
_returns = np.diff(ADJ_CLOSES_5) / np.array(ADJ_CLOSES_5[:-1])  # shape (4,)
_DAILY_VOL_REF = float(np.std(_returns, ddof=1))
_ANN_VOL_REF = _DAILY_VOL_REF * math.sqrt(252)
_PERIOD_RETURN_REF = ADJ_CLOSES_5[-1] / ADJ_CLOSES_5[0] - 1
# max_drawdown via accumulate
_cum_max = np.maximum.accumulate(ADJ_CLOSES_5)
_dd_series = (np.array(ADJ_CLOSES_5) - _cum_max) / _cum_max
_MAX_DRAWDOWN_REF = float(np.min(_dd_series))
_MAX_SINGLE_DAY_REF = float(_returns[np.argmax(np.abs(_returns))])  # preserves sign
_UP_DAYS_REF = int(np.sum(_returns > 0))
_DOWN_DAYS_REF = int(np.sum(_returns < 0))


class TestComputeMetricsAcB1:
    """AC-B1: 固定日线夹具逐项手算对拍."""

    def setup_method(self):
        self.m = compute_metrics(BARS_5, EXPECTED_TRADING_DAYS_5)

    def test_returns_metrics_instance(self):
        assert isinstance(self.m, Metrics)

    def test_period_return(self):
        assert round(self.m.period_return, 8) == round(_PERIOD_RETURN_REF, 8)

    def test_daily_volatility(self):
        assert round(self.m.daily_volatility, 8) == round(_DAILY_VOL_REF, 8)

    def test_annualized_volatility(self):
        assert round(self.m.annualized_volatility, 8) == round(_ANN_VOL_REF, 8)

    def test_max_drawdown_signed_lte_zero(self):
        assert self.m.max_drawdown <= 0

    def test_max_drawdown_value(self):
        assert round(self.m.max_drawdown, 8) == round(_MAX_DRAWDOWN_REF, 8)

    def test_max_single_day_move(self):
        assert round(self.m.max_single_day_move, 8) == round(_MAX_SINGLE_DAY_REF, 8)

    def test_max_single_day_significant_true(self):
        # r2 = 0.0396... >= 2%, so significant
        assert self.m.max_single_day_significant is True

    def test_up_days(self):
        assert self.m.up_days == _UP_DAYS_REF

    def test_down_days(self):
        assert self.m.down_days == _DOWN_DAYS_REF

    def test_data_coverage(self):
        expected = 5 / EXPECTED_TRADING_DAYS_5
        assert round(self.m.data_coverage, 8) == round(expected, 8)

    def test_effective_trading_days(self):
        assert self.m.effective_trading_days == 5

    def test_expected_trading_days(self):
        assert self.m.expected_trading_days == EXPECTED_TRADING_DAYS_5

    def test_calculation_basis(self):
        assert self.m.calculation_basis == "Price Return"

    def test_normalized_base_date(self):
        assert self.m.normalized_base_date == BARS_5[0].date

    def test_normalized_series_first_element(self):
        assert self.m.normalized_series[0] == pytest.approx(100.0)

    def test_normalized_series_length(self):
        assert len(self.m.normalized_series) == len(BARS_5)


# ---------------------------------------------------------------------------
# AC-B2: 负收益日 < 2 → negative_day_volatility = None + reason
# ---------------------------------------------------------------------------

class TestNegativeDayVolatilityAcB2:
    """AC-B2: 负收益日不足 2 天时必须返回 None + reason，不是字符串 'N/A'."""

    def test_zero_negative_days_gives_none(self):
        """全部上涨日：负收益日 = 0 < 2."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 101.0, 102.0, 103.0])]
        m = compute_metrics(bars, 5)
        assert m.negative_day_volatility is None
        assert m.negative_day_volatility_reason is not None
        assert m.negative_day_volatility_reason != "N/A"
        assert "insufficient" in m.negative_day_volatility_reason.lower()

    def test_one_negative_day_gives_none(self):
        """1 个负收益日 < 2."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 101.0, 100.5, 101.0])]
        m = compute_metrics(bars, 5)
        # returns: +0.01, -0.00497..., +0.00497...
        # one negative day only
        assert m.negative_day_volatility is None
        assert m.negative_day_volatility_reason == "insufficient_negative_days"

    def test_does_not_affect_other_metrics(self):
        """负收益日不足不影响其他指标."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 101.0, 102.0, 103.0])]
        m = compute_metrics(bars, 5)
        assert m.period_return == pytest.approx(0.03, abs=1e-8)
        assert m.daily_volatility > 0

    def test_two_or_more_negative_days_gives_value(self):
        """负收益日 >= 2 → 应返回浮点值（非 None）."""
        # returns: +0.02, -0.00980..., +0.03960..., -0.01904...  (2 negative days)
        m = compute_metrics(BARS_5, EXPECTED_TRADING_DAYS_5)
        assert m.negative_day_volatility is not None
        assert isinstance(m.negative_day_volatility, float)
        assert m.negative_day_volatility_reason is None


# ---------------------------------------------------------------------------
# AC-B3: max_single_day_significant boundary
# ---------------------------------------------------------------------------

class TestMaxSingleDaySignificantAcB3:
    """AC-B3: |幅度| < 2% → significant=False；|幅度| >= 2% → True（含边界）."""

    def test_all_under_2pct_not_significant(self):
        """所有日收益幅度 < 2%."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 101.0, 100.5, 100.8])]
        m = compute_metrics(bars, 5)
        # returns: +0.01, -0.00497..., +0.00299...  — all < 2%
        assert m.max_single_day_significant is False

    def test_exactly_2pct_is_significant(self):
        """边界：|幅度| 恰好 = 2% → significant=True（含边界）."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 102.0, 101.0])]
        m = compute_metrics(bars, 5)
        # r0 = 0.02 exactly
        assert m.max_single_day_significant is True

    def test_over_2pct_is_significant(self):
        """|幅度| > 2% → significant=True."""
        m = compute_metrics(BARS_5, EXPECTED_TRADING_DAYS_5)
        assert m.max_single_day_significant is True

    def test_negative_over_2pct_is_significant(self):
        """负向大跌 |幅度| > 2% → significant=True，且 max_single_day_move 保留符号."""
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([100.0, 97.0, 98.0])]
        m = compute_metrics(bars, 5)
        # r0 = -0.03 → abs=0.03 >= 0.02 → significant=True, move=-0.03
        assert m.max_single_day_significant is True
        assert m.max_single_day_move < 0


# ---------------------------------------------------------------------------
# Max drawdown: 全局最低在全局最高之前 → 朴素 (max-min)/max 会算错
# ---------------------------------------------------------------------------

class TestMaxDrawdownPeakBeforeTrough:
    """构造「全局最低在全局最高之前」夹具，验证 max_drawdown 的"谷必在峰后"约束."""

    def test_global_min_before_global_max(self):
        """
        adj_closes = [100.0, 80.0, 90.0, 95.0, 92.0]
        全局最低 = 80.0 (index 1), 全局最高 = 100.0 (index 0).
        朴素 (max-min)/max = (100-80)/100 = 0.20 → 会得到 -0.20
        但 80 在 100 之前, 所以正确的 max_drawdown 应考虑 80 之后的峰:
          After index 0 (100.0): sequence is [80, 90, 95, 92]
            peak=100 → trough after peak = min(80,90,95,92) = 80 → dd=(80-100)/100=-0.20
          After index 2 (90.0 from running max): peak=90 at idx 2, trough after = min(95,92)=92... wait
        Let me recompute:
          running_max = [100, 100, 100, 100, 100]  (100 stays as the max throughout)
          dd_series = (adj - running_max) / running_max
                    = [0, -0.20, -0.10, -0.05, -0.08]
          max_drawdown = -0.20

        Now a case where global min IS before global max and naive is wrong:
          adj = [90, 70, 95, 92]
          global_min=70 (idx 1), global_max=95 (idx 2)
          naive (max-min)/max = (95-70)/95 = 0.2631... → would give -0.2631
          correct (peak before trough):
            running_max = [90, 90, 95, 95]
            dd = [0, (70-90)/90, 0, (92-95)/95] = [0, -0.2222, 0, -0.0315]
            max_drawdown = -0.2222  (not -0.2631)
        """
        bars = [make_bar(f"2024-01-0{i+1}", c) for i, c in enumerate([90.0, 70.0, 95.0, 92.0])]
        m = compute_metrics(bars, 5)

        naive_drawdown = -(95.0 - 70.0) / 95.0  # = -0.2631...
        correct_drawdown = (70.0 - 90.0) / 90.0  # = -0.2222...

        # Must NOT equal the naive (wrong) value
        assert round(m.max_drawdown, 4) != round(naive_drawdown, 4)
        # Must equal the correct "peak before trough" value
        assert round(m.max_drawdown, 6) == round(correct_drawdown, 6)
        assert m.max_drawdown <= 0


# ---------------------------------------------------------------------------
# normalized_series
# ---------------------------------------------------------------------------

class TestNormalizedSeries:
    """normalized_series 独立函数测试."""

    def test_first_element_is_100(self):
        series = normalized_series([50.0, 55.0, 52.0])
        assert series[0] == pytest.approx(100.0)

    def test_proportional_values(self):
        series = normalized_series([50.0, 100.0])
        assert series[1] == pytest.approx(200.0)

    def test_length_preserved(self):
        prices = [100.0, 102.0, 98.0, 105.0]
        series = normalized_series(prices)
        assert len(series) == len(prices)

    def test_single_element(self):
        series = normalized_series([42.0])
        assert series == pytest.approx([100.0])


# ---------------------------------------------------------------------------
# flag_significant_move
# ---------------------------------------------------------------------------

class TestFlagSignificantMove:
    def test_below_threshold(self):
        assert flag_significant_move(0.01) is False

    def test_exactly_at_threshold_positive(self):
        assert flag_significant_move(0.02) is True

    def test_exactly_at_threshold_negative(self):
        assert flag_significant_move(-0.02) is True

    def test_above_threshold(self):
        assert flag_significant_move(0.05) is True

    def test_negative_above_threshold(self):
        assert flag_significant_move(-0.05) is True

    def test_zero(self):
        assert flag_significant_move(0.0) is False
