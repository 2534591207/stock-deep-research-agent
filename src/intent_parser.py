from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from .company_resolver import resolve_companies
from .models import ResearchTask, TimeRange


def parse_research_task(query: str, today: Optional[date] = None) -> ResearchTask:
    today = today or date.today()
    companies = resolve_companies(query)
    if not companies:
        raise ValueError("没有识别到支持的美股公司，请输入公司名称或股票代码。")

    time_range, defaulted = parse_time_range(query, today)
    focus = ["performance", "risk"]
    if any(word in query for word in ("财报", "文件", "材料")):
        focus.append("documents")
    if any(word in query for word in ("为什么", "原因", "新闻", "事件", "舆情")):
        focus.append("events")

    return ResearchTask(
        intent="multi_stock_research" if len(companies) > 1 else "single_stock_research",
        companies=companies,
        time_range=time_range,
        focus=focus,
        defaults_applied=["未指定时间范围，默认最近 30 天"] if defaulted else [],
    )


def parse_time_range(query: str, today: date) -> tuple[TimeRange, bool]:
    days = 30
    label = "最近 30 天"
    source = "system_default"
    defaulted = True

    if "今年以来" in query or "年初至今" in query:
        start = date(today.year, 1, 1)
        return TimeRange(label="今年以来", start_date=start, end_date=today, source="user_explicit"), False

    number_match = re.search(r"最近\s*(\d+)\s*(天|日|个月|月|年)", query)
    if number_match:
        count = int(number_match.group(1))
        unit = number_match.group(2)
        if unit in ("天", "日"):
            days = count
        elif unit in ("个月", "月"):
            days = count * 30
        else:
            days = count * 365
        label = f"最近 {count} {unit}"
        source = "user_explicit"
        defaulted = False
    elif "最近三个月" in query or "近三个月" in query:
        days, label, source, defaulted = 90, "最近三个月", "user_explicit", False
    elif "最近半年" in query or "近半年" in query:
        days, label, source, defaulted = 180, "最近半年", "user_explicit", False
    elif "最近一年" in query or "近一年" in query:
        days, label, source, defaulted = 365, "最近一年", "user_explicit", False
    elif "最近一个月" in query or "近一个月" in query:
        days, label, source, defaulted = 30, "最近一个月", "user_explicit", False

    return (
        TimeRange(
            label=label,
            start_date=today - timedelta(days=days),
            end_date=today,
            source=source,
        ),
        defaulted,
    )
