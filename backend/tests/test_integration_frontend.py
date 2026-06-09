"""tests/test_integration_frontend.py — frontend⇆backend integration surface.

These tests lock in the cross-cutting wiring the browser SPA depends on, all
exercised offline through fastapi.testclient.TestClient (no network / OpenAI):

  1. CORS — the Vite dev origins (http://localhost:5173 and
     http://127.0.0.1:5173) are allowed for preflight and actual requests,
     with all methods/headers, so the browser can call /chat, /report/* and
     /health from a different origin.
  2. Static report assets — generated price-trend PNGs under _reports/ are
     served at /reports/<file>, so the report viewer can load the chart image
     over HTTP.
  3. Chart reference is an HTTP URL — services.report.build_report embeds the
     chart as a browser-loadable "/reports/<file>" link (NOT a server-local
     filesystem path), and that exact file is then retrievable via the mount.

Isolation: ``app.require_keys`` is patched to a no-op (mirrors test_health.py)
so lifespan startup never aborts when .env keys are absent. The report is built
with a deterministic FakeMarketData provider plus injected news/SEC fakes that
honour the honesty red lines (no causation; attribution confidence never High).
No real Yahoo Finance / Tavily / SEC traffic occurs.
"""
from __future__ import annotations

import re
from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from models import (
    Bar,
    BusinessRiskItem,
    BusinessRisks,
    CompanyIdentity,
    EventEvidence,
    FilingHighlight,
    FilingHighlights,
    FinancialFact,
    NewsItem,
    Quote,
)
from services.market_data import FakeMarketData


# ---------------------------------------------------------------------------
# Deterministic fakes (offline) — modelled on tests/test_report.py.
# ---------------------------------------------------------------------------

def _bars(symbol: str = "MSFT") -> list[Bar]:
    prices = [
        100.0, 101.5, 103.0, 102.0, 104.5, 103.5, 105.0, 107.0, 106.0, 108.0,
        109.0, 107.5, 110.0, 111.0, 109.5, 112.0, 113.0, 114.0, 112.5, 115.0,
    ]
    out: list[Bar] = []
    for i, p in enumerate(prices):
        out.append(Bar(
            date=f"2024-01-{i + 2:02d}",
            open=p - 0.5, high=p + 1.0, low=p - 1.0,
            close=p, adjusted_close=p, volume=1_000_000.0,
        ))
    return out


def _quote(symbol: str = "MSFT") -> Quote:
    return Quote(
        symbol=symbol, price=115.0, quote_time="2024-01-21 16:00:00",
        partial_market=True, source="Yahoo Finance",
        freshness="Partial-market reference price; not for trading.",
    )


def _fake_provider(symbols: list[str]) -> FakeMarketData:
    return FakeMarketData(
        bars={s: _bars(s) for s in symbols},
        quotes={s: _quote(s) for s in symbols},
    )


def _fake_news_collector(identity: CompanyIdentity, significant_moves):
    """Honest, non-causal news evidence (attribution confidence never High)."""
    return [
        EventEvidence(
            date="2024-01-09",
            pct_move=0.0312,
            direction="up",
            attribution_confidence="Low",
            note="No clearly related news found around this date.",
            news=[
                NewsItem(
                    title=f"{identity.name} releases quarterly results",
                    url="https://example.com/news/q",
                    source="example.com",
                    published_date="2024-01-09",
                    explanation="Article published around this date; may be related.",
                ),
            ],
        ),
    ]


class _FakeSecProvider:
    def get_filing_highlights(self, identity: CompanyIdentity) -> FilingHighlights:
        return FilingHighlights(
            recent_filings=[
                FilingHighlight(form="10-K", filed_date="2023-10-27",
                                url="https://www.sec.gov/filing/10k"),
            ],
            key_financials=[
                FinancialFact(label="Revenue", value=211_915_000_000.0, unit="USD",
                              period="FY2023", source_url="https://www.sec.gov/xbrl"),
            ],
            note="",
        )

    def get_business_risks(self, identity: CompanyIdentity) -> BusinessRisks:
        return BusinessRisks(
            source_form="10-K",
            source_url="https://www.sec.gov/filing/10k",
            items=[
                BusinessRiskItem(
                    title="Our business is subject to intense competition.",
                    summary="",
                    source_url="https://www.sec.gov/filing/10k",
                ),
            ],
            note="",
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_client():
    """TestClient with require_keys patched out (startup never aborts offline)."""
    with patch("app.require_keys", return_value=None):
        from app import app
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


@pytest.fixture()
def report_markdown(monkeypatch):
    """Build a real report offline; return its (single) markdown.

    The GitHub image host is stubbed to return None so the chart degrades to a
    local ``/reports/<file>.png`` link — exactly what the static-mount tests
    below assert (and no real GitHub traffic occurs).
    """
    import services.image_host as image_host
    import services.report as report_module

    monkeypatch.setattr(
        image_host, "upload_png",
        lambda data, dest_filename, settings, *, client=None: None,
    )

    orig_news = report_module._news_collector
    orig_sec = report_module._sec_provider
    report_module._news_collector = _fake_news_collector
    report_module._sec_provider = _FakeSecProvider()
    try:
        result = report_module.build_report(
            ["MSFT"], "最近一个月", _fake_provider(["MSFT"]), today=date(2024, 1, 21)
        )
    finally:
        report_module._news_collector = orig_news
        report_module._sec_provider = orig_sec
    assert len(result.reports) == 1
    return result.reports[0].markdown


# ---------------------------------------------------------------------------
# 1. CORS
# ---------------------------------------------------------------------------

_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class TestCors:
    @pytest.mark.parametrize("origin", _DEV_ORIGINS)
    def test_preflight_allows_dev_origin(self, app_client, origin):
        """A CORS preflight (OPTIONS) for POST /chat is allowed from the SPA."""
        resp = app_client.options(
            "/chat",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code in (200, 204)
        assert resp.headers.get("access-control-allow-origin") == origin
        allow_methods = resp.headers.get("access-control-allow-methods", "")
        assert "POST" in allow_methods or "*" in allow_methods

    @pytest.mark.parametrize("origin", _DEV_ORIGINS)
    def test_actual_request_echoes_origin(self, app_client, origin):
        """An actual GET /health carries the allow-origin header for the SPA."""
        resp = app_client.get("/health", headers={"Origin": origin})
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == origin

    def test_health_works_without_origin(self, app_client):
        """CORS must not break same-origin / non-browser callers."""
        resp = app_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# 2 + 3. Chart reference is an HTTP /reports URL, and the file is served.
# ---------------------------------------------------------------------------

_CHART_RE = re.compile(r"!\[[^\]]*\]\((/reports/[^)]+\.png)\)")


class TestReportChartOverHttp:
    def test_markdown_references_chart_via_reports_url(self, report_markdown):
        """The report embeds the chart as '/reports/<file>.png' (an HTTP path),
        never a server-local filesystem path the browser cannot read."""
        m = _CHART_RE.search(report_markdown)
        assert m is not None, "report markdown is missing a /reports/<file>.png chart link"
        chart_url = m.group(1)
        assert chart_url.startswith("/reports/")
        # Must not leak an absolute filesystem path.
        assert "_reports" not in chart_url
        assert not chart_url.startswith("/Users") and ":\\" not in chart_url

    def test_served_chart_is_loadable_png(self, app_client, report_markdown):
        """The exact chart file referenced by the report is retrievable via the
        /reports static mount and is returned as an image."""
        m = _CHART_RE.search(report_markdown)
        assert m is not None
        chart_url = m.group(1)  # e.g. /reports/<id>_MSFT.png

        resp = app_client.get(chart_url)
        assert resp.status_code == 200, f"chart not served at {chart_url}"
        assert resp.headers.get("content-type", "").startswith("image/")
        # PNG magic number — confirms a real rendered chart, not a stub.
        assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_unknown_chart_returns_404(self, app_client):
        """A non-existent report asset is a clean 404 (not a server error)."""
        resp = app_client.get("/reports/does-not-exist.png")
        assert resp.status_code == 404
