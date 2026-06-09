"""tests/test_find_news_tool.py — tools.find_news (offline, fake Tavily client).

Injects fake market data (with significant moves) + a fake Tavily news client and
asserts:
  - ok path → events carry the required fields + non-causal explanation +
    attribution_confidence Low; identify/market_data/events stage events emitted
    under the resolved ticker.
  - degraded path (fake news empty / no key) → events present but unattributed
    (empty title) + honest note, no exception.
  - unrecognized company → status="unrecognized".

All numbers come from services code (metrics.compute_metrics over injected bars);
the news client never touches the network.
"""
from __future__ import annotations

import datetime

import pytest

import tools
from models import Bar
from services.market_data import FakeMarketData
from services.progress import report_progress


# ---------------------------------------------------------------------------
# Fakes / factories
# ---------------------------------------------------------------------------

class FakeTavily:
    """Injectable fake news client — returns pre-canned results, no network."""

    def __init__(self, results: list[dict] | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[dict] = []

    def search(self, query, *, start_date=None, end_date=None):  # noqa: ANN001
        self.calls.append({"query": query, "start_date": start_date, "end_date": end_date})
        return list(self._results)


def _bars_with_moves(symbol: str = "NVDA") -> list[Bar]:
    """30 bars containing at least one >=2% single-day move (significant)."""
    bars: list[Bar] = []
    price = 100.0
    for i in range(30):
        d = (datetime.date(2024, 1, 2) + datetime.timedelta(days=i)).isoformat()
        # Inject a clear +6% jump and a -5% drop; rest are tiny.
        if i == 10:
            change = 0.06
        elif i == 20:
            change = -0.05
        else:
            change = 0.001 if i % 2 == 0 else -0.001
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


def _run(company: str, period: str, *, fake_market, fake_news):
    """Invoke find_news with injected market + news providers and a capturing sink."""
    events: list[dict] = []
    sink_token = report_progress.set(lambda ev: events.append(ev))
    orig_provider = tools._PROVIDER
    orig_news = tools._NEWS_CLIENT
    tools.set_provider(fake_market)
    tools.set_news_client(fake_news)
    try:
        result = tools.find_news.invoke({"company": company, "period": period})
    finally:
        tools.set_provider(orig_provider)
        tools.set_news_client(orig_news)
        report_progress.reset(sink_token)
    return result, events


def _stage_tuples(events):
    return [(e["symbol"], e["stage"], e["status"]) for e in events
            if e.get("type") == "stage"]


# ---------------------------------------------------------------------------
# OK path with news
# ---------------------------------------------------------------------------

class TestFindNewsOk:
    def test_signature(self):
        assert set(tools.find_news.args) == {"company", "period"}

    def test_ok_returns_events_with_required_fields(self):
        article = {
            "title": "Nvidia announces new GPU lineup",
            "url": "https://example.com/nvda",
            "source": "Reuters",
            "published_date": "2024-01-12",
            "content": "Nvidia NVDA unveiled products this week.",
        }
        fake_news = FakeTavily([article])
        result, _ = _run(
            "英伟达", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": _bars_with_moves()}),
            fake_news=fake_news,
        )
        assert result["status"] == "ok"
        assert result["identity"]["symbol"] == "NVDA"
        assert result["identity"]["name"]
        assert result["identity"]["exchange"]
        assert result["period"]
        assert result["events"], "expected at least one event for significant moves"
        for ev in result["events"]:
            for key in (
                "date", "direction", "pct_move", "title", "url", "source",
                "published_date", "explanation", "attribution_confidence",
            ):
                assert key in ev
            # Non-causal: explanation must not assert causation.
            expl = (ev["explanation"] or "")
            for causal in ("caused", "导致", "因为", "drove", "triggered"):
                assert causal not in expl.lower()
            # collect_event_evidence never returns High.
            assert ev["attribution_confidence"] in ("Low", "Medium")

    def test_attribution_confidence_low_when_news_unrelated_to_date(self):
        # Article published far from the move date → confidence stays Low.
        article = {
            "title": "Some unrelated market note",
            "url": "https://example.com/x",
            "source": "Wire",
            "published_date": "2000-01-01",
            "content": "generic",
        }
        result, _ = _run(
            "NVDA", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": _bars_with_moves()}),
            fake_news=FakeTavily([article]),
        )
        assert all(ev["attribution_confidence"] == "Low" for ev in result["events"])

    def test_emits_identify_market_data_events_stages(self):
        result, events = _run(
            "英伟达", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": _bars_with_moves()}),
            fake_news=FakeTavily([]),
        )
        stages = _stage_tuples(events)
        # All stage events (identify start+done, market_data, events) keyed by
        # the resolved ticker so only ONE progress track is produced.
        assert ("NVDA", "identify", "start") in stages
        assert ("NVDA", "identify", "done") in stages
        assert ("NVDA", "market_data", "start") in stages
        assert ("NVDA", "market_data", "done") in stages
        assert ("NVDA", "events", "start") in stages
        assert ("NVDA", "events", "done") in stages
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Degraded paths — never raise, honest note
# ---------------------------------------------------------------------------

class TestFindNewsDegraded:
    def test_empty_news_degrades_with_honest_note(self):
        result, _ = _run(
            "NVDA", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": _bars_with_moves()}),
            fake_news=FakeTavily([]),  # no results (e.g. no key / nothing found)
        )
        assert result["status"] == "ok"
        # Moves detected but no usable headline → unattributed events.
        assert all(ev["title"] is None for ev in result["events"])
        assert result["note"]
        assert "证据" in result["note"] or "不可用" in result["note"]

    def test_no_significant_moves_returns_empty_events(self):
        # Flat series → no significant moves → no events, honest note, no exception.
        flat: list[Bar] = []
        price = 100.0
        for i in range(15):
            d = (datetime.date(2024, 1, 2) + datetime.timedelta(days=i)).isoformat()
            price = round(price * 1.0005, 4)
            flat.append(Bar(date=d, open=price, high=price, low=price,
                            close=price, adjusted_close=price, volume=1.0))
        result, _ = _run(
            "NVDA", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": flat}),
            fake_news=FakeTavily([]),
        )
        assert result["status"] == "ok"
        assert result["events"] == []
        assert result["note"]

    def test_market_data_failure_degrades(self):
        result, events = _run(
            "NVDA", "近三个月",
            fake_market=FakeMarketData(bars={"NVDA": RuntimeError("boom")}),
            fake_news=FakeTavily([]),
        )
        assert result["status"] == "ok"
        assert result["events"] == []
        assert result["note"]
        stages = _stage_tuples(events)
        assert ("NVDA", "market_data", "error") in stages


# ---------------------------------------------------------------------------
# Unrecognized company
# ---------------------------------------------------------------------------

class TestFindNewsUnrecognized:
    def test_unrecognized_company(self):
        result, events = _run(
            "这不是一只股票公司名", "近三个月",
            fake_market=FakeMarketData(bars={}),
            fake_news=FakeTavily([]),
        )
        assert result["status"] == "unrecognized"
        assert result["note"]
        stages = _stage_tuples(events)
        assert ("这不是一只股票公司名", "identify", "start") in stages
        assert ("这不是一只股票公司名", "identify", "error") in stages
