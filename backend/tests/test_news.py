"""Tests for services/news.py — fully offline (FakeTavily, no real network).

Covers:
- Top-N selection by |pct_move| (5 moves in, 3 largest-magnitude chosen)
- dict->NewsItem mapping: title/url/source/published_date/snippet/explanation
- Empty results -> news==[] and honest note set
- client.search raises -> no exception escapes; that event gets the honest note
- attribution_confidence is never 'High'; default is 'Low'
- Medium confidence when article dated within ±1 day and clearly about the company
"""
from __future__ import annotations

import pytest

from models import CompanyIdentity, SignificantMove
from services.news import (
    TavilyNewsClient,
    _HONEST_NOTE,
    collect_event_evidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _identity(name: str = "Apple Inc.", symbol: str = "AAPL") -> CompanyIdentity:
    return CompanyIdentity(
        name=name,
        symbol=symbol,
        exchange="NASDAQ",
        instrument="common",
    )


def _move(date: str, pct: float) -> SignificantMove:
    direction = "up" if pct >= 0 else "down"
    return SignificantMove(date=date, pct_move=pct, direction=direction)


def _raw_article(
    title: str = "Apple reports record earnings",
    url: str = "https://example.com/article",
    source: str = "Reuters",
    published_date: str = "2024-03-15",
    content: str = "Apple Inc reported record quarterly earnings on Friday.",
) -> dict:
    return {
        "title": title,
        "url": url,
        "source": source,
        "published_date": published_date,
        "content": content,
    }


class FakeTavily:
    """Injectable fake client that returns pre-canned results without any network call."""

    def __init__(self, results: list[dict] | Exception | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[dict] = []

    def search(
        self,
        query: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        self.calls.append({"query": query, "start_date": start_date, "end_date": end_date})
        if isinstance(self._results, Exception):
            raise self._results
        return list(self._results)


# ---------------------------------------------------------------------------
# Top-N selection
# ---------------------------------------------------------------------------

class TestTopNSelection:
    def test_top3_chosen_by_abs_pct_move(self):
        """Given 5 moves, only the 3 with largest |pct_move| appear in output."""
        moves = [
            _move("2024-01-02", 0.03),   # |3%| — 3rd largest
            _move("2024-01-03", -0.07),  # |7%| — 1st largest
            _move("2024-01-04", 0.01),   # |1%| — 5th
            _move("2024-01-05", 0.05),   # |5%| — 2nd largest
            _move("2024-01-08", -0.02),  # |2%| — 4th
        ]
        fake = FakeTavily([])
        results = collect_event_evidence(_identity(), moves, client=fake, max_events=3)

        assert len(results) == 3
        result_dates = {r.date for r in results}
        # 2024-01-03 (7%), 2024-01-05 (5%), 2024-01-02 (3%) — the top 3
        assert "2024-01-03" in result_dates
        assert "2024-01-05" in result_dates
        assert "2024-01-02" in result_dates
        # The two smallest must NOT be included
        assert "2024-01-04" not in result_dates
        assert "2024-01-08" not in result_dates

    def test_fewer_moves_than_max_events(self):
        """If fewer moves exist than max_events, return all of them."""
        moves = [_move("2024-01-02", 0.04)]
        fake = FakeTavily([])
        results = collect_event_evidence(_identity(), moves, client=fake, max_events=3)
        assert len(results) == 1

    def test_empty_moves_returns_empty(self):
        fake = FakeTavily([])
        results = collect_event_evidence(_identity(), [], client=fake, max_events=3)
        assert results == []

    def test_max_events_one(self):
        """max_events=1 returns only the single largest-magnitude move."""
        moves = [
            _move("2024-01-02", 0.03),
            _move("2024-01-03", -0.08),
            _move("2024-01-04", 0.05),
        ]
        fake = FakeTavily([])
        results = collect_event_evidence(_identity(), moves, client=fake, max_events=1)
        assert len(results) == 1
        assert results[0].date == "2024-01-03"

    def test_negative_moves_use_absolute_value(self):
        """A -6% move outranks a +4% move."""
        moves = [
            _move("2024-01-02", 0.04),
            _move("2024-01-03", -0.06),
        ]
        fake = FakeTavily([])
        results = collect_event_evidence(_identity(), moves, client=fake, max_events=1)
        assert results[0].date == "2024-01-03"


# ---------------------------------------------------------------------------
# dict -> NewsItem mapping
# ---------------------------------------------------------------------------

class TestNewsItemMapping:
    def test_all_fields_populated(self):
        raw = _raw_article(
            title="Apple beats estimates",
            url="https://reuters.com/apple",
            source="Reuters",
            published_date="2024-03-15",
            content="Apple Inc. reported strong results.",
        )
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert len(results) == 1
        items = results[0].news
        assert len(items) == 1
        item = items[0]
        assert item.title == "Apple beats estimates"
        assert item.url == "https://reuters.com/apple"
        assert item.source == "Reuters"
        assert item.published_date == "2024-03-15"
        assert item.snippet is not None and "Apple" in item.snippet
        assert item.explanation is not None and len(item.explanation) > 0

    def test_source_falls_back_to_domain(self):
        """When 'source' is absent, domain is extracted from URL."""
        raw = _raw_article(source=None, url="https://wsj.com/markets/apple-up")
        raw.pop("source", None)
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        item = results[0].news[0]
        assert item.source == "wsj.com"

    def test_snippet_truncated_to_300_chars(self):
        long_content = "x" * 500
        raw = _raw_article(content=long_content)
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        item = results[0].news[0]
        assert item.snippet is not None
        assert len(item.snippet) <= 300

    def test_missing_title_skipped(self):
        """Articles without a title are dropped."""
        raw = _raw_article()
        raw["title"] = ""
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].news == []

    def test_missing_url_skipped(self):
        """Articles without a URL are dropped."""
        raw = _raw_article()
        raw["url"] = ""
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].news == []

    def test_multiple_articles_all_mapped(self):
        raws = [
            _raw_article(title=f"Article {i}", url=f"https://example.com/{i}")
            for i in range(3)
        ]
        fake = FakeTavily(raws)
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert len(results[0].news) == 3


# ---------------------------------------------------------------------------
# Empty results -> honest note
# ---------------------------------------------------------------------------

class TestEmptyResults:
    def test_empty_results_sets_honest_note(self):
        fake = FakeTavily([])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        ev = results[0]
        assert ev.news == []
        assert ev.note == _HONEST_NOTE

    def test_empty_results_confidence_is_low(self):
        fake = FakeTavily([])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].attribution_confidence == "Low"

    def test_all_invalid_articles_treated_as_empty(self):
        """If all returned articles lack title/url, news==[] and note is set."""
        raws = [{"title": "", "url": ""}, {"title": "only title"}]
        fake = FakeTavily(raws)
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        ev = results[0]
        assert ev.news == []
        assert ev.note == _HONEST_NOTE


# ---------------------------------------------------------------------------
# client.search raises -> no exception escapes
# ---------------------------------------------------------------------------

class TestSearchRaises:
    def test_search_raises_does_not_propagate(self):
        """If client.search raises, collect_event_evidence must not raise."""
        fake = FakeTavily(RuntimeError("network failure"))
        # Must not raise:
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert len(results) == 1

    def test_search_raises_gives_honest_note(self):
        fake = FakeTavily(RuntimeError("timeout"))
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        ev = results[0]
        assert ev.news == []
        assert ev.note == _HONEST_NOTE
        assert ev.attribution_confidence == "Low"

    def test_search_raises_on_one_does_not_affect_others(self):
        """A failure on move 1 does not prevent move 2 from being processed."""

        class PartialFail:
            """Raises on first call, returns data on second."""
            def __init__(self) -> None:
                self._count = 0

            def search(self, query: str, *, start_date=None, end_date=None) -> list[dict]:
                self._count += 1
                if self._count == 1:
                    raise RuntimeError("first call fails")
                return [_raw_article()]

        moves = [_move("2024-03-15", 0.09), _move("2024-03-10", 0.07)]
        results = collect_event_evidence(_identity(), moves, client=PartialFail(), max_events=2)
        assert len(results) == 2
        # First move (largest magnitude) failed -> honest note
        assert results[0].note == _HONEST_NOTE
        # Second move succeeded -> has news
        assert len(results[1].news) >= 1


# ---------------------------------------------------------------------------
# attribution_confidence: never 'High', default 'Low'
# ---------------------------------------------------------------------------

class TestAttributionConfidence:
    def test_confidence_never_high_with_canned_data(self):
        raw = _raw_article(published_date="2024-03-15")
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].attribution_confidence != "High"

    def test_confidence_default_low_when_no_close_match(self):
        """Article dated far from move date -> 'Low'."""
        raw = _raw_article(published_date="2024-01-01")
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].attribution_confidence == "Low"

    def test_confidence_medium_when_close_date_and_company_mentioned(self):
        """Article dated within ±1 day and mentions the company -> 'Medium'."""
        raw = _raw_article(
            title="Apple Inc. AAPL surges on strong revenue outlook",
            published_date="2024-03-15",  # same date as move
            content="Apple Inc. announced strong quarterly results.",
        )
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(name="Apple Inc.", symbol="AAPL"),
            [_move("2024-03-15", 0.05)],
            client=fake,
        )
        assert results[0].attribution_confidence == "Medium"

    def test_confidence_low_on_empty_results(self):
        fake = FakeTavily([])
        results = collect_event_evidence(
            _identity(), [_move("2024-03-15", 0.05)], client=fake
        )
        assert results[0].attribution_confidence == "Low"

    def test_confidence_never_high_even_with_perfect_match(self):
        """Even a same-day article explicitly about the company stays <= Medium."""
        raw = _raw_article(
            title="Apple Inc. AAPL reports massive earnings beat",
            published_date="2024-03-15",
            content="Apple Inc (AAPL) beats analyst expectations by a wide margin.",
        )
        fake = FakeTavily([raw])
        results = collect_event_evidence(
            _identity(name="Apple Inc.", symbol="AAPL"),
            [_move("2024-03-15", 0.05)],
            client=fake,
        )
        conf = results[0].attribution_confidence
        assert conf in ("Low", "Medium")
        assert conf != "High"


# ---------------------------------------------------------------------------
# EventEvidence fields pass-through
# ---------------------------------------------------------------------------

class TestEventEvidenceFields:
    def test_date_pct_move_direction_preserved(self):
        fake = FakeTavily([])
        move = _move("2024-05-20", -0.063)
        results = collect_event_evidence(_identity(), [move], client=fake)
        ev = results[0]
        assert ev.date == "2024-05-20"
        assert ev.pct_move == pytest.approx(-0.063)
        assert ev.direction == "down"

    def test_direction_up_for_positive_move(self):
        fake = FakeTavily([])
        move = _move("2024-05-20", 0.04)
        results = collect_event_evidence(_identity(), [move], client=fake)
        assert results[0].direction == "up"
