"""tests/test_compare.py — TDD for services/compare.py

Covers:
  AC-C2: risk_score 相同 → 并列同名次
  AC-C3: 只 1 只可排名 → 返回 None
  AC-C4: absolute_level=="Undetermined" → 进 excluded，不进 items
  AC-C5: caveat 含「仅限本次所选股票与区间」
"""
from __future__ import annotations

import pytest

from models import CompanyIdentity, Risk, StockAnalysis
from services.compare import rank

# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _identity(symbol: str) -> CompanyIdentity:
    return CompanyIdentity(
        name=symbol,
        symbol=symbol,
        exchange="NASDAQ",
        instrument="common",
    )


def _risk(risk_score: float, absolute_level: str = "Medium") -> Risk:
    return Risk(
        vol_score=0.5,
        drawdown_score=0.5,
        risk_score=risk_score,
        absolute_level=absolute_level,  # type: ignore[arg-type]
        short_term_market_view="Neutral",
        return_threshold=0.05,
    )


def _ok_stock(symbol: str, risk_score: float, absolute_level: str = "Medium") -> StockAnalysis:
    return StockAnalysis(
        identity=_identity(symbol),
        risk=_risk(risk_score, absolute_level),
        status="ok",
    )


# ---------------------------------------------------------------------------
# AC-C3: 单只可排名 → None
# ---------------------------------------------------------------------------

class TestSingleStock:
    def test_single_rankable_returns_none(self):
        stocks = [_ok_stock("AAPL", 0.7)]
        result = rank(stocks)
        assert result is None

    def test_empty_list_returns_none(self):
        result = rank([])
        assert result is None

    def test_single_unrecognized_returns_none(self):
        stocks = [StockAnalysis(status="unrecognized", note="not found")]
        result = rank(stocks)
        assert result is None

    def test_single_data_failed_returns_none(self):
        stocks = [StockAnalysis(status="data_failed", note="api error")]
        result = rank(stocks)
        assert result is None


# ---------------------------------------------------------------------------
# AC-C4: Undetermined → excluded, not in items
# ---------------------------------------------------------------------------

class TestUndetermined:
    def test_undetermined_goes_to_excluded(self):
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.5, "Low"),
            _ok_stock("TSLA", 0.6, "Undetermined"),
        ]
        result = rank(stocks)
        assert result is not None
        symbols_in_items = {item.symbol for item in result.items}
        assert "TSLA" not in symbols_in_items
        assert "TSLA" in result.excluded

    def test_undetermined_does_not_count_toward_minimum(self):
        # Only 1 rankable + 1 Undetermined → still None
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("TSLA", 0.6, "Undetermined"),
        ]
        result = rank(stocks)
        assert result is None

    def test_multiple_undetermined_all_excluded(self):
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.5, "Low"),
            _ok_stock("TSLA", 0.6, "Undetermined"),
            _ok_stock("GOOG", 0.4, "Undetermined"),
        ]
        result = rank(stocks)
        assert result is not None
        assert set(result.excluded) == {"TSLA", "GOOG"}
        symbols_in_items = {item.symbol for item in result.items}
        assert "TSLA" not in symbols_in_items
        assert "GOOG" not in symbols_in_items

    def test_non_ok_status_not_in_excluded(self):
        # status != "ok" should be silently skipped, NOT added to excluded
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.5, "Low"),
            StockAnalysis(status="unrecognized", note="not found"),
        ]
        result = rank(stocks)
        assert result is not None
        assert result.excluded == []


# ---------------------------------------------------------------------------
# AC-C2: risk_score 相同 → 并列同名次 (1,1,3 式)
# ---------------------------------------------------------------------------

class TestTieRanking:
    def test_two_tied_stocks_both_rank_1(self):
        stocks = [
            _ok_stock("AAPL", 0.7, "High"),
            _ok_stock("MSFT", 0.7, "High"),
        ]
        result = rank(stocks)
        assert result is not None
        ranks = [item.rank for item in result.items]
        assert ranks == [1, 1]

    def test_three_way_tie_all_rank_1(self):
        stocks = [
            _ok_stock("AAPL", 0.6, "Medium"),
            _ok_stock("MSFT", 0.6, "Medium"),
            _ok_stock("GOOG", 0.6, "Medium"),
        ]
        result = rank(stocks)
        assert result is not None
        ranks = [item.rank for item in result.items]
        assert all(r == 1 for r in ranks)

    def test_partial_tie_1_1_3_pattern(self):
        # AAPL and MSFT tie at 0.8, GOOG at 0.5 → ranks 1,1,3
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.8, "High"),
            _ok_stock("GOOG", 0.5, "Medium"),
        ]
        result = rank(stocks)
        assert result is not None
        rank_map = {item.symbol: item.rank for item in result.items}
        assert rank_map["AAPL"] == 1
        assert rank_map["MSFT"] == 1
        assert rank_map["GOOG"] == 3

    def test_no_tie_distinct_ranks(self):
        stocks = [
            _ok_stock("AAPL", 0.9, "High"),
            _ok_stock("MSFT", 0.5, "Medium"),
            _ok_stock("GOOG", 0.2, "Low"),
        ]
        result = rank(stocks)
        assert result is not None
        rank_map = {item.symbol: item.rank for item in result.items}
        assert rank_map["AAPL"] == 1
        assert rank_map["MSFT"] == 2
        assert rank_map["GOOG"] == 3

    def test_descending_order_by_risk_score(self):
        # Items should be sorted highest risk_score first
        stocks = [
            _ok_stock("LOW_RISK", 0.2, "Low"),
            _ok_stock("HIGH_RISK", 0.9, "High"),
            _ok_stock("MED_RISK", 0.5, "Medium"),
        ]
        result = rank(stocks)
        assert result is not None
        scores = [item.risk_score for item in result.items]
        assert scores == sorted(scores, reverse=True)
        assert result.items[0].symbol == "HIGH_RISK"
        assert result.items[0].rank == 1


# ---------------------------------------------------------------------------
# AC-C5: caveat 含「仅限本次所选股票与区间」
# ---------------------------------------------------------------------------

class TestCaveat:
    def test_caveat_contains_required_phrase(self):
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.5, "Low"),
        ]
        result = rank(stocks)
        assert result is not None
        assert "仅限本次所选股票与区间" in result.caveat

    def test_caveat_present_with_undetermined(self):
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.5, "Low"),
            _ok_stock("TSLA", 0.6, "Undetermined"),
        ]
        result = rank(stocks)
        assert result is not None
        assert "仅限本次所选股票与区间" in result.caveat

    def test_caveat_present_for_two_rankable(self):
        stocks = [
            _ok_stock("AAPL", 0.7, "Medium"),
            _ok_stock("GOOG", 0.3, "Low"),
        ]
        result = rank(stocks)
        assert result is not None
        assert "仅限本次所选股票与区间" in result.caveat


# ---------------------------------------------------------------------------
# 综合：RankingResult 结构完整性
# ---------------------------------------------------------------------------

class TestRankingResultStructure:
    def test_items_contain_symbol_rank_risk_score(self):
        stocks = [
            _ok_stock("AAPL", 0.8, "High"),
            _ok_stock("MSFT", 0.4, "Low"),
        ]
        result = rank(stocks)
        assert result is not None
        for item in result.items:
            assert isinstance(item.symbol, str)
            assert isinstance(item.rank, int)
            assert isinstance(item.risk_score, float)

    def test_risk_score_preserved_in_items(self):
        stocks = [
            _ok_stock("AAPL", 0.85, "High"),
            _ok_stock("MSFT", 0.42, "Low"),
        ]
        result = rank(stocks)
        assert result is not None
        score_map = {item.symbol: item.risk_score for item in result.items}
        assert score_map["AAPL"] == pytest.approx(0.85)
        assert score_map["MSFT"] == pytest.approx(0.42)
