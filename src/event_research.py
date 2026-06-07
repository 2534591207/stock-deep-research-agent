from __future__ import annotations

import os

import httpx

from .models import Company, TimeRange


def research_events(company: Company, period: TimeRange, moves: list[dict]) -> tuple[list[dict], list[str]]:
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return [], ["未配置 TAVILY_API_KEY，事件研究阶段已跳过。"]

    dates = ", ".join(move["date"] for move in moves)
    query = (
        f"{company.name} {company.symbol} important news events between "
        f"{period.start_date} and {period.end_date}, especially around {dates}"
    )
    payload = {
        "api_key": api_key,
        "query": query,
        "topic": "finance",
        "search_depth": "advanced",
        "max_results": 6,
        "start_date": period.start_date.isoformat(),
        "end_date": period.end_date.isoformat(),
    }
    response = httpx.post("https://api.tavily.com/search", json=payload, timeout=30)
    response.raise_for_status()
    results = [
        {
            "title": item.get("title"),
            "url": item.get("url"),
            "content": item.get("content", "")[:500],
            "published_date": item.get("published_date"),
        }
        for item in response.json().get("results", [])
    ]
    return results, []
