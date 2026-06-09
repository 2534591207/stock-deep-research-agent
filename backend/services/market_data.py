"""market_data.py — Yahoo Finance (yfinance) adapter + FakeMarketData for offline testing.

为什么用 yfinance：免费、无需 API key、覆盖美股与 ADR（含 BABA，Twelve Data 免费档不含）、
日线 `auto_adjust=True` 即复权收盘价。失败一律 raise，绝不伪造（fail-fast / 诚实降级由上层处理）。
"""
from __future__ import annotations

from datetime import date, timedelta

from models import Bar, Quote


def get_bars(symbol: str, start: date, end: date) -> list[Bar]:
    """从 Yahoo Finance 取复权日线（auto_adjust）。

    Raises:
        RuntimeError: 任何取数/解析失败（绝不返回伪造数据）。
    """
    import yfinance as yf  # 延迟导入，便于 FakeMarketData 离线测试

    try:
        # yfinance 的 end 为 exclusive，+1 天确保包含 end 当天
        df = yf.Ticker(symbol).history(
            start=str(start),
            end=str(end + timedelta(days=1)),
            interval="1d",
            auto_adjust=True,
            actions=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Yahoo Finance get_bars failed for {symbol}: {exc}") from exc

    if df is None or len(df) == 0:
        raise RuntimeError(f"Yahoo Finance returned no bars for {symbol} ({start} to {end})")

    bars: list[Bar] = []
    for idx, row in df.iterrows():
        try:
            bars.append(
                Bar(
                    date=idx.date().isoformat(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    # auto_adjust=True → Close 已为复权价
                    adjusted_close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Yahoo Finance bar parse error for {symbol} row={row!r}: {exc}"
            ) from exc

    bars.sort(key=lambda b: b.date)
    return bars


def get_quote(symbol: str) -> Quote:
    """从 Yahoo Finance 取最新参考价（延迟报价）。partial_market=True、标注"不用于交易"。

    Raises:
        RuntimeError: 任何取数失败。
    """
    import yfinance as yf

    try:
        fast = yf.Ticker(symbol).fast_info
        price = float(fast["last_price"]) if "last_price" in dict(fast) else float(fast.last_price)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Yahoo Finance get_quote failed for {symbol}: {exc}") from exc

    return Quote(
        symbol=symbol,
        price=price,
        quote_time="",
        partial_market=True,
        source="Yahoo Finance",
        freshness="Delayed quote (Yahoo Finance); not for trading.",
    )


class FakeMarketData:
    """Recording/playback fake for offline tests.

    Usage:
        fake = FakeMarketData(
            bars={"AAPL": [Bar(...), ...]},
            quotes={"AAPL": Quote(...)},
        )
        bars = fake.get_bars("AAPL", start, end)
        quote = fake.get_quote("AAPL")

        # 失败 fake：
        fake = FakeMarketData(bars={"AAPL": RuntimeError("network timeout")}, quotes={...})
    """

    def __init__(
        self,
        bars: dict[str, list[Bar] | Exception | type[Exception]] | None = None,
        quotes: dict[str, Quote | Exception | type[Exception]] | None = None,
    ) -> None:
        self._bars: dict[str, list[Bar] | Exception | type[Exception]] = bars or {}
        self._quotes: dict[str, Quote | Exception | type[Exception]] = quotes or {}
        self.call_count: dict[str, int] = {"get_bars": 0, "get_quote": 0}

    def get_bars(self, symbol: str, start: date, end: date) -> list[Bar]:  # noqa: ARG002
        self.call_count["get_bars"] += 1
        entry = self._bars.get(symbol)
        if entry is None:
            raise RuntimeError(f"FakeMarketData: no bars recorded for {symbol!r}")
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, type) and issubclass(entry, Exception):
            raise entry(f"FakeMarketData: simulated failure for {symbol!r}")
        return list(entry)

    def get_quote(self, symbol: str) -> Quote:
        self.call_count["get_quote"] += 1
        entry = self._quotes.get(symbol)
        if entry is None:
            raise RuntimeError(f"FakeMarketData: no quote recorded for {symbol!r}")
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, type) and issubclass(entry, Exception):
            raise entry(f"FakeMarketData: simulated failure for {symbol!r}")
        return entry
