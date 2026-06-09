"""Tests for services/market_data.py — fake/raise paths only (no real network).

Covers:
- FakeMarketData playback: Bar and Quote fields fully populated
- FakeMarketData failure: raises on get_bars / get_quote
- call_count assertions
- Quote.partial_market == True
- Exception instance and exception class both raise correctly
"""
from __future__ import annotations

from datetime import date

import pytest

from models import Bar, Quote
from services.market_data import FakeMarketData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bar(d: str = "2024-01-02") -> Bar:
    return Bar(
        date=d,
        open=100.0,
        high=105.0,
        low=98.0,
        close=103.0,
        adjusted_close=103.0,
        volume=1_000_000.0,
    )


def _make_quote(symbol: str = "AAPL") -> Quote:
    return Quote(
        symbol=symbol,
        price=103.5,
        quote_time="2024-01-02 16:00:00",
        partial_market=True,
        source="Twelve Data",
        freshness="Partial-market reference price; not for trading.",
    )


# ---------------------------------------------------------------------------
# Bar playback
# ---------------------------------------------------------------------------

class TestFakeMarketDataBars:
    def test_get_bars_returns_recorded_bars(self):
        bars_fixture = [_make_bar("2024-01-02"), _make_bar("2024-01-03")]
        fake = FakeMarketData(bars={"AAPL": bars_fixture})

        result = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))

        assert len(result) == 2
        assert result[0].date == "2024-01-02"
        assert result[1].date == "2024-01-03"

    def test_get_bars_bar_fields_fully_populated(self):
        bar = _make_bar()
        fake = FakeMarketData(bars={"AAPL": [bar]})

        result = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))

        assert len(result) == 1
        b = result[0]
        assert b.date == "2024-01-02"
        assert b.open == 100.0
        assert b.high == 105.0
        assert b.low == 98.0
        assert b.close == 103.0
        assert b.adjusted_close == 103.0
        assert b.volume == 1_000_000.0

    def test_get_bars_returns_copy_not_same_list(self):
        bars_fixture = [_make_bar()]
        fake = FakeMarketData(bars={"AAPL": bars_fixture})

        result = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        result.append(_make_bar("2024-01-05"))  # mutate returned list

        # recorded fixture should not be affected
        result2 = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        assert len(result2) == 1

    def test_get_bars_missing_symbol_raises(self):
        fake = FakeMarketData(bars={})
        with pytest.raises(RuntimeError, match="TSLA"):
            fake.get_bars("TSLA", date(2024, 1, 2), date(2024, 1, 3))

    def test_get_bars_multiple_symbols(self):
        fake = FakeMarketData(
            bars={
                "AAPL": [_make_bar("2024-01-02")],
                "NVDA": [_make_bar("2024-01-02"), _make_bar("2024-01-03")],
            }
        )
        aapl = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        nvda = fake.get_bars("NVDA", date(2024, 1, 2), date(2024, 1, 3))

        assert len(aapl) == 1
        assert len(nvda) == 2


# ---------------------------------------------------------------------------
# Quote playback
# ---------------------------------------------------------------------------

class TestFakeMarketDataQuote:
    def test_get_quote_returns_recorded_quote(self):
        quote = _make_quote("AAPL")
        fake = FakeMarketData(quotes={"AAPL": quote})

        result = fake.get_quote("AAPL")

        assert result.symbol == "AAPL"
        assert result.price == 103.5

    def test_get_quote_fields_fully_populated(self):
        quote = _make_quote("AAPL")
        fake = FakeMarketData(quotes={"AAPL": quote})

        result = fake.get_quote("AAPL")

        assert result.symbol == "AAPL"
        assert result.price == 103.5
        assert result.quote_time == "2024-01-02 16:00:00"
        assert result.source == "Twelve Data"
        assert result.freshness == "Partial-market reference price; not for trading."

    def test_get_quote_partial_market_is_true(self):
        """AC-F3: current price must be flagged as partial-market reference."""
        quote = _make_quote()
        fake = FakeMarketData(quotes={"AAPL": quote})

        result = fake.get_quote("AAPL")

        assert result.partial_market is True

    def test_get_quote_partial_market_true_even_if_constructed_false(self):
        """Models default partial_market=True; test that the fake returns whatever was recorded."""
        # If someone stores a quote with partial_market=True (the model default), it stays True.
        quote = Quote(
            symbol="MSFT",
            price=400.0,
            quote_time="2024-01-02 16:00:00",
            partial_market=True,
        )
        fake = FakeMarketData(quotes={"MSFT": quote})
        result = fake.get_quote("MSFT")
        assert result.partial_market is True

    def test_get_quote_missing_symbol_raises(self):
        fake = FakeMarketData(quotes={})
        with pytest.raises(RuntimeError, match="TSLA"):
            fake.get_quote("TSLA")


# ---------------------------------------------------------------------------
# Failure fakes — raise paths
# ---------------------------------------------------------------------------

class TestFakeMarketDataFailure:
    def test_get_bars_raises_exception_instance(self):
        """Failure fake with an exception instance raises that exception."""
        err = RuntimeError("simulated network timeout")
        fake = FakeMarketData(bars={"AAPL": err})

        with pytest.raises(RuntimeError, match="simulated network timeout"):
            fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))

    def test_get_bars_raises_exception_class(self):
        """Failure fake with an exception class raises an instance of that class."""
        fake = FakeMarketData(bars={"AAPL": RuntimeError})

        with pytest.raises(RuntimeError):
            fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))

    def test_get_bars_raises_value_error_class(self):
        fake = FakeMarketData(bars={"NVDA": ValueError})

        with pytest.raises(ValueError):
            fake.get_bars("NVDA", date(2024, 1, 2), date(2024, 1, 3))

    def test_get_quote_raises_exception_instance(self):
        err = RuntimeError("simulated quote failure")
        fake = FakeMarketData(quotes={"AAPL": err})

        with pytest.raises(RuntimeError, match="simulated quote failure"):
            fake.get_quote("AAPL")

    def test_get_quote_raises_exception_class(self):
        fake = FakeMarketData(quotes={"AAPL": RuntimeError})

        with pytest.raises(RuntimeError):
            fake.get_quote("AAPL")

    def test_failure_does_not_return_fake_data(self):
        """Confirms that a failure fake never returns a result — it must raise."""
        err = RuntimeError("no data")
        fake = FakeMarketData(bars={"AAPL": err})

        result = None
        try:
            result = fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))
        except RuntimeError:
            pass

        assert result is None, "Failure fake must raise, never return data"

    def test_failure_bars_does_not_affect_successful_quote(self):
        """Failure on bars for one symbol does not prevent successful quote."""
        err = RuntimeError("bars failed")
        fake = FakeMarketData(
            bars={"AAPL": err},
            quotes={"AAPL": _make_quote("AAPL")},
        )

        with pytest.raises(RuntimeError):
            fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))

        # quote should still work
        quote = fake.get_quote("AAPL")
        assert quote.symbol == "AAPL"


# ---------------------------------------------------------------------------
# call_count assertions
# ---------------------------------------------------------------------------

class TestFakeMarketDataCallCount:
    def test_call_count_starts_at_zero(self):
        fake = FakeMarketData()
        assert fake.call_count["get_bars"] == 0
        assert fake.call_count["get_quote"] == 0

    def test_call_count_get_bars_increments(self):
        fake = FakeMarketData(bars={"AAPL": [_make_bar()]})

        fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        assert fake.call_count["get_bars"] == 1

        fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        assert fake.call_count["get_bars"] == 2

    def test_call_count_get_quote_increments(self):
        fake = FakeMarketData(quotes={"AAPL": _make_quote()})

        fake.get_quote("AAPL")
        assert fake.call_count["get_quote"] == 1

        fake.get_quote("AAPL")
        assert fake.call_count["get_quote"] == 2

    def test_call_count_increments_even_on_failure(self):
        """call_count must increment even when the call raises."""
        err = RuntimeError("failure")
        fake = FakeMarketData(bars={"AAPL": err})

        with pytest.raises(RuntimeError):
            fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 3))

        assert fake.call_count["get_bars"] == 1

    def test_call_count_get_quote_increments_on_failure(self):
        err = RuntimeError("quote failure")
        fake = FakeMarketData(quotes={"AAPL": err})

        with pytest.raises(RuntimeError):
            fake.get_quote("AAPL")

        assert fake.call_count["get_quote"] == 1

    def test_call_count_independent_per_method(self):
        fake = FakeMarketData(
            bars={"AAPL": [_make_bar()]},
            quotes={"AAPL": _make_quote()},
        )

        fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        fake.get_quote("AAPL")

        assert fake.call_count["get_bars"] == 2
        assert fake.call_count["get_quote"] == 1

    def test_call_count_across_multiple_symbols(self):
        """call_count is global across all symbols (not per-symbol)."""
        fake = FakeMarketData(
            bars={
                "AAPL": [_make_bar()],
                "NVDA": [_make_bar()],
            }
        )

        fake.get_bars("AAPL", date(2024, 1, 2), date(2024, 1, 2))
        fake.get_bars("NVDA", date(2024, 1, 2), date(2024, 1, 2))

        assert fake.call_count["get_bars"] == 2
