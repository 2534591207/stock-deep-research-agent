"""services/report.py — Report generation orchestration (T4.1).

build_report(companies, period, provider, *, today=None) -> ReportResult

Each requested stock gets its OWN self-contained 9-section report document
(own chart, own verbatim disclaimer, own section_index). The result is an
ORDERED LIST of PerStockReport (one entry per stock).

Orchestration:
  1. Parse period via time_range.parse_period
  2. For each company: resolver → market_data → metrics → risk
  3. compare.rank for relative ranking (each report's §3 line names the batch)
  4. Assemble a SEPARATE 9-section English Markdown document per company
  5. Render normalized price chart with matplotlib (Agg); upload to the GitHub
     image host when configured (embed the raw URL) else embed /reports/<file>.png
  6. Append verbatim disclaimer to each per-stock document
  7. Build a per-stock section_index (list[ReportSectionItem])
  8. Return ReportResult{reports=[PerStockReport{report_id,title,symbol,
     markdown,section_index}, ...]}

Provider injection:
  Module-level _provider (default None → real market_data functions).
  Tests set _provider = FakeMarketData(...) and optionally _today_override = date(...).
"""
from __future__ import annotations

import datetime
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from jinja2 import Template

from config import TRADING_DAYS_PER_YEAR
from models import (
    CompanyIdentity,
    Metrics,
    PerStockReport,
    ReportResult,
    ReportSectionItem,
    Risk,
    StockAnalysis,
)
from services import (
    compare,
    image_host,
    metrics as metrics_svc,
    news as news_svc,
    risk as risk_svc,
    sec as sec_svc,
    time_range,
)
from services.progress import emit_stage
from services.resolver import resolve

# ---------------------------------------------------------------------------
# Module-level provider injection (for testing)
# ---------------------------------------------------------------------------

_provider: Any = None          # None → use real market_data module
_today_override: Optional[datetime.date] = None
_news_collector: Any = None    # None → real news.collect_event_evidence(...); tests inject a fake
_sec_provider: Any = None      # None → real services.sec module; tests inject a fake

# ---------------------------------------------------------------------------
# Verbatim disclaimer (spec §5.D / PRD §9 — must not be paraphrased)
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
# Report output directory
# ---------------------------------------------------------------------------

_REPORTS_DIR = Path(__file__).resolve().parent.parent / "_reports"

# ---------------------------------------------------------------------------
# Jinja2 section template (one company)
# ---------------------------------------------------------------------------

_SECTION_TEMPLATE = Template("""\
# {{ company.symbol }} — {{ company.name }}

## Company Snapshot

| Field | Value |
|---|---|
| **Company** | {{ company.name }} |
| **Symbol** | {{ company.symbol }} |
| **Exchange** | {{ company.exchange }} |
| **Instrument** | {{ company.instrument }} |
| **Market** | {{ company.market }} |
| **Analysis Period** | {{ company.period_label }} |
| **Data Coverage** | {{ company.data_coverage_pct }}% ({{ company.effective_days }}/{{ company.expected_days }} trading days) |
| **Calculation Basis** | Price Return (split-adjusted close prices) |

## Price Trend

**Observation period**: {{ company.period_label }}

**Normalized price series (base = 100)**:

{{ company.norm_table }}
{% if company.chart_ref %}
![Price Trend Chart]({{ company.chart_ref }})
{% endif %}
| Metric | Value |
|---|---|
| **Period Return** | {{ company.period_return_pct }}% |
| **Period High (adj. close)** | {{ company.period_high }} |
| **Period Low (adj. close)** | {{ company.period_low }} |
| **Up Days** | {{ company.up_days }} |
| **Down Days** | {{ company.down_days }} |

## Observed Market Risk

| Metric | Value |
|---|---|
| **Annualized Volatility** | {{ company.annualized_vol_pct }}% |
| **Daily Volatility** | {{ company.daily_vol_pct }}% |
| **Negative-Day Volatility** | {{ company.neg_vol_str }} |
| **Max Drawdown** | {{ company.max_drawdown_pct }}% |
| **Max Single-Day Move** | {{ company.max_single_day_pct }}% {% if company.max_single_day_significant %}(significant){% else %}(no significant move){% endif %} |
| **Risk Score** | {{ company.risk_score }} |
| **Absolute Risk Level** | {{ company.absolute_level }} |
| **Relative Rank** | {{ company.relative_rank }} |
| **Data Coverage** | {{ company.data_coverage_pct }}% |
| **Observation Period** | {{ company.period_label }} |

> *{{ company.risk_caveat }}*

## Significant Move

{% if company.max_single_day_significant %}
The largest single-day move in this period was **{{ company.max_single_day_pct }}%**
on {{ company.max_single_day_date }}.
This exceeds the ±2% significance threshold.
{% else %}
No single-day move exceeded the ±2% significance threshold during this period.
{% endif %}

## Related Events

{% if company.events %}
> *News below is from around each significant move and MAY be related; temporal correlation does not prove causation — moves are not attributed to any cause.*
{% for ev in company.events %}
**{{ ev.date }} · {{ ev.pct }}% ({{ ev.direction }})** — Attribution confidence: {{ ev.confidence }}
{% if ev.news %}{% for n in ev.news %}
- [{{ n.title }}]({{ n.url }}){% if n.source %} — {{ n.source }}{% endif %}{% if n.published_date %} ({{ n.published_date }}){% endif %}{% if n.explanation %} — {{ n.explanation }}{% endif %}
{% endfor %}{% else %}
- _{{ ev.note }}_
{% endif %}
{% endfor %}
{% else %}
No significant single-day moves (±2%) in this period to attribute.
{% endif %}

## Financial & Filing Highlights

{% if company.filings.recent_filings or company.filings.key_financials %}
{% if company.filings.recent_filings %}**Recent SEC filings**

| Form | Filed | Link |
|---|---|---|
{% for f in company.filings.recent_filings %}| {{ f.form }} | {{ f.filed_date }} | [link]({{ f.url }}) |
{% endfor %}
{% endif %}{% if company.filings.key_financials %}**Key financials** (from SEC XBRL)

| Metric | Value | Period | Source |
|---|---|---|---|
{% for kf in company.filings.key_financials %}| {{ kf.label }} | {{ kf.value_fmt }} {{ kf.unit }} | {{ kf.period }} | [SEC]({{ kf.source_url }}) |
{% endfor %}
{% endif %}{% else %}
_{{ company.filings.note }}_
{% endif %}

## Business Risks

{% if company.brisks['items'] %}
_Verbatim risk-factor titles from {{ company.brisks.source_form }}; see source links._
{% for r in company.brisks['items'] %}
{{ loop.index }}. **{{ r.title }}**{% if r.summary %} — {{ r.summary }}{% endif %}{% if r.source_url %} ([source]({{ r.source_url }})){% endif %}
{% endfor %}
{% else %}
_{{ company.brisks.note }}_
{% endif %}

## Short-term Market View

**View**: {{ company.short_term_view }}

| Factor | Value |
|---|---|
| **Risk Level** | {{ company.absolute_level }} |
| **Period Return** | {{ company.period_return_pct }}% |
| **Return Threshold** | ±{{ company.return_threshold_pct }}% |

> *This is an observed market behavior summary, not an investment recommendation or return forecast.*

## Evidence & Limitations

- Data source: Yahoo Finance — free, delayed (not real-time); split-adjusted daily close prices.
- Analysis period: {{ company.period_label }} ({{ company.effective_days }} effective trading days).
- Data coverage: {{ company.data_coverage_pct }}%.
- Related Events use news retrieved around each significant move for context only — temporal correlation does not prove causation, and moves are not attributed to any cause.
- Financial & Filing Highlights and Business Risks are sourced from official SEC EDGAR filings; when no SEC filer matches a security (e.g. some ADRs), the section says so honestly.
- All metrics are computed deterministically from price data only; they do not incorporate fundamental analysis, news sentiment, or forward-looking estimates.
- Risk scores are relative within the selected stocks and period only; they do not represent absolute investment risk.

---

## Disclaimer

{{ disclaimer }}
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_provider():
    """Return the injected provider or the real market_data module."""
    if _provider is not None:
        return _provider
    from services import market_data as real_md
    return real_md


def _get_today() -> datetime.date:
    if _today_override is not None:
        return _today_override
    return datetime.date.today()


def _fmt_pct(value: float, decimals: int = 2) -> str:
    return f"{value * 100:.{decimals}f}"


def _render_norm_table(dates: list[str], norm_series: list[float]) -> str:
    """Render normalized series as a compact Markdown table."""
    if not dates or not norm_series:
        return "_No normalized data available._"
    # Show at most 10 evenly-spaced rows to keep the table readable
    n = len(dates)
    step = max(1, n // 10)
    indices = list(range(0, n, step))
    if (n - 1) not in indices:
        indices.append(n - 1)
    lines = ["| Date | Normalized Value (base=100) |", "|---|---|"]
    for i in indices:
        lines.append(f"| {dates[i]} | {norm_series[i]:.2f} |")
    return "\n".join(lines)


def _render_chart(
    symbol: str,
    dates: list[str],
    norm_series: list[float],
    report_id: str,
) -> Optional[str]:
    """Render the normalized-price PNG and return the Markdown image reference.

    The chart PNG is ALWAYS written under the backend's ``_reports/`` directory
    (mounted by ``app.py`` at ``/reports``) so the static mount and the local
    degrade path both work. We then try to upload the same bytes to the GitHub
    image host (``services.image_host``):

      - On success, the returned reference is the public ``raw.githubusercontent``
        URL, so a downloaded report embeds an image that loads anywhere.
      - On failure / missing config, the reference degrades to the local
        ``/reports/<file>.png`` path (on-screen still works via the frontend
        image rewrite; offline download simply loses the image — honest
        degradation).

    The filename is URL-quoted so unusual ticker characters (e.g. ``BRK.B``) do
    not break the link. Returns None only when chart rendering itself fails, so
    the report degrades to the normalized data table instead of breaking.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        file_name = f"{report_id}_{symbol}.png"
        chart_path = _REPORTS_DIR / file_name

        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(range(len(norm_series)), norm_series, linewidth=1.5, color="#2563EB")
        ax.axhline(y=100, color="#6B7280", linestyle="--", linewidth=0.8, alpha=0.7)
        ax.set_title(f"{symbol} — Normalized Price (base=100)")
        ax.set_ylabel("Normalized Value")
        # Show a subset of x-axis date labels to avoid clutter
        n = len(dates)
        tick_step = max(1, n // 6)
        tick_indices = list(range(0, n, tick_step))
        ax.set_xticks(tick_indices)
        ax.set_xticklabels([dates[i] for i in tick_indices], rotation=30, ha="right", fontsize=7)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(chart_path, dpi=100, bbox_inches="tight")
        plt.close(fig)

        # Try the GitHub image host (degrade-safe; never raises). The on-disk
        # filename is already unique per (report_id, symbol).
        from config import settings as _settings
        try:
            png_bytes = chart_path.read_bytes()
            raw_url = image_host.upload_png(png_bytes, file_name, _settings)
        except Exception:  # noqa: BLE001 — host upload is best-effort
            raw_url = None
        if raw_url:
            return raw_url

        # Degrade: serve via the /reports static mount (see app.py). URL-quote
        # the file so unusual ticker characters do not break the link.
        from urllib.parse import quote
        return f"/reports/{quote(file_name)}"
    except Exception:
        return None


def _find_max_single_day_date(bars, max_move: float) -> str:
    """Find the date of the max single-day move."""
    import numpy as np
    adj = [b.adjusted_close for b in bars]
    if len(adj) < 2:
        return ""
    returns = [adj[i] / adj[i - 1] - 1.0 for i in range(1, len(adj))]
    abs_returns = [abs(r) for r in returns]
    max_idx = int(max(range(len(abs_returns)), key=lambda i: abs_returns[i]))
    # returns[max_idx] corresponds to bars[max_idx + 1]
    return bars[min(max_idx + 1, len(bars) - 1)].date


# ---------------------------------------------------------------------------
# Bonus enrichment (Related Events / SEC filings / Business Risks).
# All three degrade to honest notes and NEVER raise — they must not block the
# core price analysis. The network/source providers are injectable for tests.
# ---------------------------------------------------------------------------

def _enrich_events(identity, significant_moves):
    """Top significant moves → news evidence (honest, non-causal). Never raises."""
    try:
        if _news_collector is not None:
            return _news_collector(identity, significant_moves) or []
        return news_svc.collect_event_evidence(identity, significant_moves, max_events=3) or []
    except Exception:  # noqa: BLE001
        return []


def _enrich_filings(identity):
    """SEC filing highlights + key financials. Returns None only on hard failure."""
    provider = _sec_provider or sec_svc
    try:
        return provider.get_filing_highlights(identity)
    except Exception:  # noqa: BLE001
        return None


def _enrich_business_risks(identity):
    """SEC 10-K/20-F business risks. Returns None only on hard failure."""
    provider = _sec_provider or sec_svc
    try:
        return provider.get_business_risks(identity)
    except Exception:  # noqa: BLE001
        return None


def _events_ctx(events) -> list[dict]:
    return [
        {
            "date": ev.date,
            "pct": _fmt_pct(ev.pct_move),
            "direction": ev.direction,
            "confidence": ev.attribution_confidence,
            "note": ev.note,
            "news": [
                {
                    "title": n.title,
                    "url": n.url,
                    "source": n.source,
                    "published_date": n.published_date,
                    "explanation": n.explanation,
                }
                for n in ev.news
            ],
        }
        for ev in events
    ]


def _filings_ctx(filings) -> dict:
    """Always return a dict with note/recent_filings/key_financials for the template."""
    if filings is None:
        return {"note": "SEC filing data not available for this security.",
                "recent_filings": [], "key_financials": []}
    recent = [
        {"form": f.form, "filed_date": f.filed_date, "url": f.url}
        for f in filings.recent_filings
    ]
    fins = [
        {
            "label": kf.label,
            "value_fmt": f"{kf.value:,.0f}",
            "unit": kf.unit,
            "period": kf.period or "",
            "source_url": kf.source_url or "",
        }
        for kf in filings.key_financials
    ]
    note = filings.note
    if not recent and not fins and not note:
        note = "SEC filing data not available for this security."
    return {"note": note, "recent_filings": recent, "key_financials": fins}


def _brisks_ctx(brisks) -> dict:
    """Always return a dict with items/source_form/note for the template."""
    if brisks is None:
        return {"note": "Business-risk data not available for this security.",
                "source_form": "", "items": []}
    items = [
        {"title": r.title, "summary": r.summary,
         "source_url": r.source_url or brisks.source_url or ""}
        for r in brisks.items
    ]
    note = brisks.note
    if not items and not note:
        note = "Business-risk data not available for this security."
    return {"note": note, "source_form": brisks.source_form or "", "items": items}


# ---------------------------------------------------------------------------
# Core orchestration
# ---------------------------------------------------------------------------

def build_report(
    companies: list[str],
    period: str,
    provider: Any = None,
    *,
    today: Optional[datetime.date] = None,
) -> ReportResult:
    """Build a multi-company 9-section English Markdown research report.

    Parameters
    ----------
    companies:
        List of company names or ticker symbols.
    period:
        Natural-language period string (e.g. "最近一个月").
    provider:
        Market data provider (must have .get_bars and .get_quote).
        Falls back to module-level _provider, then real market_data module.
    today:
        Override for today's date (for testing reproducibility).

    Returns
    -------
    ReportResult carrying an ORDERED LIST of per-stock reports — one
    self-contained 9-section document per requested stock, each with its own
    chart, verbatim disclaimer, and section_index.
    """
    # Resolve provider
    effective_provider = provider or _provider or _get_provider()
    effective_today = today or _get_today()

    # Parse period
    parsed = time_range.parse_period(period, effective_today)
    start: datetime.date = parsed["start"]
    end: datetime.date = parsed["end"]
    period_label: str = parsed["label"]
    expected_days = max(1, int((end - start).days * TRADING_DAYS_PER_YEAR / 365))

    # A batch hash distinguishes this generation; each report_id is then unique
    # per (stock, generation) as "<SYMBOL>-<8-hex>".
    batch_hash = uuid.uuid4().hex[:8]
    report_id = batch_hash    # used to name chart PNG files

    # Analyse each company
    stock_analyses: list[StockAnalysis] = []
    for query in companies:
        # Stage: identify (resolve). Use the resolved ticker as the event symbol
        # once known; until then the query string identifies the in-flight stock.
        resolve_result = resolve(query)
        if resolve_result.status != "found" or resolve_result.identity is None:
            # Unrecognized: no ticker exists — key both events by the raw query.
            emit_stage(query, "identify", "start")
            emit_stage(query, "identify", "error")
            stock_analyses.append(
                StockAnalysis(status="unrecognized", note=f"Could not identify: {query}")
            )
            continue

        identity: CompanyIdentity = resolve_result.identity
        symbol = identity.symbol
        emit_stage(symbol, "identify", "start")
        emit_stage(symbol, "identify", "done")

        # Stage: market_data (get_bars / get_quote)
        emit_stage(symbol, "market_data", "start")
        try:
            bars = effective_provider.get_bars(symbol, start, end)
        except Exception as exc:
            emit_stage(symbol, "market_data", "error")
            stock_analyses.append(
                StockAnalysis(
                    identity=identity,
                    status="data_failed",
                    note=f"Market data fetch failed: {exc}",
                )
            )
            continue

        try:
            quote = effective_provider.get_quote(symbol)
        except Exception:
            quote = None
        emit_stage(symbol, "market_data", "done")

        # Stage: metrics (compute_metrics)
        emit_stage(symbol, "metrics", "start")
        m: Metrics = metrics_svc.compute_metrics(bars, expected_days)
        emit_stage(symbol, "metrics", "done")

        # Stage: risk (risk.*)
        emit_stage(symbol, "risk", "start")
        vs = risk_svc.vol_score(m.daily_volatility)
        ds = risk_svc.drawdown_score(m.max_drawdown)
        rs = risk_svc.risk_score(m.daily_volatility, m.max_drawdown)
        level = risk_svc.absolute_level(
            m.daily_volatility, m.max_drawdown, m.effective_trading_days, m.data_coverage
        )
        rt = risk_svc.return_threshold(m.expected_trading_days)
        view = risk_svc.short_term_market_view(
            level, m.period_return, m.expected_trading_days,
            m.effective_trading_days, m.data_coverage,
        )

        risk_obj = Risk(
            vol_score=vs,
            drawdown_score=ds,
            risk_score=rs,
            absolute_level=level,  # type: ignore[arg-type]
            short_term_market_view=view,  # type: ignore[arg-type]
            return_threshold=rt,
        )

        analysis = StockAnalysis(
            identity=identity,
            metrics=m,
            risk=risk_obj,
            quote=quote,
            status="ok",
        )
        stock_analyses.append(analysis)
        emit_stage(symbol, "risk", "done")

    # Stage: compare (cross-stock ranking once for the whole batch)
    emit_stage("__batch__", "compare", "start")
    # Relative ranking across all ok analyses
    ranking = compare.rank(stock_analyses)
    emit_stage("__batch__", "compare", "done")
    rank_map: dict[str, str] = {}
    if ranking:
        for item in ranking.items:
            rank_map[item.symbol] = f"#{item.rank} of {len(ranking.items)}"

    # Symbols compared in THIS batch (for the per-report relative-rank caveat).
    batch_symbols = [
        a.identity.symbol for a in stock_analyses
        if a.status == "ok" and a.identity is not None
    ]
    multi_stock_batch = len(batch_symbols) > 1

    # Build ONE self-contained per-stock report document per company.
    reports: list[PerStockReport] = []
    for analysis in stock_analyses:
        if analysis.status != "ok" or analysis.identity is None or analysis.metrics is None:
            continue

        identity = analysis.identity
        m = analysis.metrics
        risk_obj = analysis.risk
        symbol = identity.symbol

        # Bars for date lookup (re-fetch from provider or derive from metrics)
        try:
            bars_for_dates = effective_provider.get_bars(symbol, start, end)
        except Exception:
            bars_for_dates = []

        dates = [b.date for b in bars_for_dates] if bars_for_dates else []

        # Stage: chart (_render_chart incl. image_host upload)
        emit_stage(symbol, "chart", "start")
        # Render chart (degrade gracefully)
        chart_ref = _render_chart(symbol, dates, m.normalized_series, report_id)
        emit_stage(symbol, "chart", "done")

        # Normalized table
        norm_table = _render_norm_table(dates, m.normalized_series)

        # Period high/low
        adj_closes = [b.adjusted_close for b in bars_for_dates] if bars_for_dates else []
        period_high = f"{max(adj_closes):.2f}" if adj_closes else "N/A"
        period_low = f"{min(adj_closes):.2f}" if adj_closes else "N/A"

        # Max single-day date
        max_day_date = _find_max_single_day_date(bars_for_dates, m.max_single_day_move)

        # Negative-day vol display
        if m.negative_day_volatility is not None:
            neg_vol_str = f"{_fmt_pct(m.negative_day_volatility)}% (annualized, negative days only)"
        else:
            neg_vol_str = f"N/A ({m.negative_day_volatility_reason or 'insufficient data'})"

        # Relative rank. When this turn compared multiple stocks, the per-report
        # §3 line carries the batch peers + an explicit "within this batch" caveat
        # so each self-contained report honestly states what it was ranked against.
        relative_rank = rank_map.get(symbol, "N/A (single stock or insufficient data)")
        if multi_stock_batch and symbol in rank_map:
            peers = ", ".join(s for s in batch_symbols if s != symbol)
            relative_rank = (
                f"{rank_map[symbol]} (within this batch: {', '.join(batch_symbols)}; "
                f"ranked relative to {peers} only)"
            )

        # Bonus enrichment (on-demand; network; degrade-safe, never raises)
        # Stage: events (_enrich_events)
        emit_stage(symbol, "events", "start")
        events = _enrich_events(identity, m.significant_moves)
        emit_stage(symbol, "events", "done")

        # Stage: filings (_enrich_filings)
        emit_stage(symbol, "filings", "start")
        filings = _enrich_filings(identity)
        emit_stage(symbol, "filings", "done")

        # Stage: risk_factors (_enrich_business_risks)
        emit_stage(symbol, "risk_factors", "start")
        brisks = _enrich_business_risks(identity)
        emit_stage(symbol, "risk_factors", "done")

        ctx = {
            "symbol": symbol,
            "name": identity.name,
            "exchange": identity.exchange,
            "instrument": identity.instrument,
            "market": identity.market,
            "period_label": period_label,
            "data_coverage_pct": f"{m.data_coverage * 100:.1f}",
            "effective_days": m.effective_trading_days,
            "expected_days": m.expected_trading_days,
            "norm_table": norm_table,
            "chart_ref": chart_ref,
            "period_return_pct": _fmt_pct(m.period_return),
            "period_high": period_high,
            "period_low": period_low,
            "up_days": m.up_days,
            "down_days": m.down_days,
            "annualized_vol_pct": _fmt_pct(m.annualized_volatility),
            "daily_vol_pct": _fmt_pct(m.daily_volatility),
            "neg_vol_str": neg_vol_str,
            "max_drawdown_pct": _fmt_pct(m.max_drawdown),
            "max_single_day_pct": _fmt_pct(m.max_single_day_move),
            "max_single_day_significant": m.max_single_day_significant,
            "max_single_day_date": max_day_date,
            "risk_score": risk_obj.risk_score if risk_obj else "N/A",
            "absolute_level": risk_obj.absolute_level if risk_obj else "N/A",
            "relative_rank": relative_rank,
            "risk_caveat": risk_obj.caveat if risk_obj else "",
            "short_term_view": risk_obj.short_term_market_view if risk_obj else "N/A",
            "return_threshold_pct": _fmt_pct(risk_obj.return_threshold if risk_obj else 0.0),
            "events": _events_ctx(events),
            "filings": _filings_ctx(filings),
            "brisks": _brisks_ctx(brisks),
        }

        # Per-stock section_index (so cite resolves against THIS stock's report).
        section_index: list[ReportSectionItem] = []
        item_counter: dict[str, int] = {}

        def _add_index(sec: str, text: str, source: Optional[str] = None) -> None:
            item_counter[sec] = item_counter.get(sec, 0) + 1
            section_index.append(ReportSectionItem(
                owner_company=symbol,
                section=sec,
                item=item_counter[sec],
                text=text,
                source=source,
            ))

        _add_index("Company Snapshot", f"{identity.name} ({symbol}) on {identity.exchange}.")
        _add_index(
            "Price Trend",
            f"Period return: {_fmt_pct(m.period_return)}%. "
            f"Normalized series starts at 100.0 on {m.normalized_base_date}.",
        )
        _add_index(
            "Observed Market Risk",
            f"Absolute level: {risk_obj.absolute_level if risk_obj else 'N/A'}. "
            f"Risk score: {risk_obj.risk_score if risk_obj else 'N/A'}.",
        )
        _add_index(
            "Significant Move",
            f"Max single-day move: {_fmt_pct(m.max_single_day_move)}% "
            f"({'significant' if m.max_single_day_significant else 'not significant'}).",
        )
        # Bonus sections — real, citable entries (degrade to one honest entry)
        if events:
            for ev in events:
                if ev.news:
                    titles = "; ".join(n.title for n in ev.news[:3])
                    _add_index(
                        "Related Events",
                        f"{ev.date} {_fmt_pct(ev.pct_move)}% ({ev.direction}): {titles}",
                        source=ev.news[0].url,
                    )
                else:
                    _add_index(
                        "Related Events",
                        f"{ev.date} {_fmt_pct(ev.pct_move)}% ({ev.direction}): {ev.note}",
                    )
        else:
            _add_index("Related Events",
                       "No significant single-day moves to attribute in this period.")

        if filings is not None and (filings.recent_filings or filings.key_financials):
            for f in filings.recent_filings:
                _add_index("Financial & Filing Highlights",
                           f"{f.form} filed {f.filed_date}.", source=f.url)
            for kf in filings.key_financials:
                _add_index("Financial & Filing Highlights",
                           f"{kf.label}: {kf.value:,.0f} {kf.unit} ({kf.period or 'latest'}).",
                           source=kf.source_url)
        else:
            _add_index(
                "Financial & Filing Highlights",
                (filings.note if filings is not None else None)
                or "SEC filing data not available for this security.",
            )

        if brisks is not None and brisks.items:
            for r in brisks.items:
                text = r.title + (f" — {r.summary}" if r.summary else "")
                _add_index("Business Risks", text, source=r.source_url or brisks.source_url)
        else:
            _add_index(
                "Business Risks",
                (brisks.note if brisks is not None else None)
                or "Business-risk data not available for this security.",
            )
        _add_index(
            "Short-term Market View",
            f"View: {risk_obj.short_term_market_view if risk_obj else 'N/A'}.",
        )
        _add_index(
            "Evidence & Limitations",
            f"Data source: Yahoo Finance. Period: {period_label}. "
            f"Coverage: {m.data_coverage * 100:.1f}%.",
        )

        # Stage: assemble (Jinja2 render of this stock's markdown)
        emit_stage(symbol, "assemble", "start")
        # Render THIS stock's self-contained Markdown (own chart + own disclaimer).
        markdown = _SECTION_TEMPLATE.render(company=ctx, disclaimer=DISCLAIMER)
        emit_stage(symbol, "assemble", "done")

        reports.append(PerStockReport(
            report_id=f"{symbol}-{batch_hash}",
            title=f"{identity.name} ({symbol}) — {period_label}",
            symbol=symbol,
            markdown=markdown,
            section_index=section_index,
        ))

    return ReportResult(reports=reports)
