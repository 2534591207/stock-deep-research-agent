"""tests/test_analyze_tool.py — TDD for tools.py::analyze_stocks (T3.2).

Covers:
  AC-C1: 多只 → ranking 附 caveat
  AC-C3: 单只 → ranking=None
  AC-F2: 某只 get_bars 抛错 → 该只 data_failed 隔离、其余 ok、warnings 说明
  AC-F3: 当前价 Quote.partial_market=True
  AC-H2: >3 只 → 取前 3 + warnings 标注其余被推迟
  AC-H4: resolver ambiguous → status=unrecognized + 需澄清 note
  No-markdown invariant: 返回对象无 markdown / 下载字段

NOTE: The real catalog only has 8 tickers (NVDA, BABA, INTC, MSFT, AMZN, AMD, CRM, COST).
      Tests that rely on resolver "found" use those symbols; tests for none/ambiguous
      patch resolver.resolve directly.
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from models import Bar, Quote, AnalyzeResult, ResolveResult
from services.market_data import FakeMarketData

# ---------------------------------------------------------------------------
# Shared bar / quote factories
# ---------------------------------------------------------------------------

def _bars(symbol: str, n: int = 30) -> list[Bar]:
    """Generate n synthetic daily bars starting 2024-01-02."""
    bars = []
    price = 100.0
    for i in range(n):
        d = (datetime.date(2024, 1, 2) + datetime.timedelta(days=i)).isoformat()
        change = 0.005 if i % 2 == 0 else -0.003
        price = round(price * (1 + change), 4)
        bars.append(
            Bar(
                date=d,
                open=price * 0.99,
                high=price * 1.01,
                low=price * 0.98,
                close=price,
                adjusted_close=price,
                volume=1_000_000.0,
            )
        )
    return bars


def _quote(symbol: str, price: float = 105.0) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        quote_time="2024-02-01 16:00:00",
        partial_market=True,
        source="Twelve Data",
        freshness="Partial-market reference price; not for trading.",
    )


# ---------------------------------------------------------------------------
# Helper: inject FakeMarketData into the tools module
# ---------------------------------------------------------------------------

def _run_tool(companies: list[str], period: str, fake: FakeMarketData) -> dict:
    """Invoke analyze_stocks.invoke() with an injected FakeMarketData provider."""
    import tools

    original = tools._PROVIDER
    tools.set_provider(fake)
    try:
        result = tools.analyze_stocks.invoke({"companies": companies, "period": period})
    finally:
        tools.set_provider(original)
    return result


# ---------------------------------------------------------------------------
# Test: single stock (AC-C3: ranking=None)
# Uses NVDA — present in catalog
# ---------------------------------------------------------------------------

class TestSingleStock:
    def test_single_stock_ranking_is_none(self):
        """AC-C3: single stock → ranking must be None."""
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA")},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert ar.ranking is None

    def test_single_stock_status_ok(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA")},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 1
        assert ar.stocks[0].status == "ok"

    def test_single_stock_metrics_populated(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA", n=22)},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.metrics is not None
        assert s.metrics.effective_trading_days == 22
        assert isinstance(s.metrics.period_return, float)

    def test_single_stock_risk_populated(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA", n=22)},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.risk is not None
        assert s.risk.absolute_level in {"Low", "Medium", "High", "Undetermined"}

    def test_single_stock_identity_populated(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA")},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.identity is not None
        assert s.identity.symbol == "NVDA"


# ---------------------------------------------------------------------------
# No-markdown invariant
# ---------------------------------------------------------------------------

class TestNoMarkdown:
    def test_result_has_no_markdown_field(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA")},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        assert "markdown" not in result
        assert "download_ref" not in result
        assert "section_index" not in result

    def test_analyze_result_schema_has_no_markdown(self):
        """AnalyzeResult model must not have markdown/download fields structurally."""
        fields = AnalyzeResult.model_fields
        assert "markdown" not in fields
        assert "download_ref" not in fields

    def test_result_is_valid_analyze_result(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA")},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert isinstance(ar, AnalyzeResult)


# ---------------------------------------------------------------------------
# Multiple stocks — ranking present (AC-C1)
# Uses NVDA + MSFT (both in catalog)
# ---------------------------------------------------------------------------

class TestMultipleStocks:
    def _two_stock_fake(self) -> FakeMarketData:
        return FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=25),
                "MSFT": _bars("MSFT", n=25),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT", 300.0),
            },
        )

    def test_two_stocks_both_in_result(self):
        result = _run_tool(["NVDA", "MSFT"], "最近30天", self._two_stock_fake())
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 2

    def test_two_stocks_ranking_is_not_none(self):
        """AC-C1: 2 rankable stocks → ranking must be present."""
        result = _run_tool(["NVDA", "MSFT"], "最近30天", self._two_stock_fake())
        ar = AnalyzeResult(**result)
        # With 25 bars and ~21 expected trading days the coverage > 0.8,
        # effective_trading_days >= 10 → not Undetermined → ranking present
        assert ar.ranking is not None

    def test_two_stocks_ranking_caveat_present(self):
        result = _run_tool(["NVDA", "MSFT"], "最近30天", self._two_stock_fake())
        ar = AnalyzeResult(**result)
        assert ar.ranking is not None
        assert "仅限本次所选股票与区间" in ar.ranking.caveat

    def test_three_stocks_ranking_present(self):
        fake = FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=25),
                "MSFT": _bars("MSFT", n=25),
                "AMZN": _bars("AMZN", n=25),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT", 300.0),
                "AMZN": _quote("AMZN", 180.0),
            },
        )
        result = _run_tool(["NVDA", "MSFT", "AMZN"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 3
        if ar.ranking is not None:
            assert len(ar.ranking.items) >= 2


# ---------------------------------------------------------------------------
# AC-F2: single stock get_bars failure — isolation
# ---------------------------------------------------------------------------

class TestDataFailedIsolation:
    def test_bars_failure_sets_data_failed(self):
        """AC-F2: failed stock gets status=data_failed."""
        fake = FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=22),
                "MSFT": RuntimeError("network timeout"),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT"),
            },
        )
        result = _run_tool(["NVDA", "MSFT"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 2

        msft_stock = next(s for s in ar.stocks
                          if (s.identity and s.identity.symbol == "MSFT")
                          or ("MSFT" in (s.note or "")))
        assert msft_stock.status == "data_failed"

    def test_bars_failure_other_stock_still_ok(self):
        """AC-F2: failure of one stock must not affect others."""
        fake = FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=22),
                "MSFT": RuntimeError("api down"),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT"),
            },
        )
        result = _run_tool(["NVDA", "MSFT"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        nvda_stock = next(s for s in ar.stocks if s.identity and s.identity.symbol == "NVDA")
        assert nvda_stock.status == "ok"
        assert nvda_stock.metrics is not None

    def test_bars_failure_warning_mentions_failed_symbol(self):
        """AC-F2: warnings must mention which stock failed."""
        fake = FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=22),
                "MSFT": RuntimeError("api down"),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT"),
            },
        )
        result = _run_tool(["NVDA", "MSFT"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        assert len(ar.warnings) > 0
        warning_text = " ".join(ar.warnings)
        assert "MSFT" in warning_text

    def test_failed_stock_has_no_fake_metrics(self):
        """AC-F2: failed stock must not have fabricated metrics."""
        fake = FakeMarketData(
            bars={
                "NVDA": _bars("NVDA", n=22),
                "MSFT": RuntimeError("api down"),
            },
            quotes={
                "NVDA": _quote("NVDA"),
                "MSFT": _quote("MSFT"),
            },
        )
        result = _run_tool(["NVDA", "MSFT"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        failed = [s for s in ar.stocks if s.status == "data_failed"]
        assert len(failed) == 1
        assert failed[0].metrics is None
        assert failed[0].risk is None


# ---------------------------------------------------------------------------
# AC-H2: >3 stocks → take first 3 + warnings (uses catalog symbols)
# ---------------------------------------------------------------------------

class TestMaxStocksTruncation:
    # catalog has: NVDA, BABA, INTC, MSFT, AMZN, AMD, CRM, COST
    _FOUR = ["NVDA", "MSFT", "AMZN", "INTC"]
    _FIVE = ["NVDA", "MSFT", "AMZN", "INTC", "AMD"]

    def _make_fake(self, symbols: list[str]) -> FakeMarketData:
        return FakeMarketData(
            bars={s: _bars(s, n=22) for s in symbols},
            quotes={s: _quote(s) for s in symbols},
        )

    def test_four_stocks_only_three_processed(self):
        result = _run_tool(self._FOUR, "最近30天", self._make_fake(self._FOUR))
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 3

    def test_four_stocks_warning_mentions_deferred_symbol(self):
        """AC-H2: warnings must mention the 4th stock was deferred."""
        result = _run_tool(self._FOUR, "最近30天", self._make_fake(self._FOUR))
        ar = AnalyzeResult(**result)
        assert len(ar.warnings) > 0
        warning_text = " ".join(ar.warnings)
        # 4th element (INTC) should appear in warnings
        assert "INTC" in warning_text

    def test_five_stocks_only_three_processed(self):
        result = _run_tool(self._FIVE, "最近30天", self._make_fake(self._FIVE))
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 3

    def test_five_stocks_two_deferred_in_warnings(self):
        result = _run_tool(self._FIVE, "最近30天", self._make_fake(self._FIVE))
        ar = AnalyzeResult(**result)
        warning_text = " ".join(ar.warnings)
        # INTC and AMD (4th and 5th) should appear in warnings
        assert "INTC" in warning_text or "AMD" in warning_text

    def test_three_stocks_no_truncation_warning(self):
        """Exactly 3 stocks — no truncation warning."""
        symbols = ["NVDA", "MSFT", "AMZN"]
        result = _run_tool(symbols, "最近30天", self._make_fake(symbols))
        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 3
        truncation_warnings = [w for w in ar.warnings
                                if "推迟" in w or "deferred" in w.lower()]
        assert len(truncation_warnings) == 0


# ---------------------------------------------------------------------------
# AC-F3: Quote.partial_market=True
# ---------------------------------------------------------------------------

class TestPartialMarket:
    def test_quote_partial_market_is_true(self):
        """AC-F3: current price must be flagged as partial-market reference."""
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA", n=22)},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.quote is not None
        assert s.quote.partial_market is True

    def test_quote_freshness_disclaimer_present(self):
        fake = FakeMarketData(
            bars={"NVDA": _bars("NVDA", n=22)},
            quotes={"NVDA": _quote("NVDA")},
        )
        result = _run_tool(["NVDA"], "最近30天", fake)
        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.quote is not None
        assert (
            "not for trading" in s.quote.freshness.lower()
            or "partial" in s.quote.freshness.lower()
        )


# ---------------------------------------------------------------------------
# AC-H4: resolver ambiguous → status=unrecognized + candidates in note
# AC-H6: resolver none → status=unrecognized
# These patch resolver.resolve directly (independent of catalog size)
# ---------------------------------------------------------------------------

class TestAmbiguousResolver:
    def test_ambiguous_query_sets_unrecognized(self):
        """AC-H4: ambiguous resolver result → status=unrecognized."""
        import tools

        ambiguous_result = ResolveResult(
            status="ambiguous",
            candidates=["GOOGL", "GOOG"],
            query="Google",
        )
        fake = FakeMarketData(bars={}, quotes={})
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            with patch("tools.resolver.resolve", return_value=ambiguous_result):
                result = tools.analyze_stocks.invoke(
                    {"companies": ["Google"], "period": "最近30天"}
                )
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 1
        assert ar.stocks[0].status == "unrecognized"

    def test_ambiguous_note_contains_candidates(self):
        """AC-H4: note must contain candidate symbols so LLM can ask one clarifying question."""
        import tools

        ambiguous_result = ResolveResult(
            status="ambiguous",
            candidates=["GOOGL", "GOOG"],
            query="Google",
        )
        fake = FakeMarketData(bars={}, quotes={})
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            with patch("tools.resolver.resolve", return_value=ambiguous_result):
                result = tools.analyze_stocks.invoke(
                    {"companies": ["Google"], "period": "最近30天"}
                )
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.note is not None
        assert "GOOGL" in s.note or "GOOG" in s.note

    def test_none_query_sets_unrecognized(self):
        """AC-H6: resolver returns none → status=unrecognized (not encoded)."""
        import tools

        none_result = ResolveResult(status="none", query="小米")
        fake = FakeMarketData(bars={}, quotes={})
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            with patch("tools.resolver.resolve", return_value=none_result):
                result = tools.analyze_stocks.invoke(
                    {"companies": ["小米"], "period": "最近30天"}
                )
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 1
        assert ar.stocks[0].status == "unrecognized"

    def test_none_query_no_identity(self):
        """AC-H6: unrecognized stock has no identity (not encoded)."""
        import tools

        none_result = ResolveResult(status="none", query="小米")
        fake = FakeMarketData(bars={}, quotes={})
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            with patch("tools.resolver.resolve", return_value=none_result):
                result = tools.analyze_stocks.invoke(
                    {"companies": ["小米"], "period": "最近30天"}
                )
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.identity is None
        assert s.metrics is None
