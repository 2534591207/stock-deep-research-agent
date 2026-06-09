"""tests/test_time_range.py — T1.4 period 解析（注入固定 today，可复现）。

AC-H3：未给范围 → 默认 30 天 + note。
超 1 年 → MAX_RANGE_DAYS=365 封顶 + note。
"三个月" → 90 自然日。
"""
import datetime

import pytest

from services.time_range import parse_period
from config import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS

# 固定 today，消除真实时钟随机性
TODAY = datetime.date(2024, 6, 15)


# ── AC-H3：空输入 → 默认 30 天 + note ──────────────────────────────────────

def test_none_input_defaults_to_30_days():
    result = parse_period(None, TODAY)
    assert result["range_days"] == DEFAULT_RANGE_DAYS
    assert result["start"] == TODAY - datetime.timedelta(days=DEFAULT_RANGE_DAYS)
    assert result["end"] == TODAY
    assert result["note"] is not None and len(result["note"]) > 0, "AC-H3: note 必须有可见文案"


def test_empty_string_defaults_to_30_days():
    result = parse_period("", TODAY)
    assert result["range_days"] == DEFAULT_RANGE_DAYS
    assert result["note"] is not None and len(result["note"]) > 0


def test_whitespace_only_defaults_to_30_days():
    result = parse_period("   ", TODAY)
    assert result["range_days"] == DEFAULT_RANGE_DAYS
    assert result["note"] is not None


# ── "三个月" → 90 自然日 ─────────────────────────────────────────────────

def test_san_ge_yue_returns_90_days():
    result = parse_period("三个月", TODAY)
    assert result["range_days"] == 90
    assert result["start"] == TODAY - datetime.timedelta(days=90)
    assert result["end"] == TODAY
    assert result["note"] is None


def test_zui_jin_san_ge_yue_returns_90_days():
    result = parse_period("最近三个月", TODAY)
    assert result["range_days"] == 90
    assert result["start"] == TODAY - datetime.timedelta(days=90)


# ── 超 1 年 → MAX_RANGE_DAYS=365 封顶 + note ────────────────────────────

def test_yi_nian_returns_365_no_cap():
    """一年 = 365 天，刚好等于上限，不触发截断 note。"""
    result = parse_period("一年", TODAY)
    assert result["range_days"] == MAX_RANGE_DAYS
    assert result["start"] == TODAY - datetime.timedelta(days=MAX_RANGE_DAYS)
    assert result["note"] is None


def test_liang_nian_capped_at_365_with_note():
    """两年 > 365 → 截到 365 + note。"""
    result = parse_period("两年", TODAY)
    assert result["range_days"] == MAX_RANGE_DAYS
    assert result["start"] == TODAY - datetime.timedelta(days=MAX_RANGE_DAYS)
    assert result["note"] is not None and len(result["note"]) > 0


def test_san_nian_capped_at_365_with_note():
    result = parse_period("三年", TODAY)
    assert result["range_days"] == MAX_RANGE_DAYS
    assert result["note"] is not None


# ── YTD / 今年以来 ──────────────────────────────────────────────────────

def test_ytd_start_is_jan_1():
    result = parse_period("今年以来", TODAY)
    assert result["start"] == datetime.date(TODAY.year, 1, 1)
    assert result["end"] == TODAY
    assert result["label"] == "今年以来（YTD）"


def test_ytd_english_case_insensitive():
    result = parse_period("YTD", TODAY)
    assert result["start"] == datetime.date(TODAY.year, 1, 1)


def test_ytd_range_days_correct():
    result = parse_period("ytd", TODAY)
    expected_days = (TODAY - datetime.date(TODAY.year, 1, 1)).days
    assert result["range_days"] == expected_days


# ── 其他合法中文相对范围 ─────────────────────────────────────────────────

def test_yi_ge_yue_returns_30():
    result = parse_period("一个月", TODAY)
    assert result["range_days"] == 30
    assert result["note"] is None


def test_ban_nian_returns_180():
    result = parse_period("半年", TODAY)
    assert result["range_days"] == 180
    assert result["note"] is None


def test_yi_zhou_returns_7():
    result = parse_period("一周", TODAY)
    assert result["range_days"] == 7
    assert result["note"] is None


# ── 无法解析 → 默认 30 天 + note ────────────────────────────────────────

def test_unrecognized_text_defaults_to_30_with_note():
    result = parse_period("上个季度末", TODAY)
    assert result["range_days"] == DEFAULT_RANGE_DAYS
    assert result["note"] is not None and len(result["note"]) > 0


def test_gibberish_defaults_to_30_with_note():
    result = parse_period("xyzxyz", TODAY)
    assert result["range_days"] == DEFAULT_RANGE_DAYS
    assert result["note"] is not None


# ── 注入固定 today，start/end 确定性验证 ─────────────────────────────────

def test_injected_today_is_respected():
    fixed = datetime.date(2023, 1, 31)
    result = parse_period("三个月", fixed)
    assert result["end"] == fixed
    assert result["start"] == datetime.date(2022, 11, 2)  # 2023-01-31 - 90 days


def test_different_today_gives_different_start():
    day_a = datetime.date(2024, 1, 1)
    day_b = datetime.date(2024, 6, 1)
    r_a = parse_period("一个月", day_a)
    r_b = parse_period("一个月", day_b)
    assert r_a["start"] != r_b["start"]
    assert r_a["end"] == day_a
    assert r_b["end"] == day_b


# ── 返回结构完整性 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [None, "", "三个月", "今年以来", "两年", "未知输入"])
def test_result_has_all_keys(text):
    result = parse_period(text, TODAY)
    for key in ("start", "end", "range_days", "label", "note"):
        assert key in result, f"缺少字段: {key}"
    assert isinstance(result["start"], datetime.date)
    assert isinstance(result["end"], datetime.date)
    assert isinstance(result["range_days"], int)
    assert result["range_days"] > 0
    assert result["end"] >= result["start"]
