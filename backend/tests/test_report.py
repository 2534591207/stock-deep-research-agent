"""tests/test_report.py — TDD for services/report.py + tools.py::generate_report (T4.1).

Covers (per-stock report contract):
- ReportResult.reports is an ORDERED LIST of PerStockReport (one per stock)
- Each PerStockReport: report_id / title / symbol / markdown / section_index
- All 9 section headings + verbatim disclaimer (AC-D2) in EACH per-stock markdown
- Normalized series (base=100) present; section_index isolated per stock
- Chart embeds the GitHub image-host raw URL when available, else /reports/*.png
- generate_report tool returns model_dump() dict with a "reports" list
"""
from __future__ import annotations

from datetime import date

import pytest

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
# The verbatim disclaimer (must match spec §5.D / PRD §9 exactly)
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "This report is generated from market data and public information within the specified period,"
    " for information aggregation and research reference only."
    " It does not constitute investment advice, a buy/sell recommendation, or any return guarantee."
    " Temporal correlation between events and price changes does not prove causation."
    " Market prices can change rapidly; please make independent decisions based on your own risk"
    " tolerance and after consulting a professional."
)

# ---------------------------------------------------------------------------
# The required 9 section headings (AC-D1)
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "Company Snapshot",
    "Price Trend",
    "Observed Market Risk",
    "Significant Move",
    "Related Events",
    "Financial & Filing Highlights",
    "Business Risks",
    "Short-term Market View",
    "Evidence & Limitations",
]

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _bars(symbol: str = "MSFT") -> list[Bar]:
    """20 bars with modest upward drift — sufficient data coverage."""
    prices = [
        100.0, 101.5, 103.0, 102.0, 104.5, 103.5, 105.0, 107.0, 106.0, 108.0,
        109.0, 107.5, 110.0, 111.0, 109.5, 112.0, 113.0, 114.0, 112.5, 115.0,
    ]
    bars = []
    for i, p in enumerate(prices):
        day = f"2024-01-{i + 2:02d}"
        bars.append(Bar(
            date=day,
            open=p - 0.5,
            high=p + 1.0,
            low=p - 1.0,
            close=p,
            adjusted_close=p,
            volume=1_000_000.0,
        ))
    return bars


def _quote(symbol: str = "MSFT") -> Quote:
    return Quote(
        symbol=symbol,
        price=115.0,
        quote_time="2024-01-21 16:00:00",
        partial_market=True,
        source="Twelve Data",
        freshness="Partial-market reference price; not for trading.",
    )


def _fake_provider(symbols: list[str] | None = None) -> FakeMarketData:
    """Build a FakeMarketData for one or two symbols."""
    # Use catalog-known symbols: MSFT, NVDA are in us_catalog.json
    syms = symbols or ["MSFT"]
    return FakeMarketData(
        bars={s: _bars(s) for s in syms},
        quotes={s: _quote(s) for s in syms},
    )


# ---------------------------------------------------------------------------
# Import the module under test (will fail RED until implemented)
# ---------------------------------------------------------------------------

from services.report import build_report  # noqa: E402
import tools as tools_module               # noqa: E402


# ---------------------------------------------------------------------------
# Deterministic FAKES for the bonus enrichment (news / SEC).
#
# The real services.news (Tavily) and services.sec (EDGAR) make live network
# calls. To keep these tests hermetic AND to exercise the *real* rendering /
# section_index code paths, we inject deterministic fakes into services.report
# via its module-level hooks (_news_collector and _sec_provider). The fakes
# return canned data that honours the project's honesty red lines:
#   - news is "around this date, MAY be related"; attribution_confidence is
#     never 'High'; one move degrades to an honest note with no news.
#   - business-risk titles are verbatim; multiple items so per-item citation
#     (item=1,2,...) is exercised.
# ---------------------------------------------------------------------------


def _fake_news_collector(identity: CompanyIdentity, significant_moves):
    """Stand-in for services.news.collect_event_evidence.

    Returns two EventEvidence objects regardless of the (possibly empty)
    significant_moves passed in, so the rendering of both the "has news" and
    the "degraded note" branches is always exercised deterministically.
    """
    return [
        EventEvidence(
            date="2024-01-09",
            pct_move=0.0312,
            direction="up",
            attribution_confidence="Low",
            news=[
                NewsItem(
                    title=f"{identity.name} reports quarterly results",
                    url="https://news.example.com/earnings",
                    source="example.com",
                    published_date="2024-01-09",
                    explanation="Article reports the company's quarterly results.",
                ),
                NewsItem(
                    title=f"Analysts discuss {identity.symbol} outlook",
                    url="https://news.example.com/outlook",
                    source="example.com",
                    published_date="2024-01-09",
                    explanation="Article discusses analyst views on the stock.",
                ),
            ],
        ),
        EventEvidence(
            date="2024-01-16",
            pct_move=-0.0241,
            direction="down",
            attribution_confidence="Low",
            news=[],
            note=(
                "No reliable news evidence found around this date; "
                "the move is not attributed to any cause."
            ),
        ),
    ]


class _FakeSecProvider:
    """Stand-in for services.sec exposing the two methods report.py calls."""

    def get_filing_highlights(self, identity: CompanyIdentity) -> FilingHighlights:
        return FilingHighlights(
            cik="0000789019",
            recent_filings=[
                FilingHighlight(
                    form="10-K",
                    filed_date="2023-07-27",
                    url="https://www.sec.gov/Archives/edgar/data/789019/10k.htm",
                    description="Annual report",
                ),
                FilingHighlight(
                    form="10-Q",
                    filed_date="2023-10-24",
                    url="https://www.sec.gov/Archives/edgar/data/789019/10q.htm",
                    description="Quarterly report",
                ),
            ],
            key_financials=[
                FinancialFact(
                    label="Revenue",
                    value=211915000000.0,
                    unit="USD",
                    period="FY2023",
                    source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
                ),
                FinancialFact(
                    label="Net Income",
                    value=72361000000.0,
                    unit="USD",
                    period="FY2023",
                    source_url="https://data.sec.gov/api/xbrl/companyfacts/CIK0000789019.json",
                ),
            ],
        )

    def get_business_risks(self, identity: CompanyIdentity) -> BusinessRisks:
        # Multiple verbatim items so per-item citation (item=1,2,3) is exercised.
        source = "https://www.sec.gov/Archives/edgar/data/789019/10k.htm"
        source_form = "10-K (filed 2023-07-27)"
        return BusinessRisks(
            source_form=source_form,
            source_url=source,
            items=[
                BusinessRiskItem(
                    title="We face intense competition across our businesses.",
                    summary="Competitors range from large multinationals to startups.",
                    source_form=source_form,
                    source_url=source,
                ),
                BusinessRiskItem(
                    title="Cyberattacks and security vulnerabilities could harm our business.",
                    summary="Threats are increasing in frequency and sophistication.",
                    source_form=source_form,
                    source_url=source,
                ),
                BusinessRiskItem(
                    title="Issues in the development and use of AI may result in liabilities.",
                    summary=None,
                    source_form=source_form,
                    source_url=source,
                ),
            ],
        )


@pytest.fixture(autouse=True, scope="module")
def _inject_report_bonus_fakes():
    """Inject deterministic news/SEC fakes into services.report for this module.

    Module-scoped + autouse so EVERY report build in this file renders the bonus
    sections from canned data instead of touching the live Tavily/SEC network.
    Hooks are restored on teardown so other test modules are unaffected.
    """
    import services.report as report_module

    orig_news = report_module._news_collector
    orig_sec = report_module._sec_provider
    report_module._news_collector = _fake_news_collector
    report_module._sec_provider = _FakeSecProvider()
    try:
        yield
    finally:
        report_module._news_collector = orig_news
        report_module._sec_provider = orig_sec


# ---------------------------------------------------------------------------
# FAKE GitHub image host. By default it returns None so the chart degrades to
# the local /reports/<file>.png path (no network). A dedicated test flips it to
# return a raw URL and asserts the URL is embedded.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_image_host(monkeypatch):
    """Default: image host returns None (offline degrade) for every test.

    Individual tests override services.image_host.upload_png as needed. This
    autouse stub guarantees no test in this module ever touches real GitHub.
    """
    import services.image_host as image_host

    def _no_upload(data, dest_filename, settings, *, client=None):
        return None

    monkeypatch.setattr(image_host, "upload_png", _no_upload)


def _combined_markdown(result) -> str:
    """Concatenate every per-stock report's markdown (for whole-report asserts)."""
    return "\n\n".join(r.markdown for r in result.reports)


def _combined_section_index(result):
    """Flatten every per-stock report's section_index into one list."""
    out = []
    for r in result.reports:
        out.extend(r.section_index)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildReportSingleStock:
    """build_report for a single company."""

    def _run(self, symbols=None, period="最近一个月"):
        syms = symbols or ["MSFT"]
        fake = _fake_provider(syms)
        today = date(2024, 1, 21)
        return build_report(syms, period, fake, today=today)

    def test_returns_report_result(self):
        result = self._run()
        # Must be a ReportResult carrying a per-stock reports list.
        from models import PerStockReport, ReportResult
        assert isinstance(result, ReportResult)
        assert len(result.reports) == 1
        assert isinstance(result.reports[0], PerStockReport)

    def test_markdown_is_string(self):
        result = self._run()
        md = result.reports[0].markdown
        assert isinstance(md, str)
        assert len(md) > 100

    def test_report_id_and_title_present(self):
        result = self._run(symbols=["MSFT"])
        rep = result.reports[0]
        # report_id is stable/unique per (stock, generation): "<SYMBOL>-<hash>".
        assert rep.report_id.startswith("MSFT-")
        assert rep.symbol == "MSFT"
        assert "MSFT" in rep.title

    def test_all_nine_section_headings_present(self):
        result = self._run()
        md = result.reports[0].markdown
        for section in REQUIRED_SECTIONS:
            assert section in md, f"Missing section heading: {section!r}"

    def test_disclaimer_verbatim(self):
        """AC-D2: disclaimer must appear verbatim in each per-stock report."""
        result = self._run()
        assert DISCLAIMER in result.reports[0].markdown, (
            "Verbatim disclaimer not found in report markdown"
        )

    def test_normalized_series_base_100_present(self):
        """Price Trend section must reference normalized base=100."""
        result = self._run()
        md = result.reports[0].markdown
        # The normalized series starts at 100.0; check for "100.0" or "100" near base indicator
        assert "100" in md, "Normalized base=100 value not found in markdown"
        # Also check that the Price Trend section exists and has some numeric content
        assert "Price Trend" in md

    def test_section_index_non_empty(self):
        result = self._run()
        assert len(result.reports[0].section_index) > 0

    def test_section_index_items_have_required_fields(self):
        result = self._run()
        for item in result.reports[0].section_index:
            assert isinstance(item.owner_company, str)
            assert isinstance(item.section, str)
            assert isinstance(item.item, int)
            assert isinstance(item.text, str)

    def test_section_index_contains_business_risks(self):
        """Business Risks placeholder must appear in section_index."""
        result = self._run()
        sections = {item.section for item in result.reports[0].section_index}
        assert "Business Risks" in sections

    def test_section_index_business_risks_has_item_1(self):
        """Even placeholder Business Risks must have item=1."""
        result = self._run()
        br_items = [
            item for item in result.reports[0].section_index
            if item.section == "Business Risks"
        ]
        assert len(br_items) >= 1
        assert any(i.item == 1 for i in br_items)

    def test_section_index_owner_company_is_symbol(self):
        """owner_company in section_index must match the requested symbol."""
        result = self._run(symbols=["MSFT"])
        for item in result.reports[0].section_index:
            assert item.owner_company == "MSFT"

    def test_no_leading_yaml_frontmatter_delimiter(self):
        """Regression: report must NOT start with '---' (YAML frontmatter bug).

        A leading '---' on the first line causes frontmatter-aware Markdown
        parsers (Obsidian, VS Code, GitHub, Typora) to treat the report body
        as YAML, which either errors or hides the entire content.  The report
        must begin with a heading ('# '), and the mid-document '---' before the
        Disclaimer section must still be present.
        """
        result = self._run()
        md = result.reports[0].markdown
        # First non-empty line must be a heading, not a frontmatter delimiter.
        first_nonempty = next(line for line in md.splitlines() if line.strip())
        assert first_nonempty.startswith("# "), (
            f"Report must start with a '# ' heading, got: {first_nonempty!r}"
        )
        assert not md.startswith("---"), (
            "Report must NOT begin with '---' (YAML frontmatter delimiter)"
        )
        # The mid-document horizontal rule before Disclaimer must be retained.
        assert "\n---\n" in md, (
            "Mid-document '---' separator before Disclaimer must still be present"
        )
        assert "## Disclaimer" in md


class TestBuildReportTwoStocks:
    """build_report for two companies produces entries for each."""

    def _run(self, period="最近一个月"):
        syms = ["MSFT", "NVDA"]
        fake = _fake_provider(syms)
        today = date(2024, 1, 21)
        return build_report(syms, period, fake, today=today)

    def test_one_report_per_stock(self):
        """A 2-stock generation yields exactly two self-contained reports."""
        result = self._run()
        assert len(result.reports) == 2
        symbols = {r.symbol for r in result.reports}
        assert symbols == {"MSFT", "NVDA"}

    def test_each_report_self_contained_nine_sections(self):
        """Every per-stock report must carry all 9 sections + its own disclaimer."""
        result = self._run()
        for rep in result.reports:
            for section in REQUIRED_SECTIONS:
                assert section in rep.markdown, (
                    f"{rep.symbol} report missing section: {section!r}"
                )
            assert DISCLAIMER in rep.markdown

    def test_relative_rank_references_batch(self):
        """Each report's §3 relative-rank line names the batch it was ranked in."""
        result = self._run()
        for rep in result.reports:
            assert "within this batch" in rep.markdown

    def test_section_index_isolated_per_stock(self):
        """Each report's section_index contains ONLY its own symbol."""
        result = self._run()
        for rep in result.reports:
            owners = {item.owner_company for item in rep.section_index}
            assert owners == {rep.symbol}

    def test_normalized_base_100_present(self):
        result = self._run()
        for rep in result.reports:
            assert "100" in rep.markdown


class TestBuildReportBonusSections:
    """Bonus sections render REAL cited content from the injected fakes.

    The module-scoped autouse fixture wires services.report to deterministic
    news/SEC fakes, so the three bonus sections must now contain real, cited
    content (no "Not available in this version" placeholder anywhere) and the
    section_index must carry per-item Business Risks entries.
    """

    def _run(self):
        """Return the single per-stock report (so .markdown / .section_index
        assertions below read against that stock's self-contained document)."""
        fake = _fake_provider(["MSFT"])
        today = date(2024, 1, 21)
        result = build_report(["MSFT"], "最近一个月", fake, today=today)
        assert len(result.reports) == 1
        return result.reports[0]

    # ── Section headings still render ────────────────────────────────────────

    def test_related_events_heading_present(self):
        result = self._run()
        assert "Related Events" in result.markdown

    def test_financial_filing_heading_present(self):
        result = self._run()
        assert "Financial & Filing Highlights" in result.markdown

    def test_business_risks_heading_present(self):
        result = self._run()
        assert "Business Risks" in result.markdown

    # ── The old placeholder must be gone entirely ────────────────────────────

    def test_no_placeholder_text_anywhere(self):
        result = self._run()
        assert "Not available in this version" not in result.markdown

    # ── Related Events: real cited news + honest degraded note ───────────────

    def test_related_events_shows_cited_news(self):
        """With injected news fakes, the report shows cited news with a source URL."""
        result = self._run()
        md = result.markdown
        assert "https://news.example.com/earnings" in md
        assert "reports quarterly results" in md

    def test_related_events_shows_degraded_note(self):
        """The move with no news degrades to an honest, non-causal note."""
        result = self._run()
        assert "the move is not attributed to any cause" in result.markdown

    def test_related_events_never_claims_causation(self):
        """Honesty red line: never assert a cause for a move."""
        result = self._run()
        md = result.markdown.lower()
        assert "caused the" not in md
        assert "because of the news" not in md

    # ── Financial & Filing Highlights: real cited SEC content ────────────────

    def test_financial_filing_shows_filings_and_financials(self):
        result = self._run()
        md = result.markdown
        # Recent filing forms and an SEC archive link.
        assert "10-K" in md
        assert "https://www.sec.gov/Archives/edgar/data/789019/10k.htm" in md
        # Key financial labels sourced from SEC XBRL.
        assert "Revenue" in md
        assert "Net Income" in md

    # ── Business Risks: verbatim multi-item content ──────────────────────────

    def test_business_risks_shows_verbatim_titles(self):
        result = self._run()
        md = result.markdown
        assert "We face intense competition across our businesses." in md
        assert "Cyberattacks and security vulnerabilities could harm our business." in md

    # ── section_index: per-item Business Risks entries (item=1,2,3) ──────────

    def test_section_index_business_risks_has_per_item_entries(self):
        result = self._run()
        br_items = [
            item for item in result.section_index
            if item.section == "Business Risks"
        ]
        # The fake returns three risk items → three citable entries.
        assert len(br_items) == 3
        item_numbers = sorted(i.item for i in br_items)
        assert item_numbers == [1, 2, 3]

    def test_section_index_business_risks_items_cite_verbatim_text(self):
        result = self._run()
        br_by_item = {
            item.item: item
            for item in result.section_index
            if item.section == "Business Risks"
        }
        assert br_by_item[1].text.startswith(
            "We face intense competition across our businesses."
        )
        assert br_by_item[2].text.startswith(
            "Cyberattacks and security vulnerabilities could harm our business."
        )
        # Each cited entry carries the SEC source URL.
        for item in br_by_item.values():
            assert item.source == "https://www.sec.gov/Archives/edgar/data/789019/10k.htm"
            assert item.owner_company == "MSFT"

    def test_section_index_related_events_has_cited_entry(self):
        result = self._run()
        re_items = [
            item for item in result.section_index
            if item.section == "Related Events"
        ]
        # One entry per EventEvidence returned by the fake (two moves).
        assert len(re_items) == 2
        # At least one carries a news source URL (the cited move).
        assert any(i.source == "https://news.example.com/earnings" for i in re_items)

    def test_section_index_financial_filing_has_entries(self):
        result = self._run()
        ff_items = [
            item for item in result.section_index
            if item.section == "Financial & Filing Highlights"
        ]
        # 2 recent filings + 2 key financials = 4 citable entries.
        assert len(ff_items) == 4
        assert any(i.source == "https://www.sec.gov/Archives/edgar/data/789019/10k.htm"
                   for i in ff_items)


class TestGenerateReportTool:
    """tools.py::generate_report returns model_dump() dict."""

    def setup_method(self):
        """Inject fake provider into services.report module."""
        import services.report as report_module
        self._original_provider = report_module._provider
        self._original_today = report_module._today_override
        report_module._provider = _fake_provider(["MSFT"])
        report_module._today_override = date(2024, 1, 21)

    def teardown_method(self):
        """Restore original provider and today override."""
        import services.report as report_module
        report_module._provider = self._original_provider
        report_module._today_override = self._original_today

    def test_generate_report_returns_dict(self):
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        assert isinstance(result, dict)

    def test_generate_report_dict_has_reports_list(self):
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        assert "reports" in result
        assert isinstance(result["reports"], list)
        assert len(result["reports"]) == 1

    def test_generate_report_per_stock_dict_shape(self):
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        rep = result["reports"][0]
        for key in ("report_id", "title", "symbol", "markdown", "section_index"):
            assert key in rep
        assert rep["report_id"].startswith("MSFT-")
        assert rep["symbol"] == "MSFT"
        assert isinstance(rep["markdown"], str)
        assert isinstance(rep["section_index"], list)
        assert len(rep["section_index"]) > 0

    def test_generate_report_all_sections_in_markdown(self):
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        md = result["reports"][0]["markdown"]
        for section in REQUIRED_SECTIONS:
            assert section in md, f"Tool result missing section: {section!r}"

    def test_generate_report_disclaimer_in_markdown(self):
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        assert DISCLAIMER in result["reports"][0]["markdown"]

    def test_generate_report_two_stocks_two_reports(self):
        """A 2-stock request yields one dict report per stock."""
        import services.report as report_module
        report_module._provider = _fake_provider(["MSFT", "NVDA"])
        from tools import generate_report
        result = generate_report.invoke(
            {"companies": ["MSFT", "NVDA"], "period": "最近一个月"}
        )
        assert len(result["reports"]) == 2
        symbols = {r["symbol"] for r in result["reports"]}
        assert symbols == {"MSFT", "NVDA"}


class TestReportChartImageHost:
    """The chart embed uses the GitHub image host URL when available, else the
    local /reports/<file>.png path (honest degrade). No real GitHub traffic."""

    def _build(self):
        fake = _fake_provider(["MSFT"])
        return build_report(["MSFT"], "最近一个月", fake, today=date(2024, 1, 21))

    def test_chart_embeds_github_raw_url_when_upload_succeeds(self, monkeypatch):
        """When image_host.upload_png returns a raw URL, the markdown embeds it."""
        import services.image_host as image_host

        raw_url = "https://raw.githubusercontent.com/owner/repo/report-assets/report-charts/x.png"
        calls: list[tuple] = []

        def _fake_upload(data, dest_filename, settings, *, client=None):
            calls.append((data[:8], dest_filename))
            return raw_url

        monkeypatch.setattr(image_host, "upload_png", _fake_upload)

        result = self._build()
        md = result.reports[0].markdown
        # The fake was called with real PNG bytes (magic number) ...
        assert calls and calls[0][0] == b"\x89PNG\r\n\x1a\n"
        # ... and the raw URL is embedded (not the local /reports path).
        assert f"![Price Trend Chart]({raw_url})" in md
        assert "/reports/" not in md

    def test_chart_degrades_to_local_path_when_upload_returns_none(self, monkeypatch):
        """When upload_png returns None, the markdown embeds /reports/<file>.png."""
        import re as _re

        import services.image_host as image_host

        monkeypatch.setattr(
            image_host, "upload_png",
            lambda data, dest_filename, settings, *, client=None: None,
        )

        result = self._build()
        md = result.reports[0].markdown
        m = _re.search(r"!\[Price Trend Chart\]\((/reports/[^)]+\.png)\)", md)
        assert m is not None, "degrade path must embed a /reports/<file>.png link"
        assert "raw.githubusercontent" not in md
