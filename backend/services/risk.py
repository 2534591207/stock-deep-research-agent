"""services/risk.py — 风险打分 + 绝对等级 + 短期市场观点。

公式严格按 spec §5.B / tasks.md T1.2，阈值全从 config 读取，不散落硬编码。
全部纯函数，无副作用，可单独测试。
"""
from __future__ import annotations

from math import sqrt

from config import (
    DRAWDOWN_SCORE_CAP,
    MIN_DATA_COVERAGE,
    MIN_EFFECTIVE_TRADING_DAYS,
    RETURN_THRESHOLD_BASE,
    RETURN_THRESHOLD_REF_DAYS,
    RISK_THRESHOLDS,
    RISK_WEIGHT_DD,
    RISK_WEIGHT_VOL,
    VOL_SCORE_CAP,
)


def vol_score(daily_volatility: float) -> float:
    """vol_score = round(min(dv / VOL_SCORE_CAP, 1) * 100, 1)"""
    return round(min(daily_volatility / VOL_SCORE_CAP, 1.0) * 100, 1)


def drawdown_score(max_drawdown: float) -> float:
    """drawdown_score = round(min(|dd| / DRAWDOWN_SCORE_CAP, 1) * 100, 1)"""
    return round(min(abs(max_drawdown) / DRAWDOWN_SCORE_CAP, 1.0) * 100, 1)


def risk_score(daily_volatility: float, max_drawdown: float) -> float:
    """risk_score = round(vol_score * RISK_WEIGHT_VOL + drawdown_score * RISK_WEIGHT_DD, 2)"""
    vs = vol_score(daily_volatility)
    ds = drawdown_score(max_drawdown)
    return round(vs * RISK_WEIGHT_VOL + ds * RISK_WEIGHT_DD, 2)


def absolute_level(
    daily_volatility: float,
    max_drawdown: float,
    effective_trading_days: int,
    data_coverage: float,
) -> str:
    """绝对等级（最严重优先，含边界）。

    顺序：
      1. eff < MIN_EFFECTIVE_TRADING_DAYS 或 cov < MIN_DATA_COVERAGE → "Undetermined"
      2. dv >= high_volatility(0.03) 或 dd <= -high_drawdown(-0.20) → "High"
      3. dv >= medium_volatility(0.015) 或 dd <= -medium_drawdown(-0.10) → "Medium"
      4. 否则 → "Low"
    """
    if effective_trading_days < MIN_EFFECTIVE_TRADING_DAYS or data_coverage < MIN_DATA_COVERAGE:
        return "Undetermined"

    high_vol = RISK_THRESHOLDS["high_volatility"]    # 0.030
    high_dd = RISK_THRESHOLDS["high_drawdown"]        # 0.20
    med_vol = RISK_THRESHOLDS["medium_volatility"]   # 0.015
    med_dd = RISK_THRESHOLDS["medium_drawdown"]       # 0.10

    if daily_volatility >= high_vol or max_drawdown <= -high_dd:
        return "High"

    if daily_volatility >= med_vol or max_drawdown <= -med_dd:
        return "Medium"

    return "Low"


def return_threshold(expected_trading_days: int) -> float:
    """return_threshold = round(RETURN_THRESHOLD_BASE * sqrt(expected / RETURN_THRESHOLD_REF_DAYS), 4)"""
    return round(
        RETURN_THRESHOLD_BASE * sqrt(expected_trading_days / RETURN_THRESHOLD_REF_DAYS),
        4,
    )


def short_term_market_view(
    level: str,
    period_return: float,
    expected_trading_days: int,
    effective_trading_days: int,
    data_coverage: float,
) -> str:
    """Short-term Market View。

    顺序（命中即停）：
      1. level == "Undetermined" 或 eff < 10 或 cov < 0.8 → "Insufficient data"
      2. level == "High" → "Cautious"
      3. period_return < -threshold → "Cautious"
      4. period_return > +threshold → "Positive"
      5. 否则 → "Neutral"
    """
    if (
        level == "Undetermined"
        or effective_trading_days < MIN_EFFECTIVE_TRADING_DAYS
        or data_coverage < MIN_DATA_COVERAGE
    ):
        return "Insufficient data"

    if level == "High":
        return "Cautious"

    threshold = return_threshold(expected_trading_days)

    if period_return < -threshold:
        return "Cautious"

    if period_return > threshold:
        return "Positive"

    return "Neutral"
