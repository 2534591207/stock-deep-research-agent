"""services/news.py — Related Events: find news around significant price moves.

Honesty contract:
- News items are described neutrally (what the article is about).
- attribution_confidence is NEVER set to 'High'.
- collect_event_evidence NEVER raises; any failure degrades to an honest note.
- The key value is NEVER printed or logged.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from models import CompanyIdentity, EventEvidence, NewsItem, SignificantMove

_HONEST_NOTE = (
    "No reliable news evidence found around this date; "
    "the move is not attributed to any cause."
)


class TavilyNewsClient:
    """Thin wrapper around the Tavily search API using httpx (no SDK required).

    Returns [] on missing key or any network/parse error — never raises.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        if api_key is None:
            from config import settings
            api_key = settings.tavily_api_key or ""
        # Store without printing or logging the value.
        self._key = api_key.strip()

    def search(
        self,
        query: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        """Query Tavily for news. Returns raw result dicts or [] on any error."""
        if not self._key:
            return []

        try:
            import httpx  # delayed import; available in the project venv

            payload: dict = {
                "api_key": self._key,
                "query": query,
                "topic": "news",
                "max_results": 5,
            }
            if start_date:
                payload["start_date"] = start_date
            if end_date:
                payload["end_date"] = end_date

            response = httpx.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if not isinstance(results, list):
                return []
            return results
        except Exception:  # noqa: BLE001 — degrade silently, never expose key
            return []


def _parse_news_item(raw: dict) -> Optional[NewsItem]:
    """Map one Tavily result dict to a NewsItem. Returns None if title/url missing."""
    title = (raw.get("title") or "").strip()
    url = (raw.get("url") or "").strip()
    if not title or not url:
        return None

    # source: prefer explicit field, fall back to domain extraction
    source: Optional[str] = raw.get("source") or None
    if not source:
        try:
            from urllib.parse import urlparse
            source = urlparse(url).netloc or None
        except Exception:  # noqa: BLE001
            source = None

    published_date: Optional[str] = raw.get("published_date") or None

    # snippet: prefer content excerpt, then score-less summary
    snippet_raw = raw.get("content") or raw.get("description") or ""
    snippet = snippet_raw[:300].strip() if snippet_raw else None

    # explanation: neutral one-liner about what the article covers (never causal)
    explanation_raw = raw.get("title") or ""
    # Use the title as the basis; trim to a single sentence if long
    if explanation_raw:
        # Take up to first sentence boundary or 120 chars
        for sep in (".", "!", "?"):
            idx = explanation_raw.find(sep)
            if 0 < idx <= 120:
                explanation_raw = explanation_raw[: idx + 1]
                break
        explanation = explanation_raw.strip()
    else:
        explanation = None

    return NewsItem(
        title=title,
        url=url,
        source=source,
        published_date=published_date,
        snippet=snippet or None,
        explanation=explanation,
    )


def _date_within(published_date: Optional[str], move_date: str, days: int = 1) -> bool:
    """Return True if published_date is within ±days of move_date (ISO strings)."""
    if not published_date:
        return False
    try:
        pub = date.fromisoformat(published_date[:10])
        move = date.fromisoformat(move_date[:10])
        return abs((pub - move).days) <= days
    except (ValueError, TypeError):
        return False


def _confidence_for(news: list[NewsItem], move_date: str, company_name: str, symbol: str) -> str:
    """Determine attribution_confidence. NEVER returns 'High'."""
    if not news:
        return "Low"
    name_lower = company_name.lower()
    sym_lower = symbol.lower()
    for item in news:
        if not _date_within(item.published_date, move_date, days=1):
            continue
        # Check if the article is clearly about this company
        combined = " ".join(
            filter(None, [item.title, item.snippet, item.explanation])
        ).lower()
        if name_lower in combined or sym_lower in combined:
            return "Medium"
    return "Low"


def _collect_for_move(
    move: SignificantMove,
    identity: CompanyIdentity,
    client: TavilyNewsClient,
    window_days: int,
) -> EventEvidence:
    """Gather news for a single move. Never raises — always returns EventEvidence."""
    try:
        move_date = date.fromisoformat(move.date)
        start = (move_date - timedelta(days=window_days)).isoformat()
        end = (move_date + timedelta(days=window_days)).isoformat()

        query = f"{identity.name} {identity.symbol} news"
        raw_results = client.search(query, start_date=start, end_date=end)

        news: list[NewsItem] = []
        for raw in raw_results:
            item = _parse_news_item(raw)
            if item is not None:
                news.append(item)

        if not news:
            return EventEvidence(
                date=move.date,
                pct_move=move.pct_move,
                direction=move.direction,
                attribution_confidence="Low",
                news=[],
                note=_HONEST_NOTE,
            )

        confidence = _confidence_for(news, move.date, identity.name, identity.symbol)
        return EventEvidence(
            date=move.date,
            pct_move=move.pct_move,
            direction=move.direction,
            attribution_confidence=confidence,
            news=news,
        )

    except Exception:  # noqa: BLE001 — never propagate; degrade honestly
        return EventEvidence(
            date=move.date,
            pct_move=move.pct_move,
            direction=move.direction,
            attribution_confidence="Low",
            news=[],
            note=_HONEST_NOTE,
        )


def collect_event_evidence(
    identity: CompanyIdentity,
    significant_moves: list[SignificantMove],
    *,
    client: Optional[TavilyNewsClient] = None,
    max_events: int = 3,
    window_days: int = 3,
) -> list[EventEvidence]:
    """Return EventEvidence for the top max_events moves by |pct_move|.

    Never raises. Degrades to honest notes on any failure or missing data.
    """
    if client is None:
        client = TavilyNewsClient()

    # Select top N by absolute magnitude
    selected = sorted(significant_moves, key=lambda m: abs(m.pct_move), reverse=True)
    selected = selected[:max_events]

    results: list[EventEvidence] = []
    for move in selected:
        evidence = _collect_for_move(move, identity, client, window_days)
        results.append(evidence)

    return results
