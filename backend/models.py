"""结构化数据模型（pydantic v2）。

关键不变量：`AnalyzeResult` **刻意不含 markdown / 下载字段** —— 顶层 `analyze_stocks`
永不出报告（结构上不可能），报告只由 `generate_report` → `ReportResult` 产出。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class Bar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float


class Quote(BaseModel):
    symbol: str
    price: float
    quote_time: str
    partial_market: bool = True
    source: str = "Yahoo Finance"
    freshness: str = "Partial-market reference price; not for trading."


class CompanyIdentity(BaseModel):
    name: str
    symbol: str
    exchange: str
    instrument: Literal["common", "ADR"]
    market: str = "US"
    cik: Optional[str] = None


class ResolveResult(BaseModel):
    status: Literal["found", "none", "ambiguous"]
    identity: Optional[CompanyIdentity] = None
    candidates: Optional[list[str]] = None
    query: str = ""


class Metrics(BaseModel):
    period_return: float
    daily_volatility: float
    annualized_volatility: float
    negative_day_volatility: Optional[float] = None
    negative_day_volatility_reason: Optional[str] = None
    max_drawdown: float                 # signed, <= 0
    max_single_day_move: float          # signed
    max_single_day_significant: bool
    up_days: int
    down_days: int
    data_coverage: float
    effective_trading_days: int
    expected_trading_days: int
    normalized_series: list[float]
    normalized_base_date: str
    calculation_basis: str = "Price Return"   # split-adjusted only（无含息复权）
    significant_moves: list["SignificantMove"] = []   # 所有 |日收益| ≥ SIGNIFICANT_MOVE_MIN_PCT 的交易日（确定性计算）


class Risk(BaseModel):
    vol_score: float
    drawdown_score: float
    risk_score: float                   # 仅用于组内相对排序
    absolute_level: Literal["Low", "Medium", "High", "Undetermined"]
    short_term_market_view: Literal["Positive", "Neutral", "Cautious", "Insufficient data"]
    return_threshold: float
    caveat: str = "Observed Market Risk reflects recent price behavior only; not the company's overall investment risk."


class StockAnalysis(BaseModel):
    identity: Optional[CompanyIdentity] = None
    metrics: Optional[Metrics] = None
    risk: Optional[Risk] = None
    quote: Optional[Quote] = None
    status: Literal["ok", "unrecognized", "data_failed"] = "ok"
    note: Optional[str] = None          # 未识别 / 失败 / 需澄清 说明
    source: str = "Yahoo Finance"       # 数据来源
    data_as_of: Optional[str] = None    # 走势/指标数据截至日期（最近已完成交易日）；当前价为延迟报价
    # —— bonus 充实（仅 generate_report 会填；analyze 默认空，保持轻量）——
    events: list["EventEvidence"] = []              # 异动新闻证据（Related Events）
    filings: Optional["FilingHighlights"] = None    # SEC 申报/财务亮点
    business_risks: Optional["BusinessRisks"] = None  # SEC 10-K/20-F 经营风险


class RankingItem(BaseModel):
    symbol: str
    rank: int
    risk_score: float


class RankingResult(BaseModel):
    items: list[RankingItem]
    excluded: list[str] = []            # Undetermined 被排除的标的
    caveat: str = "Relative ranking is limited to the selected stocks and this analysis period only."


class AnalyzeResult(BaseModel):
    """analyze_stocks 的返回。**无 markdown / 下载字段** —— 永不出报告。"""
    stocks: list[StockAnalysis]
    ranking: Optional[RankingResult] = None
    warnings: list[str] = []


class ReportSectionItem(BaseModel):
    owner_company: str                  # e.g. "BABA"
    section: str                        # e.g. "Business Risks"
    item: int                           # e.g. 2
    text: str
    source: Optional[str] = None


class PerStockReport(BaseModel):
    """A self-contained, per-stock research report.

    Each stock generated in a turn gets its OWN full 9-section Markdown document,
    its own chart, its own verbatim disclaimer, and its own section_index (so the
    cite flow resolves owner_company/section/item against the right stock).

    report_id is stable/unique per (session, stock, generation), e.g.
    "NVDA-ab12cd34".
    """
    report_id: str
    title: str
    symbol: str
    markdown: str
    section_index: list[ReportSectionItem] = []


class ReportResult(BaseModel):
    """Result of generate_report: an ORDERED LIST of per-stock reports.

    One self-contained report document per stock requested this turn.
    """
    reports: list[PerStockReport] = []


# ===== Bonus 充实模型：Related Events / SEC Filing Highlights / Business Risks =====
# 共享数据契约。诚实红线：新闻只列"时间相近、可能相关"的报道，绝不断言因果；
# 财务数字来自 SEC XBRL（确定性）；经营风险逐字/忠实摘要自真实申报，绝不编造；
# 任一外部源不可用 → 该节如实降级（note 说明），绝不阻塞核心行情分析。

class SignificantMove(BaseModel):
    date: str
    pct_move: float                      # 带符号日收益
    direction: Literal["up", "down"]


class NewsItem(BaseModel):
    title: str
    url: str
    source: Optional[str] = None         # 发布方 / 域名
    published_date: Optional[str] = None
    snippet: Optional[str] = None        # 文章摘录
    explanation: Optional[str] = None    # 一句话：这篇报道讲什么（**不是**因果论断）


class EventEvidence(BaseModel):
    """围绕一次显著异动收集的新闻证据。绝不断言"新闻导致涨跌"。"""
    date: str                            # 显著异动交易日
    pct_move: float
    direction: Literal["up", "down"]
    attribution_confidence: Literal["High", "Medium", "Low"] = "Low"
    news: list[NewsItem] = []
    note: Optional[str] = None           # 诚实说明，如 "No reliable news evidence found."


class FinancialFact(BaseModel):
    label: str                           # 如 "Revenue" / "Net Income"
    value: float
    unit: str = "USD"
    period: Optional[str] = None         # 财年/期间，如 "FY2025"
    source_url: Optional[str] = None


class FilingHighlight(BaseModel):
    form: str                            # 如 "10-K" / "10-Q" / "20-F"
    filed_date: str
    url: str
    description: Optional[str] = None


class FilingHighlights(BaseModel):
    cik: Optional[str] = None
    recent_filings: list[FilingHighlight] = []
    key_financials: list[FinancialFact] = []
    note: Optional[str] = None           # SEC 不可用时的降级说明


class BusinessRiskItem(BaseModel):
    title: str                           # 风险因素标题（**逐字**取自申报）
    summary: Optional[str] = None        # 忠实简述/摘录（不编造）
    source_form: Optional[str] = None    # 如 "10-K (FY2025)"
    source_url: Optional[str] = None


class BusinessRisks(BaseModel):
    items: list[BusinessRiskItem] = []
    source_form: Optional[str] = None
    source_url: Optional[str] = None
    note: Optional[str] = None           # 降级说明（如 ADR 报 20-F / 无 CIK / 抓取失败）


# 解析上面被前置引用（forward ref）的 bonus 模型
Metrics.model_rebuild()
StockAnalysis.model_rebuild()
