"""tests/test_report_cite.py — T4.2: report citation precision + no-report invariants.

Covers:
  AC-E1: Given a ReportResult with multi-company Business Risks in section_index,
         querying owner=BABA, section="Business Risks", item=2 returns the exact
         text for BABA item 2 — not another company's item, not fabricated.
  AC-C6 / D3: analyze_stocks path produces NO report (AnalyzeResult has no markdown).

All tests are offline — no real OpenAI or Twelve Data calls.
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest

from models import (
    AnalyzeResult,
    Bar,
    CompanyIdentity,
    PerStockReport,
    Quote,
    ReportResult,
    ReportSectionItem,
)
from services.market_data import FakeMarketData


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _bars(symbol: str = "BABA", n: int = 22) -> list[Bar]:
    bars = []
    price = 80.0
    for i in range(n):
        d = (datetime.date(2024, 1, 2) + datetime.timedelta(days=i)).isoformat()
        change = 0.004 if i % 3 != 0 else -0.006
        price = round(price * (1 + change), 4)
        bars.append(Bar(
            date=d,
            open=price * 0.99,
            high=price * 1.01,
            low=price * 0.98,
            close=price,
            adjusted_close=price,
            volume=2_000_000.0,
        ))
    return bars


def _quote(symbol: str, price: float = 80.0) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        quote_time="2024-01-24 16:00:00",
        partial_market=True,
        source="Twelve Data",
        freshness="Partial-market reference price; not for trading.",
    )


# ---------------------------------------------------------------------------
# AC-E1 helper: build a ReportResult directly with rich section_index
# ---------------------------------------------------------------------------

def _build_multi_company_report_result() -> ReportResult:
    """Construct a ReportResult containing Business Risks for BABA and NVDA.

    BABA Business Risks:
      item=1: "Regulatory risk: subject to PRC government oversight."
      item=2: "VIE structure risk: contractual arrangements may not be enforceable."
      item=3: "Competition risk: intense competition in Chinese e-commerce."

    NVDA Business Risks:
      item=1: "Supply chain risk: dependency on TSMC for chip fabrication."
      item=2: "Export controls risk: US restrictions on advanced chip exports."
    """
    baba_index = [
        ReportSectionItem(
            owner_company="BABA",
            section="Company Snapshot",
            item=1,
            text="Alibaba Group Holding Limited (BABA) — NYSE ADR.",
        ),
        ReportSectionItem(
            owner_company="BABA",
            section="Business Risks",
            item=1,
            text="Regulatory risk: subject to PRC government oversight.",
        ),
        ReportSectionItem(
            owner_company="BABA",
            section="Business Risks",
            item=2,
            text="VIE structure risk: contractual arrangements may not be enforceable.",
        ),
        ReportSectionItem(
            owner_company="BABA",
            section="Business Risks",
            item=3,
            text="Competition risk: intense competition in Chinese e-commerce.",
        ),
    ]
    nvda_index = [
        ReportSectionItem(
            owner_company="NVDA",
            section="Company Snapshot",
            item=1,
            text="NVIDIA Corporation (NVDA) — NASDAQ common stock.",
        ),
        ReportSectionItem(
            owner_company="NVDA",
            section="Business Risks",
            item=1,
            text="Supply chain risk: dependency on TSMC for chip fabrication.",
        ),
        ReportSectionItem(
            owner_company="NVDA",
            section="Business Risks",
            item=2,
            text="Export controls risk: US restrictions on advanced chip exports.",
        ),
    ]

    return ReportResult(reports=[
        PerStockReport(
            report_id="BABA-test1234",
            title="Alibaba (BABA)",
            symbol="BABA",
            markdown="# BABA Research Report\n...",
            section_index=baba_index,
        ),
        PerStockReport(
            report_id="NVDA-test1234",
            title="NVIDIA (NVDA)",
            symbol="NVDA",
            markdown="# NVDA Research Report\n...",
            section_index=nvda_index,
        ),
    ])


def _lookup(report: ReportResult, owner: str, section: str, item: int) -> ReportSectionItem | None:
    """Locate exactly one section item by (owner_company, section, item).

    Cite now resolves against the OWNING stock's report: the per-stock report
    whose symbol matches ``owner`` carries that stock's section_index. We search
    across every per-stock report so the lookup is robust regardless of ordering.
    """
    matches = [
        entry
        for rep in report.reports
        for entry in rep.section_index
        if entry.owner_company == owner
        and entry.section == section
        and entry.item == item
    ]
    return matches[0] if len(matches) == 1 else None


# ---------------------------------------------------------------------------
# AC-E1: Precise citation — BABA Business Risks item 2
# ---------------------------------------------------------------------------

class TestReportCitationPrecision:
    """AC-E1: section_index lookup must be exact — correct owner + section + item."""

    def setup_method(self):
        self.report = _build_multi_company_report_result()

    def test_baba_business_risks_item2_found(self):
        """AC-E1: can locate BABA / Business Risks / item=2."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None, "BABA Business Risks item 2 not found in section_index"

    def test_baba_business_risks_item2_text_is_correct(self):
        """AC-E1: the text for BABA Business Risks item 2 must be the VIE risk."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None
        assert "VIE" in entry.text, (
            f"Expected VIE risk text, got: {entry.text!r}"
        )

    def test_baba_business_risks_item2_owner_is_baba(self):
        """AC-E1: owner_company of the located entry must be BABA, not another company."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None
        assert entry.owner_company == "BABA"

    def test_baba_business_risks_item2_section_is_correct(self):
        """AC-E1: section must be Business Risks."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None
        assert entry.section == "Business Risks"

    def test_baba_business_risks_item2_item_number_is_2(self):
        """AC-E1: item number must be exactly 2."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None
        assert entry.item == 2

    def test_no_cross_contamination_with_nvda(self):
        """AC-E1: BABA item 2 must NOT return NVDA's Business Risks item 2."""
        baba_entry = _lookup(self.report, "BABA", "Business Risks", 2)
        nvda_entry = _lookup(self.report, "NVDA", "Business Risks", 2)

        assert baba_entry is not None
        assert nvda_entry is not None

        # They must be different items
        assert baba_entry.text != nvda_entry.text, (
            "BABA and NVDA Business Risks item 2 must not have the same text"
        )
        assert baba_entry.owner_company == "BABA"
        assert nvda_entry.owner_company == "NVDA"

    def test_nvda_item2_is_export_controls_not_vie(self):
        """Verify NVDA item 2 is export controls, confirming no cross-contamination."""
        nvda_entry = _lookup(self.report, "NVDA", "Business Risks", 2)
        assert nvda_entry is not None
        assert "export" in nvda_entry.text.lower() or "Export" in nvda_entry.text, (
            f"NVDA Business Risks item 2 should be about export controls, got: {nvda_entry.text!r}"
        )

    def test_baba_item1_is_not_returned_for_item2(self):
        """AC-E1: item=2 lookup must not return item=1."""
        entry = _lookup(self.report, "BABA", "Business Risks", 2)
        assert entry is not None
        assert entry.item == 2
        assert "Regulatory" not in entry.text, (
            "item=1 (Regulatory) text should not appear in item=2 result"
        )


# ---------------------------------------------------------------------------
# AC-C6 / D3: analyze_stocks path must NOT produce a report
# ---------------------------------------------------------------------------

class TestAnalyzeDoesNotProduceReport:
    """AC-C6 / D3: analyze_stocks result is structurally incapable of containing a report."""

    def _run_analyze(self, symbols: list[str]) -> dict:
        import tools
        fake = FakeMarketData(
            bars={s: _bars(s) for s in symbols},
            quotes={s: _quote(s) for s in symbols},
        )
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            return tools.analyze_stocks.invoke(
                {"companies": symbols, "period": "最近30天"}
            )
        finally:
            tools.set_provider(original)

    def test_single_stock_result_has_no_markdown(self):
        """AC-D3: single-stock analyze result must not contain markdown."""
        result = self._run_analyze(["NVDA"])
        assert "markdown" not in result

    def test_single_stock_result_has_no_download_ref(self):
        """AC-D3: single-stock analyze result must not contain download_ref."""
        result = self._run_analyze(["NVDA"])
        assert "download_ref" not in result

    def test_single_stock_result_has_no_section_index(self):
        """AC-D3: single-stock analyze result must not contain section_index."""
        result = self._run_analyze(["NVDA"])
        assert "section_index" not in result

    def test_multi_stock_result_has_no_markdown(self):
        """AC-C6: comparison result must not contain markdown."""
        result = self._run_analyze(["NVDA", "BABA"])
        assert "markdown" not in result

    def test_multi_stock_result_has_no_download_ref(self):
        """AC-C6: comparison result must not contain download_ref."""
        result = self._run_analyze(["NVDA", "BABA"])
        assert "download_ref" not in result

    def test_analyze_result_model_has_no_markdown_field(self):
        """AC-D3 structural invariant: AnalyzeResult schema lacks markdown/download fields."""
        fields = AnalyzeResult.model_fields
        assert "markdown" not in fields
        assert "download_ref" not in fields
        assert "section_index" not in fields

    def test_analyze_result_is_valid_analyze_result(self):
        """analyze_stocks returns a valid AnalyzeResult, not a ReportResult."""
        result = self._run_analyze(["NVDA"])
        ar = AnalyzeResult(**result)
        assert isinstance(ar, AnalyzeResult)
        # The analyze payload carries no report material: even coerced into a
        # ReportResult it yields an EMPTY reports list (no per-stock report,
        # no markdown) — structurally it can never be a report.
        assert "reports" not in result
        coerced = ReportResult(**result)
        assert coerced.reports == []


# ---------------------------------------------------------------------------
# AC-E1 via generate_report: real section_index from build_report
# ---------------------------------------------------------------------------

class TestReportCitationViaGenerateReport:
    """Verify section_index from a real build_report call supports AC-E1 lookup."""

    def setup_method(self):
        import services.report as report_module
        self._orig_provider = report_module._provider
        self._orig_today = report_module._today_override
        report_module._provider = FakeMarketData(
            bars={
                "BABA": _bars("BABA", n=22),
                "NVDA": _bars("NVDA", n=22),
            },
            quotes={
                "BABA": _quote("BABA"),
                "NVDA": _quote("NVDA"),
            },
        )
        report_module._today_override = datetime.date(2024, 1, 24)

    def teardown_method(self):
        import services.report as report_module
        report_module._provider = self._orig_provider
        report_module._today_override = self._orig_today

    @staticmethod
    def _all_index(result):
        """Flatten every per-stock report's section_index into one list."""
        return [e for rep in result.reports for e in rep.section_index]

    def test_section_index_has_baba_entries(self):
        """build_report for BABA + NVDA produces section_index with BABA entries."""
        from services.report import build_report
        result = build_report(["BABA", "NVDA"], "最近一个月")

        baba_entries = [e for e in self._all_index(result) if e.owner_company == "BABA"]
        assert len(baba_entries) > 0, "No section_index entries for BABA"

    def test_section_index_has_nvda_entries(self):
        """build_report for BABA + NVDA produces section_index with NVDA entries."""
        from services.report import build_report
        result = build_report(["BABA", "NVDA"], "最近一个月")

        nvda_entries = [e for e in self._all_index(result) if e.owner_company == "NVDA"]
        assert len(nvda_entries) > 0, "No section_index entries for NVDA"

    def test_section_index_business_risks_baba_item1_locatable(self):
        """AC-E1: Business Risks item 1 for BABA must be locatable in section_index."""
        from services.report import build_report
        result = build_report(["BABA", "NVDA"], "最近一个月")

        baba_br_1 = _lookup(result, "BABA", "Business Risks", 1)
        assert baba_br_1 is not None, "BABA Business Risks item 1 not in section_index"
        assert baba_br_1.owner_company == "BABA"
        assert baba_br_1.section == "Business Risks"
        assert baba_br_1.item == 1

    def test_section_index_no_cross_company_text_bleeding(self):
        """AC-E1: BABA and NVDA entries must not bleed across per-stock reports.

        Each per-stock report's section_index must contain ONLY its own symbol,
        so cite resolves against the right stock's report.
        """
        from services.report import build_report
        result = build_report(["BABA", "NVDA"], "最近一个月")

        owners = {e.owner_company for e in self._all_index(result)}
        assert "BABA" in owners
        assert "NVDA" in owners

        # Per-stock isolation: each report owns exactly one symbol's entries.
        for rep in result.reports:
            rep_owners = {e.owner_company for e in rep.section_index}
            assert rep_owners == {rep.symbol}, (
                f"{rep.symbol} report leaked entries for {rep_owners - {rep.symbol}}"
            )
