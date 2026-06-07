from __future__ import annotations

import statistics


def calculate_metrics(bars: list[dict]) -> dict:
    closes = [float(bar["close"]) for bar in bars]
    returns = [closes[index] / closes[index - 1] - 1 for index in range(1, len(closes))]
    peak = closes[0]
    max_drawdown = 0.0
    for close in closes:
        peak = max(peak, close)
        max_drawdown = min(max_drawdown, close / peak - 1)

    first_volume = sum((bar.get("volume") or 0) for bar in bars[:5]) / min(5, len(bars))
    last_volume = sum((bar.get("volume") or 0) for bar in bars[-5:]) / min(5, len(bars))

    return {
        "first_close": closes[0],
        "last_close": closes[-1],
        "period_return_percent": round((closes[-1] / closes[0] - 1) * 100, 2),
        "period_high": round(max(float(bar["high"]) for bar in bars), 2),
        "period_low": round(min(float(bar["low"]) for bar in bars), 2),
        "daily_volatility_percent": round(statistics.stdev(returns) * 100, 2) if len(returns) > 1 else 0.0,
        "max_drawdown_percent": round(max_drawdown * 100, 2),
        "up_days": sum(1 for value in returns if value > 0),
        "down_days": sum(1 for value in returns if value < 0),
        "volume_change_percent": round((last_volume / first_volume - 1) * 100, 2) if first_volume else None,
    }


def significant_moves(bars: list[dict], limit: int = 3) -> list[dict]:
    moves = []
    for index in range(1, len(bars)):
        previous = float(bars[index - 1]["close"])
        current = float(bars[index]["close"])
        moves.append(
            {
                "date": bars[index]["date"],
                "change_percent": round((current / previous - 1) * 100, 2),
                "close": current,
            }
        )
    return sorted(moves, key=lambda item: abs(item["change_percent"]), reverse=True)[:limit]


def normalized_series(bars: list[dict]) -> list[dict]:
    base = float(bars[0]["close"])
    return [{"date": bar["date"], "value": round(float(bar["close"]) / base * 100, 2)} for bar in bars]
