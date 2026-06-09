"""自然语言 period → 明确起止（纯代码规则，无真实时钟）。

AC-H3：未给范围 → 默认最近 30 天，并在 note 中返回可见说明文案。
1 年封顶：超过 MAX_RANGE_DAYS=365 自然日 → 截到 365 + note。
注入 today 可复现（绝不调用 date.today()）。
"""
from __future__ import annotations

import datetime
import re

from config import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS


# ---------------------------------------------------------------------------
# 规则映射（中文自然语言 → 自然日数）
# ---------------------------------------------------------------------------

_PATTERN_DAYS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"一周|7\s*天|七天"), 7),
    (re.compile(r"半月|15\s*天|十五天"), 15),
    (re.compile(r"一个月|1\s*个月|30\s*天|三十天"), 30),
    (re.compile(r"三个月|3\s*个月|90\s*天|九十天"), 90),
    (re.compile(r"半年|6\s*个月|180\s*天"), 180),
    (re.compile(r"一年|12\s*个月|365\s*天|一整年"), 365),
    # 超一年的表述直接映射为 MAX_RANGE_DAYS
    (re.compile(r"两年|三年|五年|十年|\d+\s*年"), MAX_RANGE_DAYS + 1),
]

_PATTERN_YTD = re.compile(r"今年以来|ytd|year.to.date", re.IGNORECASE)


def parse_period(
    text: str | None,
    today: datetime.date,
) -> dict:
    """将自然语言 period 解析为明确起止区间。

    返回字典包含：
      start       : datetime.date
      end         : datetime.date  (= today)
      range_days  : int            (自然日数，即 (end - start).days)
      label       : str            (人类可读标签)
      note        : str | None     (AC-H3 说明文案 / 超范围说明 / None)
    """
    end = today
    note: str | None = None

    # ── 空输入 → AC-H3 默认 30 天 ──────────────────────────────────────
    if not text or not text.strip():
        start = end - datetime.timedelta(days=DEFAULT_RANGE_DAYS)
        return {
            "start": start,
            "end": end,
            "range_days": DEFAULT_RANGE_DAYS,
            "label": f"最近 {DEFAULT_RANGE_DAYS} 天",
            "note": f"未指定时间范围，已默认使用最近 {DEFAULT_RANGE_DAYS} 天。",
        }

    text = text.strip()

    # ── YTD / 今年以来 ──────────────────────────────────────────────────
    if _PATTERN_YTD.search(text):
        start = datetime.date(today.year, 1, 1)
        range_days = (end - start).days
        # YTD 也受 MAX_RANGE_DAYS 约束（理论上全年 ≤ 365，但防跨年极端情形）
        if range_days > MAX_RANGE_DAYS:
            start = end - datetime.timedelta(days=MAX_RANGE_DAYS)
            range_days = MAX_RANGE_DAYS
            note = f"今年以来超过 {MAX_RANGE_DAYS} 天，已截断至最近 {MAX_RANGE_DAYS} 天。"
        return {
            "start": start,
            "end": end,
            "range_days": range_days,
            "label": "今年以来（YTD）",
            "note": note,
        }

    # ── 中文相对范围规则匹配 ────────────────────────────────────────────
    for pattern, days in _PATTERN_DAYS:
        if pattern.search(text):
            raw_days = days
            if raw_days > MAX_RANGE_DAYS:
                start = end - datetime.timedelta(days=MAX_RANGE_DAYS)
                note = (
                    f"请求范围（{raw_days} 天）超过系统上限 {MAX_RANGE_DAYS} 天，"
                    f"已截断至最近 {MAX_RANGE_DAYS} 天。"
                )
                range_days = MAX_RANGE_DAYS
            else:
                start = end - datetime.timedelta(days=raw_days)
                range_days = raw_days
            label = f"最近 {range_days} 天"
            return {
                "start": start,
                "end": end,
                "range_days": range_days,
                "label": label,
                "note": note,
            }

    # ── 无法解析 → 默认 30 天 + note ───────────────────────────────────
    start = end - datetime.timedelta(days=DEFAULT_RANGE_DAYS)
    return {
        "start": start,
        "end": end,
        "range_days": DEFAULT_RANGE_DAYS,
        "label": f"最近 {DEFAULT_RANGE_DAYS} 天",
        "note": f"无法解析时间范围「{text}」，已默认使用最近 {DEFAULT_RANGE_DAYS} 天。",
    }
