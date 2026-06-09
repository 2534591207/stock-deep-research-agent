"""tests/test_risk.py — T1.2 风险打分 / 绝对等级 / 短期市场观点。

AC-B4: 自洽样例逐项精确断言
AC-B5: 绝对等级阈值边界（含边界、最严重优先）
AC-B6: 有效日线 < 10 或 coverage < 0.8 → Undetermined + Insufficient data
"""
import pytest

from services.risk import (
    absolute_level,
    drawdown_score,
    return_threshold,
    risk_score,
    short_term_market_view,
    vol_score,
)


# ---------------------------------------------------------------------------
# AC-B4 — 自洽样例（全项目共用：dv=0.02665, dd=-0.138, ret=-0.104, exp=63）
# ---------------------------------------------------------------------------

class TestSelfConsistentExample:
    """spec §5.B / tasks.md T1.2 / AC-B4 自洽样例逐项精确断言。"""

    DV = 0.02665
    DD = -0.138
    RET = -0.104
    EXP = 63
    # 有效日 / coverage 充分
    EFF = 63
    COV = 1.0

    def test_vol_score(self):
        # min(0.02665/0.05, 1)*100 = 53.3
        assert vol_score(self.DV) == 53.3

    def test_drawdown_score(self):
        # min(0.138/0.30, 1)*100 = 46.0
        assert drawdown_score(self.DD) == 46.0

    def test_risk_score(self):
        # 53.3*0.6 + 46.0*0.4 = 31.98 + 18.4 = 50.38
        rs = risk_score(self.DV, self.DD)
        assert abs(rs - 50.38) <= 0.1, f"risk_score={rs}, expected≈50.38"

    def test_risk_score_exact(self):
        assert risk_score(self.DV, self.DD) == 50.38

    def test_absolute_level(self):
        # dv=0.02665 >= 0.015 → Medium（未达 0.030 High）
        assert absolute_level(self.DV, self.DD, self.EFF, self.COV) == "Medium"

    def test_return_threshold(self):
        # 0.05 * sqrt(63/21) = 0.05 * sqrt(3) = 0.05 * 1.7320508… ≈ 0.0866
        rt = return_threshold(self.EXP)
        assert abs(rt - 0.0866) <= 0.0001, f"return_threshold={rt}, expected≈0.0866"

    def test_return_threshold_exact(self):
        assert return_threshold(self.EXP) == 0.0866

    def test_short_term_market_view_cautious(self):
        # -0.104 < -0.0866 → Cautious
        view = short_term_market_view(
            level="Medium",
            period_return=self.RET,
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Cautious"


# ---------------------------------------------------------------------------
# AC-B5 — 绝对等级阈值边界（含边界、最严重优先）
# ---------------------------------------------------------------------------

# Sufficient data defaults
_EFF_OK = 20
_COV_OK = 1.0


@pytest.mark.parametrize(
    "dv, dd, expected_level",
    [
        # dv=0.030 at High boundary → High
        (0.030, 0.0, "High"),
        # dv=0.015 at Medium boundary, dd=0 (no drawdown) → Medium
        (0.015, 0.0, "Medium"),
        # dv=0.0149 < 0.015, but dd=-0.10 at Medium boundary → Medium (回撤触发)
        (0.0149, -0.10, "Medium"),
        # dv=0.0149, dd=-0.099 below both thresholds → Low
        (0.0149, -0.099, "Low"),
    ],
    ids=["high_vol_boundary", "medium_vol_boundary", "medium_dd_boundary", "low"],
)
def test_absolute_level_boundaries(dv, dd, expected_level):
    result = absolute_level(dv, dd, _EFF_OK, _COV_OK)
    assert result == expected_level, (
        f"absolute_level(dv={dv}, dd={dd}) = {result!r}, expected {expected_level!r}"
    )


def test_absolute_level_high_drawdown_boundary():
    """dd=-0.20 at High boundary → High (even with low volatility)."""
    result = absolute_level(0.0, -0.20, _EFF_OK, _COV_OK)
    assert result == "High"


def test_absolute_level_high_vol_beats_lower_dd():
    """dv>=0.03 takes priority even when drawdown is shallow."""
    result = absolute_level(0.03, -0.01, _EFF_OK, _COV_OK)
    assert result == "High"


# ---------------------------------------------------------------------------
# AC-B6 — 数据不足 → Undetermined + Insufficient data
# ---------------------------------------------------------------------------

class TestInsufficientData:
    """有效日 < 10 或 coverage < 0.8 → Undetermined + Insufficient data。"""

    def test_undetermined_when_eff_below_10(self):
        result = absolute_level(0.02, -0.10, effective_trading_days=9, data_coverage=1.0)
        assert result == "Undetermined"

    def test_undetermined_when_eff_exactly_9(self):
        result = absolute_level(0.04, -0.25, effective_trading_days=9, data_coverage=1.0)
        assert result == "Undetermined"

    def test_undetermined_when_coverage_below_threshold(self):
        result = absolute_level(0.02, -0.10, effective_trading_days=20, data_coverage=0.79)
        assert result == "Undetermined"

    def test_undetermined_when_coverage_exactly_079(self):
        result = absolute_level(0.04, -0.25, effective_trading_days=20, data_coverage=0.799)
        assert result == "Undetermined"

    def test_not_undetermined_when_eff_exactly_10(self):
        """eff=10 is the boundary — at 10 it is sufficient (< 10 triggers Undetermined)."""
        result = absolute_level(0.02, -0.05, effective_trading_days=10, data_coverage=1.0)
        assert result != "Undetermined"

    def test_not_undetermined_when_coverage_exactly_080(self):
        """coverage=0.80 is sufficient (< 0.80 triggers Undetermined)."""
        result = absolute_level(0.02, -0.05, effective_trading_days=20, data_coverage=0.80)
        assert result != "Undetermined"

    def test_view_insufficient_when_eff_below_10(self):
        view = short_term_market_view(
            level="Low",
            period_return=0.10,
            expected_trading_days=21,
            effective_trading_days=9,
            data_coverage=1.0,
        )
        assert view == "Insufficient data"

    def test_view_insufficient_when_coverage_below_threshold(self):
        view = short_term_market_view(
            level="Low",
            period_return=0.10,
            expected_trading_days=21,
            effective_trading_days=20,
            data_coverage=0.79,
        )
        assert view == "Insufficient data"

    def test_view_insufficient_when_level_undetermined(self):
        view = short_term_market_view(
            level="Undetermined",
            period_return=0.10,
            expected_trading_days=21,
            effective_trading_days=20,
            data_coverage=1.0,
        )
        assert view == "Insufficient data"


# ---------------------------------------------------------------------------
# Additional short_term_market_view branches
# ---------------------------------------------------------------------------

class TestShortTermMarketView:
    EFF = 21
    COV = 1.0
    EXP = 21  # threshold = 0.05 * sqrt(1) = 0.05

    def test_high_level_always_cautious(self):
        view = short_term_market_view(
            level="High",
            period_return=0.20,   # even positive return
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Cautious"

    def test_positive_return_above_threshold(self):
        # period_return=0.06 > 0.05 threshold → Positive
        view = short_term_market_view(
            level="Medium",
            period_return=0.06,
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Positive"

    def test_negative_return_below_threshold(self):
        # period_return=-0.06 < -0.05 → Cautious
        view = short_term_market_view(
            level="Medium",
            period_return=-0.06,
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Cautious"

    def test_return_within_threshold_neutral(self):
        # |period_return| <= 0.05 → Neutral
        view = short_term_market_view(
            level="Low",
            period_return=0.03,
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Neutral"

    def test_return_threshold_uses_expected_not_effective(self):
        """return_threshold uses expected_trading_days, NOT effective_trading_days.
        This prevents fewer actual trading days from making threshold smaller/easier to beat.
        """
        # exp=63 → threshold≈0.0866; eff=10 (below MIN) → Insufficient data
        # But with eff=15 (sufficient) and exp=63:
        # threshold = 0.05*sqrt(63/21) ≈ 0.0866
        # period_return=0.07 < 0.0866 → Neutral  (not Positive)
        view = short_term_market_view(
            level="Low",
            period_return=0.07,
            expected_trading_days=63,
            effective_trading_days=15,
            data_coverage=1.0,
        )
        assert view == "Neutral"

    def test_low_level_positive_return_positive(self):
        view = short_term_market_view(
            level="Low",
            period_return=0.10,
            expected_trading_days=self.EXP,
            effective_trading_days=self.EFF,
            data_coverage=self.COV,
        )
        assert view == "Positive"


# ---------------------------------------------------------------------------
# vol_score / drawdown_score capping at 100
# ---------------------------------------------------------------------------

class TestScoreCaps:
    def test_vol_score_capped_at_100(self):
        assert vol_score(0.10) == 100.0   # 0.10/0.05 = 2 → capped at 1 → 100

    def test_drawdown_score_capped_at_100(self):
        assert drawdown_score(-0.60) == 100.0  # 0.60/0.30 = 2 → capped

    def test_vol_score_zero(self):
        assert vol_score(0.0) == 0.0

    def test_drawdown_score_zero_drawdown(self):
        assert drawdown_score(0.0) == 0.0

    def test_drawdown_score_positive_input(self):
        """drawdown_score takes abs(), so positive value same as negative."""
        assert drawdown_score(0.15) == drawdown_score(-0.15)
