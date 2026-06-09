"""Deterministic metrics computation — T1.1 (AC-B1, AC-B2, AC-B3).

All arithmetic is vectorised with numpy/pandas.  No Python for-loops over
arrays.  Key outputs are float64; callers may round for display.

Public API
----------
compute_metrics(bars, expected_trading_days) -> Metrics
flag_significant_move(signed_change)         -> bool
normalized_series(adj_closes)                -> list[float]
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from config import (
    MIN_NEGATIVE_DAYS_FOR_VOL,
    SIGNIFICANT_MOVE_MIN_PCT,
    TRADING_DAYS_PER_YEAR,
)
from models import Bar, Metrics, SignificantMove


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def flag_significant_move(signed_change: float) -> bool:
    """Return True iff |signed_change| >= SIGNIFICANT_MOVE_MIN_PCT (boundary inclusive)."""
    return abs(signed_change) >= SIGNIFICANT_MOVE_MIN_PCT


def normalized_series(adj_closes: list[float]) -> list[float]:
    """Normalise a price series so the first element equals 100.

    Parameters
    ----------
    adj_closes:
        Non-empty list of adjusted close prices.

    Returns
    -------
    List of the same length with the first value set to 100.0 and all
    subsequent values scaled proportionally.
    """
    if not adj_closes:
        return []
    prices = np.array(adj_closes, dtype=np.float64)
    return (prices / prices[0] * 100.0).tolist()


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def compute_metrics(bars: list[Bar], expected_trading_days: int) -> Metrics:
    """Compute all deterministic metrics for a bar sequence.

    Parameters
    ----------
    bars:
        Chronological list of daily bars (at least 2 required for meaningful
        returns; 1-bar input is handled gracefully).
    expected_trading_days:
        Number of trading days the caller expected to receive (used for
        Data Coverage).

    Returns
    -------
    A fully-populated :class:`~models.Metrics` instance.
    """
    adj = np.array([b.adjusted_close for b in bars], dtype=np.float64)
    n = len(adj)

    # ---- daily returns (n-1 values) ----
    if n >= 2:
        returns = adj[1:] / adj[:-1] - 1.0
    else:
        returns = np.array([], dtype=np.float64)

    # ---- period return ----
    period_return: float = float(adj[-1] / adj[0] - 1.0) if n >= 1 else 0.0

    # ---- daily volatility (sample stdev, ddof=1) ----
    if len(returns) >= 2:
        daily_vol: float = float(np.std(returns, ddof=1))
    else:
        daily_vol = 0.0

    annualized_vol: float = daily_vol * math.sqrt(TRADING_DAYS_PER_YEAR)

    # ---- negative-day volatility ----
    neg_returns = returns[returns < 0]
    neg_vol: Optional[float]
    neg_vol_reason: Optional[str]
    if len(neg_returns) >= MIN_NEGATIVE_DAYS_FOR_VOL:
        neg_vol = float(np.std(neg_returns, ddof=1)) * math.sqrt(TRADING_DAYS_PER_YEAR)
        neg_vol_reason = None
    else:
        neg_vol = None
        neg_vol_reason = "insufficient_negative_days"

    # ---- max drawdown (peak → subsequent trough, using np.maximum.accumulate) ----
    # running_max[i] = max(adj[0..i])
    running_max = np.maximum.accumulate(adj)
    drawdowns = (adj - running_max) / running_max   # all <= 0
    max_drawdown: float = float(np.min(drawdowns))  # most negative

    # ---- max single-day move (preserves sign) ----
    if len(returns) > 0:
        abs_returns = np.abs(returns)
        max_abs_idx = int(np.argmax(abs_returns))
        max_single_day: float = float(returns[max_abs_idx])
    else:
        max_single_day = 0.0

    significant = flag_significant_move(max_single_day)

    # ---- up / down day counts ----
    up_days = int(np.sum(returns > 0))
    down_days = int(np.sum(returns < 0))

    # ---- data coverage ----
    effective = n
    coverage: float = effective / expected_trading_days if expected_trading_days > 0 else 0.0

    # ---- normalised series ----
    norm_series = normalized_series(adj.tolist())
    norm_base_date: str = bars[0].date if bars else ""

    # ---- significant single-day moves (every day with |return| >= threshold) ----
    sig_moves: list[SignificantMove] = []
    if len(returns) > 0:
        sig_indices = np.nonzero(np.abs(returns) >= SIGNIFICANT_MOVE_MIN_PCT)[0]
        for idx in sig_indices:
            r = float(returns[int(idx)])
            sig_moves.append(
                SignificantMove(
                    date=bars[int(idx) + 1].date,   # returns[idx] 对应 bars[idx+1] 当日
                    pct_move=r,
                    direction="up" if r > 0 else "down",
                )
            )

    return Metrics(
        period_return=period_return,
        daily_volatility=daily_vol,
        annualized_volatility=annualized_vol,
        negative_day_volatility=neg_vol,
        negative_day_volatility_reason=neg_vol_reason,
        max_drawdown=max_drawdown,
        max_single_day_move=max_single_day,
        max_single_day_significant=significant,
        up_days=up_days,
        down_days=down_days,
        data_coverage=coverage,
        effective_trading_days=effective,
        expected_trading_days=expected_trading_days,
        normalized_series=norm_series,
        normalized_base_date=norm_base_date,
        calculation_basis="Price Return",
        significant_moves=sig_moves,
    )
