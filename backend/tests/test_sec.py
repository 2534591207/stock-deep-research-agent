"""tests/test_sec.py — services/sec.py 验收（**全离线**，FakeFetcher，无真实网络）。

覆盖：
- CIK 由 canned company_tickers 映射**动态**解析（证明非硬编码：未知 ticker → 诚实降级 note）。
- 最近申报从 canned submissions 正确映射（form / filed_date / url）。
- 关键财务从 canned companyfacts 正确提取（确定性，非编造）。
- 小型 10-K HTML 含 "Item 1A. Risk Factors" … 两个加粗风险标题 … "Item 1B." →
  ≥2 个 BusinessRiskItem，title **逐字**取自文档。
- ADR 在映射里无 CIK → FilingHighlights / BusinessRisks 诚实 note（不 raise）。
- fetcher 抛错 → 诚实 note，异常不外泄。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from models import CompanyIdentity
from services import sec
from services.sec import (
    FakeFetcher,
    get_business_risks,
    get_filing_highlights,
    resolve_cik,
)

_FIXTURES = Path(__file__).parent / "fixtures"

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


# ---------------------------------------------------------------------------
# 缓存隔离：每个用例前重置 ticker→CIK 内存缓存。
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cik_cache():
    sec.reset_cache()
    yield
    sec.reset_cache()


# ---------------------------------------------------------------------------
# Canned fixtures（绝不硬编码真实 CIK；这些数值仅存在于测试夹具里）。
# ---------------------------------------------------------------------------
# 注意：故意用与现实不同的 CIK 数值，证明实现是从映射读取而非内置常量。
_FAKE_TICKERS = {
    "0": {"cik_str": 111222, "ticker": "ACME", "title": "Acme Widgets Inc."},
    "1": {"cik_str": 999000, "ticker": "ZETA", "title": "Zeta Corp."},
}

_ACME_CIK10 = "0000111222"


def _submissions(forms_rows: list[dict]) -> dict:
    """构造 submissions.filings.recent 的列向结构。"""
    keys = ("form", "filingDate", "accessionNumber", "primaryDocument", "primaryDocDescription")
    recent = {k: [row.get(k) for row in forms_rows] for k in keys}
    return {"cik": 111222, "filings": {"recent": recent}}


_ACME_FILINGS = [
    {
        "form": "10-K",
        "filingDate": "2026-02-01",
        "accessionNumber": "0000111222-26-000010",
        "primaryDocument": "acme-10k.htm",
        "primaryDocDescription": "Annual report",
    },
    {
        "form": "10-Q",
        "filingDate": "2025-11-01",
        "accessionNumber": "0000111222-25-000040",
        "primaryDocument": "acme-10q.htm",
        "primaryDocDescription": "Quarterly report",
    },
    {
        "form": "8-K",
        "filingDate": "2025-10-15",
        "accessionNumber": "0000111222-25-000038",
        "primaryDocument": "acme-8k.htm",
        "primaryDocDescription": "Current report",
    },
    # 噪声：非关注表单，应被过滤掉。
    {
        "form": "4",
        "filingDate": "2025-10-10",
        "accessionNumber": "0000111222-25-000037",
        "primaryDocument": "form4.xml",
        "primaryDocDescription": "Insider",
    },
]


_ACME_COMPANYFACTS = {
    "cik": 111222,
    "entityName": "Acme Widgets Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"fy": 2024, "fp": "FY", "form": "10-K", "val": 9_000_000, "end": "2024-12-31"},
                        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 12_500_000, "end": "2025-12-31"},
                        # 季度噪声：fp=Q3 不应被选中。
                        {"fy": 2025, "fp": "Q3", "form": "10-Q", "val": 3_100_000, "end": "2025-09-30"},
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 2_200_000, "end": "2025-12-31"},
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "form": "10-K", "val": 40_000_000, "end": "2025-12-31"},
                    ]
                }
            },
        }
    },
}


# 小型 10-K HTML：含目录里的 "Item 1A"（前置）+ 正文章节 + 两个加粗风险标题 + "Item 1B."。
_ACME_10K_HTML = b"""
<html><body>
<p>Table of Contents</p>
<p>Item 1A. Risk Factors .......... 15</p>
<p>Item 1B. Unresolved Staff Comments .......... 30</p>
<hr/>
<p><b>Item 1A. Risk Factors</b></p>
<p>The following risk factors could materially affect our business.</p>
<p><b>Our supply chain depends on a limited number of widget suppliers.</b></p>
<p>If these suppliers fail to deliver, our production could halt and revenue could decline. We may not find timely replacements.</p>
<p><b>Cybersecurity incidents could disrupt our operations and harm our reputation.</b></p>
<p>A breach of our systems could expose customer data and result in significant liability. Remediation costs could be material.</p>
<p>Item 1B. Unresolved Staff Comments</p>
<p>None.</p>
</body></html>
"""


def _acme_fetcher(**overrides: object) -> FakeFetcher:
    """构造覆盖 ACME 全链路的 FakeFetcher；overrides 可替换某个 URL 子串的响应（如注入异常）。"""
    responses: dict[str, object] = {
        COMPANY_TICKERS_URL: _FAKE_TICKERS,
        f"submissions/CIK{_ACME_CIK10}.json": _submissions(_ACME_FILINGS),
        f"companyfacts/CIK{_ACME_CIK10}.json": _ACME_COMPANYFACTS,
        "acme-10k.htm": _ACME_10K_HTML,
    }
    responses.update(overrides)
    return FakeFetcher(responses)


def _acme_identity() -> CompanyIdentity:
    return CompanyIdentity(name="Acme Widgets Inc.", symbol="ACME", exchange="NASDAQ", instrument="common")


def _adr_identity() -> CompanyIdentity:
    # 不在 _FAKE_TICKERS 映射里 → 模拟"无 CIK 匹配的 ADR"。
    return CompanyIdentity(name="Foreign ADR Co.", symbol="FADR", exchange="NYSE", instrument="ADR")


# ===========================================================================
# 1) 动态 CIK 解析（证明非硬编码）
# ===========================================================================
class TestDynamicCikResolution:
    def test_cik_resolved_from_mapping_not_hardcoded(self):
        fetcher = _acme_fetcher()
        # 夹具里 ACME→111222；任何硬编码真实 CIK 都不会等于这个测试值。
        assert resolve_cik("ACME", fetcher=fetcher) == 111222
        assert resolve_cik("ZETA", fetcher=fetcher) == 999000

    def test_cik_case_insensitive(self):
        fetcher = _acme_fetcher()
        assert resolve_cik("acme", fetcher=fetcher) == 111222

    def test_unknown_ticker_returns_none(self):
        """未知 ticker → None（证明不是返回某个内置/猜测的 CIK）。"""
        fetcher = _acme_fetcher()
        assert resolve_cik("NOSUCH", fetcher=fetcher) is None

    def test_cik_cached_in_memory(self):
        """第二次解析不应再次拉取 company_tickers.json（命中内存缓存）。"""
        fetcher = _acme_fetcher()
        resolve_cik("ACME", fetcher=fetcher)
        tickers_calls = sum(1 for u in fetcher.calls if COMPANY_TICKERS_URL in u)
        assert tickers_calls == 1
        resolve_cik("ZETA", fetcher=fetcher)
        tickers_calls = sum(1 for u in fetcher.calls if COMPANY_TICKERS_URL in u)
        assert tickers_calls == 1  # 仍只拉一次


# ===========================================================================
# 2) Filing Highlights
# ===========================================================================
class TestFilingHighlights:
    def test_filings_mapped_from_submissions(self):
        result = get_filing_highlights(_acme_identity(), fetcher=_acme_fetcher())

        assert result.cik == _ACME_CIK10
        assert result.note is None
        # 关注表单：10-K / 10-Q / 8-K（"4" 被过滤）。
        forms = [f.form for f in result.recent_filings]
        assert forms == ["10-K", "10-Q", "8-K"]

        tenk = result.recent_filings[0]
        assert tenk.form == "10-K"
        assert tenk.filed_date == "2026-02-01"
        # url 由 CIK(int) + accession(无横线) + primaryDocument 拼成。
        assert tenk.url == (
            "https://www.sec.gov/Archives/edgar/data/111222/"
            "000011122226000010/acme-10k.htm"
        )
        assert tenk.description == "Annual report"

    def test_key_financials_extracted_from_companyfacts(self):
        result = get_filing_highlights(_acme_identity(), fetcher=_acme_fetcher())

        labels = {f.label: f for f in result.key_financials}
        assert "Revenue" in labels
        assert "Net Income" in labels
        assert "Total Assets" in labels

        rev = labels["Revenue"]
        # 取最新年度（FY2025=12.5M），而非 FY2024 或季度噪声。
        assert rev.value == 12_500_000
        assert rev.period == "FY2025"
        assert rev.unit == "USD"
        assert rev.source_url is not None and "companyfacts" in rev.source_url

        assert labels["Net Income"].value == 2_200_000
        assert labels["Total Assets"].value == 40_000_000

    def test_adr_no_cik_match_honest_note_no_raise(self):
        result = get_filing_highlights(_adr_identity(), fetcher=_acme_fetcher())
        assert result.recent_filings == []
        assert result.key_financials == []
        assert result.note is not None
        assert "FADR" in result.note
        assert "no matching SEC filer" in result.note

    def test_fetcher_raising_degrades_no_exception(self):
        """submissions + companyfacts 都抛错 → 诚实 note，绝不抛出。"""
        fetcher = _acme_fetcher(
            **{
                f"submissions/CIK{_ACME_CIK10}.json": RuntimeError("network down"),
                f"companyfacts/CIK{_ACME_CIK10}.json": RuntimeError("network down"),
            }
        )
        result = get_filing_highlights(_acme_identity(), fetcher=fetcher)
        # CIK 仍解析成功（tickers 正常），但数据抓取失败 → 空列表 + note。
        assert result.cik == _ACME_CIK10
        assert result.recent_filings == []
        assert result.key_financials == []
        assert result.note is not None

    def test_company_tickers_fetch_failure_degrades(self):
        """连 company_tickers 都抓不到 → 当作无 CIK，诚实 note。"""
        fetcher = FakeFetcher({COMPANY_TICKERS_URL: RuntimeError("dns failure")})
        result = get_filing_highlights(_acme_identity(), fetcher=fetcher)
        assert result.note is not None
        assert result.recent_filings == []


# ===========================================================================
# 3) Business Risks（10-K Item 1A 解析）
# ===========================================================================
class TestBusinessRisks:
    def test_item_1a_parsed_verbatim_titles(self):
        result = get_business_risks(_acme_identity(), fetcher=_acme_fetcher())

        assert result.note is None
        assert len(result.items) >= 2

        titles = [it.title for it in result.items]
        # 标题必须**逐字**取自文档（HTML 里的加粗句）。
        assert "Our supply chain depends on a limited number of widget suppliers." in titles
        assert "Cybersecurity incidents could disrupt our operations and harm our reputation." in titles

        # source_form / source_url 正确填充。
        first = result.items[0]
        assert first.source_form == "10-K (filed 2026-02-01)"
        assert first.source_url.endswith("acme-10k.htm")
        # summary 为忠实摘录（来自文档解释段，不编造）。
        supply = next(it for it in result.items if it.title.startswith("Our supply chain"))
        assert supply.summary is not None
        assert "suppliers fail to deliver" in supply.summary

    def test_titles_are_real_document_text(self):
        """反编造：每个 title 必须能在原始 HTML 文本中找到（逐字）。"""
        html_text = _ACME_10K_HTML.decode("utf-8")
        result = get_business_risks(_acme_identity(), fetcher=_acme_fetcher())
        for item in result.items:
            assert item.title in html_text, f"title not verbatim in source: {item.title!r}"

    def test_adr_no_cik_match_honest_note_no_raise(self):
        result = get_business_risks(_adr_identity(), fetcher=_acme_fetcher())
        assert result.items == []
        assert result.note is not None
        assert "FADR" in result.note

    def test_fetcher_raising_on_html_degrades(self):
        """submissions 成功但主文档 HTML 抓取抛错 → 诚实 note + source_url，不抛出。"""
        fetcher = _acme_fetcher(**{"acme-10k.htm": RuntimeError("timeout")})
        result = get_business_risks(_acme_identity(), fetcher=fetcher)
        assert result.items == []
        assert result.note is not None
        assert "see source" in result.note
        # 已知 10-K url → 即便降级也回传 source_url。
        assert result.source_url is not None and result.source_url.endswith("acme-10k.htm")

    def test_section_not_found_degrades(self):
        """HTML 里没有 Item 1A 章节 → 诚实 note，不编造风险。"""
        empty_html = b"<html><body><p>Nothing relevant here at all.</p></body></html>"
        fetcher = _acme_fetcher(**{"acme-10k.htm": empty_html})
        result = get_business_risks(_acme_identity(), fetcher=fetcher)
        assert result.items == []
        assert result.note is not None

    def test_submissions_fetch_failure_degrades(self):
        fetcher = _acme_fetcher(
            **{f"submissions/CIK{_ACME_CIK10}.json": RuntimeError("network down")}
        )
        result = get_business_risks(_acme_identity(), fetcher=fetcher)
        assert result.items == []
        assert result.note is not None


# ===========================================================================
# 4) FakeFetcher 自身契约
# ===========================================================================
class TestFakeFetcher:
    def test_json_payload_returned_as_bytes(self):
        fake = FakeFetcher({COMPANY_TICKERS_URL: _FAKE_TICKERS})
        raw = fake(COMPANY_TICKERS_URL)
        assert isinstance(raw, bytes)
        assert json.loads(raw)["0"]["ticker"] == "ACME"

    def test_exception_instance_raises(self):
        fake = FakeFetcher({"x": ValueError("boom")})
        with pytest.raises(ValueError):
            fake("x")

    def test_unknown_url_raises(self):
        fake = FakeFetcher({})
        with pytest.raises(RuntimeError):
            fake("https://unknown")


# ===========================================================================
# 5) 回归：真实 10-K Item 1A 抽取（修复「封面样板被当成风险」live-run bug）
# ===========================================================================
# 背景：真实 NVDA 10-K 里 "Item 1A. Risk Factors" 出现多次（目录 + 正文 + 多处
# “See …”交叉引用）。旧实现取「最后一次命中」→ 落到正文末尾交叉引用，窗口越过整章，
# 把**封面文本**（“For the fiscal year ended …”/“Registrant’s telephone number …”）
# 当成风险标题输出。下列回归用真实申报的精简切片（tests/fixtures/）锁定修复：
#   - 真实 Item 1A 切片 → 抽到真实风险句（逐字、以句末标点收尾），且**绝无**封面样板。
#   - 仅含封面加粗文本的切片 → 诚实 note（空 items），绝不编造。

# 真实 NVDA 10-K Item 1A 区域应出现的逐字风险标题（取自切片，逐字断言）。
_NVDA_REAL_TITLES = (
    "Failure to meet the evolving needs of our industry and markets may adversely impact our financial results.",
    "Competition could adversely impact our market share and financial results.",
    "Adverse economic conditions may harm our business.",
    "Climate change may have a long-term impact on our business.",
)

# 封面/样板片段：**绝不**应作为风险标题出现（这正是 live-run 复现的 bug）。
_COVER_PAGE_GARBAGE = (
    "For the fiscal year ended",
    "telephone number, including area code",
    "Registrant",
    "Commission File",
    "Securities registered",
)


def _read_fixture(name: str) -> bytes:
    return (_FIXTURES / name).read_bytes()


def _nvda_identity() -> CompanyIdentity:
    return CompanyIdentity(name="NVIDIA Corp", symbol="NVDA", exchange="NASDAQ", instrument="common")


def _risk_fetcher(primary_doc: str, html: bytes) -> FakeFetcher:
    """构造覆盖 NVDA 风险链路的 FakeFetcher（CIK 仍动态解析，数值仅存于夹具，非硬编码）。"""
    cik10 = _ACME_CIK10  # 复用任意夹具 CIK（值与现实不同，证明非硬编码）。
    tickers = {"0": {"cik_str": int(cik10), "ticker": "NVDA", "title": "NVIDIA Corp"}}
    rows = [
        {
            "form": "10-K",
            "filingDate": "2026-04-01",
            "accessionNumber": "0000111222-26-000099",
            "primaryDocument": primary_doc,
            "primaryDocDescription": "Annual report",
        }
    ]
    return FakeFetcher(
        {
            COMPANY_TICKERS_URL: tickers,
            f"submissions/CIK{cik10}.json": _submissions(rows),
            primary_doc: html,
        }
    )


class TestRealFilingRiskExtraction:
    def test_nvda_item1a_excerpt_yields_real_titles_not_cover_page(self):
        """真实 NVDA 10-K Item 1A 切片 → 真实风险句；绝无封面样板（核心回归）。"""
        html = _read_fixture("nvda_10k_item1a_excerpt.htm")
        result = get_business_risks(_nvda_identity(), fetcher=_risk_fetcher("nvda-10k.htm", html))

        assert result.note is None
        assert len(result.items) >= 4
        titles = [it.title for it in result.items]

        # 1) 逐字真实风险标题在抽取结果里。
        for expected in _NVDA_REAL_TITLES:
            assert expected in titles, f"missing real risk title: {expected!r}"

        # 2) 封面样板**绝不**出现（这是 live-run bug 的硬红线）。
        joined = " ".join(titles)
        for garbage in _COVER_PAGE_GARBAGE:
            assert garbage not in joined, f"cover-page garbage leaked as risk title: {garbage!r}"

        # 3) 每条标题都是「完整句子」（以句末标点收尾）——封面碎片不会满足。
        for t in titles:
            assert t.rstrip()[-1] in ".!?", f"title is not a full risk sentence: {t!r}"

        # 4) 逐字性：标题必须能在原始 HTML 文本中找到。
        html_text = html.decode("utf-8")
        for t in titles:
            assert t in html_text, f"title not verbatim in source: {t!r}"

        # source 元数据正确填充。
        assert result.items[0].source_form == "10-K (filed 2026-04-01)"
        assert result.items[0].source_url.endswith("nvda-10k.htm")

    def test_cover_page_bold_only_returns_honest_note(self):
        """仅含封面加粗文本（无真实风险句）→ 诚实 note，空 items，绝不编造。"""
        html = _read_fixture("cover_page_only_10k.htm")
        result = get_business_risks(_nvda_identity(), fetcher=_risk_fetcher("nvda-10k.htm", html))

        assert result.items == []
        assert result.note is not None
        assert "see source" in result.note
        # 即便降级，也回传 source_url（指向真实申报）。
        assert result.source_url is not None and result.source_url.endswith("nvda-10k.htm")

    def test_extractor_handles_repeated_item1a_anchors(self):
        """直接对切片调用底层抽取：多处 Item 1A 锚点下仍只取真正小节，标题数受上限约束。"""
        from services.sec import (  # 局部导入：仅此回归需要触达内部抽取器。
            _ITEM_1A_RE,
            _NEXT_ITEM_10K_RE,
            _MAX_RISK_ITEMS,
            _extract_risk_items_from_html,
        )

        html = _read_fixture("nvda_10k_item1a_excerpt.htm").decode("utf-8")
        items = _extract_risk_items_from_html(html, _ITEM_1A_RE, _NEXT_ITEM_10K_RE)
        assert 1 <= len(items) <= _MAX_RISK_ITEMS
        # 至少一条带忠实简述（取自文档解释段，逐字截断、不改写）。
        assert any(summary for _, summary in items)
