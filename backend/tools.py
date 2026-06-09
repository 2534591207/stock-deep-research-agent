"""tools.py — LangChain @tool wrappers for the two-layer agent.

T3.2: analyze_stocks
  - Thin orchestration: time_range → resolver → market_data → metrics → risk → compare
  - No financial formulas here; all numbers computed in services/
  - Market data provider is injectable (_PROVIDER) for offline testing

Invariants:
  - AnalyzeResult has no markdown/download fields (structural guarantee)
  - >MAX_STOCKS input → take first MAX_STOCKS + warnings (AC-H2)
  - resolver none → status="unrecognized" (AC-H6)
  - resolver ambiguous → status="unrecognized" + note with candidates (AC-H4)
  - get_bars raises → status="data_failed" isolated, others continue (AC-F2)
  - Quote.partial_market=True always (AC-F3)
"""
from __future__ import annotations

import datetime
from typing import Any

from langchain_core.tools import tool

from config import DOC_MAX_INDEX_CHARS, DOC_TOP_K, MAX_STOCKS
from models import (
    AnalyzeResult,
    Risk,
    StockAnalysis,
)
from services import compare, metrics, resolver, risk, time_range


# ---------------------------------------------------------------------------
# Injectable market-data provider
# ---------------------------------------------------------------------------

class _RealProvider:
    """Thin wrapper around the real market_data functions."""

    def get_bars(self, symbol: str, start: datetime.date, end: datetime.date):
        from services.market_data import get_bars
        return get_bars(symbol, start, end)

    def get_quote(self, symbol: str):
        from services.market_data import get_quote
        return get_quote(symbol)


_PROVIDER: Any = _RealProvider()


def set_provider(provider: Any) -> None:
    """Replace the module-level provider (for testing)."""
    global _PROVIDER
    _PROVIDER = provider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_risk(m: "metrics.Metrics") -> Risk:  # type: ignore[name-defined]
    """Assemble a Risk object from computed Metrics using services/risk."""
    vs = risk.vol_score(m.daily_volatility)
    ds = risk.drawdown_score(m.max_drawdown)
    rs = risk.risk_score(m.daily_volatility, m.max_drawdown)
    level = risk.absolute_level(
        m.daily_volatility,
        m.max_drawdown,
        m.effective_trading_days,
        m.data_coverage,
    )
    view = risk.short_term_market_view(
        level,
        m.period_return,
        m.expected_trading_days,
        m.effective_trading_days,
        m.data_coverage,
    )
    rt = risk.return_threshold(m.expected_trading_days)
    return Risk(
        vol_score=vs,
        drawdown_score=ds,
        risk_score=rs,
        absolute_level=level,  # type: ignore[arg-type]
        short_term_market_view=view,  # type: ignore[arg-type]
        return_threshold=rt,
    )


def _trading_days_in_range(start: datetime.date, end: datetime.date) -> int:
    """Approximate expected trading days in a calendar range (5/7 rule)."""
    total_days = (end - start).days + 1
    return max(1, round(total_days * 5 / 7))


# ---------------------------------------------------------------------------
# analyze_stocks tool
# ---------------------------------------------------------------------------

@tool
def analyze_stocks(companies: list[str], period: str) -> dict:
    """Identify 1–3 US-listed stocks, fetch historical bars, compute metrics/risk,
    and rank them by risk score when multiple stocks are provided.

    Args:
        companies: List of company names or ticker symbols (e.g. ["AAPL", "阿里巴巴"]).
                   More than MAX_STOCKS entries are truncated to the first MAX_STOCKS.
        period: Natural-language time range (e.g. "最近三个月", "最近一年").
                Defaults to last 30 days when empty or unparseable.

    Returns:
        AnalyzeResult serialised as dict. Never contains markdown or report fields.
    """
    warnings: list[str] = []

    # ── AC-H2: truncate to MAX_STOCKS ────────────────────────────────────────
    if len(companies) > MAX_STOCKS:
        deferred = companies[MAX_STOCKS:]
        companies = companies[:MAX_STOCKS]
        warnings.append(
            f"超过最多 {MAX_STOCKS} 只限制，以下标的已推迟（deferred）："
            f" {', '.join(deferred)}"
        )

    # ── Parse time range (AC-H3 default 30 days) ────────────────────────────
    today = datetime.date.today()
    tr = time_range.parse_period(period, today)
    start: datetime.date = tr["start"]
    end: datetime.date = tr["end"]
    expected_days = _trading_days_in_range(start, end)

    # ── Process each stock ───────────────────────────────────────────────────
    stock_analyses: list[StockAnalysis] = []

    for company in companies:
        # Resolve identity
        resolve_result = resolver.resolve(company)

        if resolve_result.status == "none":
            # AC-H6: not found → unrecognized, no encoding
            stock_analyses.append(
                StockAnalysis(
                    status="unrecognized",
                    note=f"未能识别「{company}」为美股上市标的。",
                )
            )
            continue

        if resolve_result.status == "ambiguous":
            # AC-H4: ambiguous → unrecognized + candidates note
            candidates_str = ", ".join(resolve_result.candidates or [])
            stock_analyses.append(
                StockAnalysis(
                    status="unrecognized",
                    note=(
                        f"「{company}」匹配到多个候选标的，请澄清：{candidates_str}。"
                        f"（候选：{candidates_str}）"
                    ),
                )
            )
            continue

        # status == "found"
        identity = resolve_result.identity
        symbol = identity.symbol  # type: ignore[union-attr]

        # Fetch bars — AC-F2: failure → isolate this stock
        try:
            bars = _PROVIDER.get_bars(symbol, start, end)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} 行情数据获取失败，已跳过：{exc}")
            stock_analyses.append(
                StockAnalysis(
                    identity=identity,
                    status="data_failed",
                    note=f"行情数据获取失败：{exc}",
                )
            )
            continue

        # Fetch current quote — AC-F3: partial_market=True
        try:
            quote = _PROVIDER.get_quote(symbol)
        except Exception as exc:  # noqa: BLE001
            # Quote failure is non-fatal; continue without quote
            warnings.append(f"{symbol} 当前报价获取失败（非致命）：{exc}")
            quote = None

        # Compute metrics
        m = metrics.compute_metrics(bars, expected_days)

        # Compute risk
        r = _build_risk(m)

        stock_analyses.append(
            StockAnalysis(
                identity=identity,
                metrics=m,
                risk=r,
                quote=quote,
                status="ok",
                data_as_of=bars[-1].date,  # 数据截至最近已完成交易日（来源 Yahoo Finance，延迟/非实时）
            )
        )

    # ── Ranking (AC-C1, AC-C3) ───────────────────────────────────────────────
    ranking = compare.rank(stock_analyses)

    return AnalyzeResult(
        stocks=stock_analyses,
        ranking=ranking,
        warnings=warnings,
    ).model_dump()


# ---------------------------------------------------------------------------
# generate_report tool
# ---------------------------------------------------------------------------

@tool
def generate_report(companies: list[str], period: str) -> dict:
    """Generate a 9-section English research report for the given companies and period.

    Only call this tool when the user explicitly asks for a report.
    Do NOT call this for analysis or comparison — use analyze_stocks instead.

    Args:
        companies: List of company names or ticker symbols (1–3).
        period:    Natural-language time period (e.g. "最近一个月", "最近三个月").

    Returns:
        dict with key ``reports``: an ordered list of per-stock reports, each
        carrying report_id, title, symbol, markdown, and section_index.
    """
    import services.report as _report_module
    result = _report_module.build_report(companies, period)
    return result.model_dump()


# ---------------------------------------------------------------------------
# analyze_document tool (NEW — RAG-lite over the session's uploaded financial file)
# ---------------------------------------------------------------------------

# Injectable embedder / llm (mirrors _PROVIDER). None → real OpenAI defaults via
# services.document; tests inject deterministic fakes for offline runs.
_DOC_EMBEDDER: Any = None
_DOC_LLM: Any = None


def set_doc_embedder(embedder: Any) -> None:
    """Replace the module-level document embedder (for testing)."""
    global _DOC_EMBEDDER
    _DOC_EMBEDDER = embedder


def set_doc_llm(llm: Any) -> None:
    """Replace the module-level document summarizer LLM (for testing)."""
    global _DOC_LLM
    _DOC_LLM = llm


# ---------------------------------------------------------------------------
# find_news tool (NEW — standalone in-conversation news/events lookup)
# ---------------------------------------------------------------------------

# Injectable Tavily news client (mirrors _PROVIDER). None → real
# services.news.TavilyNewsClient via collect_event_evidence's own default;
# tests inject a fake client for offline runs.
_NEWS_CLIENT: Any = None


def set_news_client(client: Any) -> None:
    """Replace the module-level news client (for testing)."""
    global _NEWS_CLIENT
    _NEWS_CLIENT = client


@tool
def find_news(company: str, period: str = "近三个月") -> dict:
    """Look up a single US stock's recent news/events around its significant price
    moves — a lightweight in-conversation lookup, WITHOUT generating a report.

    Call this when the user asks about a stock's news / events / 利好 / 利空 /
    "最近有什么消息" for ONE company. It detects the stock's significant single-day
    moves over the period and finds time-adjacent news for each (honest, non-causal:
    news MAY be related; never asserts causation). For a downloadable report use
    generate_report instead; for price/risk metrics use analyze_stocks.

    Args:
        company: A single company name or ticker symbol (e.g. "英伟达" / "NVDA").
        period:  Natural-language time period (e.g. "近三个月"). Defaults to 近三个月.

    Returns:
        dict: {"status": "ok"|"unrecognized", "identity": {...}, "period": str,
        "events": [{date, direction, pct_move, title, url, source, published_date,
        explanation, attribution_confidence}], "note": str}. Events degrade to an
        empty list with an honest note when no news source is available; numbers
        come from services code, never invented.
    """
    from services import news as news_svc
    from services.progress import emit_stage

    today = datetime.date.today()
    tr = time_range.parse_period(period, today)
    start: datetime.date = tr["start"]
    end: datetime.date = tr["end"]
    period_label = tr.get("label") or period
    expected_days = _trading_days_in_range(start, end)

    # ── Stage: identify ──────────────────────────────────────────────────────
    # Resolve FIRST so that ALL stage events (identify, market_data, events)
    # share the same resolved ticker key → exactly ONE progress track.
    # Only for unrecognized companies (no ticker) do we key events by the raw query.
    resolve_result = resolver.resolve(company)
    if resolve_result.status != "found" or resolve_result.identity is None:
        emit_stage(company, "identify", "start")
        emit_stage(company, "identify", "error")
        if resolve_result.status == "ambiguous":
            candidates_str = ", ".join(resolve_result.candidates or [])
            note = f"「{company}」匹配到多个候选标的，请澄清：{candidates_str}。"
        else:
            note = f"未能识别「{company}」为美股上市标的。"
        return {"status": "unrecognized", "note": note}

    identity = resolve_result.identity
    symbol = identity.symbol
    emit_stage(symbol, "identify", "start")
    emit_stage(symbol, "identify", "done")

    identity_dict = {
        "name": identity.name,
        "symbol": symbol,
        "exchange": identity.exchange,
    }

    # ── Stage: market_data ───────────────────────────────────────────────────
    emit_stage(symbol, "market_data", "start")
    try:
        bars = _PROVIDER.get_bars(symbol, start, end)
    except Exception as exc:  # noqa: BLE001 — degrade honestly, never fabricate
        emit_stage(symbol, "market_data", "error")
        return {
            "status": "ok",
            "identity": identity_dict,
            "period": period_label,
            "events": [],
            "note": f"行情数据获取失败，无法定位重大波动：{exc}",
        }
    emit_stage(symbol, "market_data", "done")

    # Compute significant moves via the SAME services code reports use.
    m = metrics.compute_metrics(bars, expected_days)
    significant_moves = m.significant_moves

    # ── Stage: events ────────────────────────────────────────────────────────
    emit_stage(symbol, "events", "start")
    try:
        evidence = news_svc.collect_event_evidence(
            identity,
            significant_moves,
            client=_NEWS_CLIENT,
            max_events=3,
        )
    except Exception:  # noqa: BLE001 — never propagate
        evidence = []
    emit_stage(symbol, "events", "done")

    events: list[dict] = []
    for ev in evidence:
        top = ev.news[0] if ev.news else None
        events.append(
            {
                "date": ev.date,
                "direction": ev.direction,
                "pct_move": ev.pct_move,
                "title": top.title if top else None,
                "url": top.url if top else None,
                "source": top.source if top else None,
                "published_date": top.published_date if top else None,
                # Descriptive only — never causal.
                "explanation": (top.explanation if top else None) or ev.note,
                # collect_event_evidence never returns High; default Low when absent.
                "attribution_confidence": ev.attribution_confidence or "Low",
            }
        )

    if not significant_moves:
        note = f"{period_label}内未检测到显著单日波动，因此无相关事件可检索。"
    elif not any(e["title"] for e in events):
        note = "未找到可靠新闻证据 / 事件检索不可用；不对涨跌原因做任何断言。"
    else:
        note = (
            "以下新闻在时间上与重大波动接近，可能相关、可能是因素之一，"
            "但绝不构成因果断言；证据不足处不臆测原因。"
        )

    return {
        "status": "ok",
        "identity": identity_dict,
        "period": period_label,
        "events": events,
        "note": note,
    }


@tool
def analyze_document(question: str) -> dict:
    """Read the financial report file the user uploaded THIS session and answer
    strictly from its text. Call this when the session has an uploaded document and
    the user asks about that file / financial report.

    This does NOT compute stock price metrics — for stock quotes / risk metrics use
    analyze_stocks instead. It performs grounded text retrieval + a brief qualitative
    summary over the uploaded document only; it never fabricates content.

    Args:
        question: The user's question about the uploaded document.

    Returns:
        dict: {"status": "ok", "summary": str, "excerpts": [{"text", "locator"}]}
        grounded on the session's document; or {"status": "no_document"} when no
        document has been uploaded for the current session.
    """
    from services import document as _doc
    from services import doc_store as _store
    from services.progress import emit_stage

    track = "__doc__"

    # doc_load — locate the session's uploaded document.
    emit_stage(track, "doc_load", "start")
    doc = _store.get_current_document()
    if doc is None:
        emit_stage(track, "doc_load", "done")
        return {"status": "no_document"}
    emit_stage(track, "doc_load", "done")

    # doc_parse — the embedding index is now built AT UPLOAD time, so this is a
    # near-instant no-op when embeddings are already present. It stays as a SAFETY
    # NET: rebuilds only if the index is somehow missing (e.g. a question arrived
    # before upload-time indexing finished). Cached back onto the stored doc.
    emit_stage(track, "doc_parse", "start")
    _doc.ensure_index(doc, embedder=_DOC_EMBEDDER)
    emit_stage(track, "doc_parse", "done")

    # doc_locate — embed the query + retrieve the most relevant excerpts.
    emit_stage(track, "doc_locate", "start")
    excerpts = _doc.retrieve(question, doc, k=DOC_TOP_K, embedder=_DOC_EMBEDDER)
    emit_stage(track, "doc_locate", "done")

    # doc_summarize — grounded brief overview over the retrieved excerpts.
    emit_stage(track, "doc_summarize", "start")
    summary = _doc.summarize(doc, excerpts, llm=_DOC_LLM)
    emit_stage(track, "doc_summarize", "done")

    result: dict = {
        "status": "ok",
        "summary": summary,
        "excerpts": [{"text": e.text, "locator": e.locator} for e in excerpts],
    }
    if doc.index_truncated:
        indexed_chars = len("".join(doc.chunks))  # approximate indexed volume
        result["truncation_note"] = (
            f"本文件较大，仅索引了前约 {DOC_MAX_INDEX_CHARS // 10000} 万字用于检索；"
            "文件后段（财务报表附表等）未参与向量检索，相关问题可能无法覆盖。"
        )
    return result
