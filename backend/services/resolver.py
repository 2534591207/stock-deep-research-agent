"""services/resolver.py — 公司标识解析（**通用**：ticker 直通 / 中文别名 / 英文名模糊）。

支持边界（不再绑死 14 条 curated 名单，避免 demo-bound）：
  1. 中文别名（aliases.json）：精确 key → symbol（不要求在 curated 名单内）。
  2. ticker 直通：任意 1–5 位字母 ticker 视为候选（found）；**真实性交给行情层 Yahoo Finance 校验**
     （无效 ticker 在取数时 raise，由上层如实告知"未找到数据"）。
  3. 英文名 rapidfuzz 模糊：在 curated 名单（us_catalog.json）的 name 上匹配（便利通道）。

curated 名单只提供 instrument（ADR/common）/交易所等**精确信息**；不是"支不支持"的硬边界。
rapidfuzz 仅匹配工具，不做裁决。多匹配 → ambiguous；纯中文/非 ticker/无命中 → none（不编码）。

返回：ResolveResult{status: found|none|ambiguous, identity?, candidates?, query}
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz, process as fuzz_process

from models import CompanyIdentity, ResolveResult

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CATALOG_PATH = _DATA_DIR / "us_catalog.json"
_ALIASES_PATH = _DATA_DIR / "aliases.json"

_FUZZY_THRESHOLD = 80
_AMBIGUOUS_MAX_CANDIDATES = 5
# ticker 形态：1–5 位字母，可选 .X 后缀（如 BRK.B）
_TICKER_RE = re.compile(r"^[A-Za-z]{1,5}(\.[A-Za-z])?$")


@lru_cache(maxsize=1)
def _load_catalog() -> list[dict]:
    """curated 名单（提供精确 instrument/交易所）。读取失败 → 空（不阻塞 ticker 直通）。"""
    try:
        with open(_CATALOG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    return [e for e in entries if e.get("exchange", "").upper() in {"NYSE", "NASDAQ"}]


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, str]:
    """中文（及英文昵称）→ symbol 映射。读取失败 → 空。"""
    try:
        with open(_ALIASES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _entry_to_identity(entry: dict) -> CompanyIdentity:
    raw_type = entry.get("type", "Common Stock")
    instrument = "ADR" if "ADR" in raw_type else "common"
    return CompanyIdentity(
        name=entry.get("name", entry["symbol"]),
        symbol=entry["symbol"],
        exchange=entry.get("exchange", "US"),
        instrument=instrument,
        cik=entry.get("cik"),
    )


def _lookup_by_symbol(symbol: str, catalog: list[dict]) -> Optional[dict]:
    sym = symbol.upper()
    for entry in catalog:
        if entry.get("symbol", "").upper() == sym:
            return entry
    return None


def _identity_for_symbol(symbol: str, catalog: list[dict]) -> CompanyIdentity:
    """在 curated 名单内 → 用名单精确信息；否则通用直通（默认 common/US，由行情层校验真实性）。"""
    entry = _lookup_by_symbol(symbol, catalog)
    if entry:
        return _entry_to_identity(entry)
    return CompanyIdentity(name=symbol.upper(), symbol=symbol.upper(), exchange="US", instrument="common")


def resolve(text: str) -> ResolveResult:
    query = (text or "").strip()
    if not query:
        return ResolveResult(status="none", query=query)

    catalog = _load_catalog()
    aliases = _load_aliases()

    # ── 通道 1：别名精确匹配（通用，不要求在 curated 名单内）──────────────────
    if query in aliases:
        return ResolveResult(status="found", identity=_identity_for_symbol(aliases[query], catalog), query=query)
    # 大小写不敏感的英文昵称兜底（如 "apple" / "Tesla"）
    lowered = {k.lower(): v for k, v in aliases.items()}
    if query.lower() in lowered:
        return ResolveResult(status="found", identity=_identity_for_symbol(lowered[query.lower()], catalog), query=query)

    # ── 通道 2：ticker 直通（任意 1–5 位字母 ticker；真实性交给行情层校验）──────
    if _TICKER_RE.match(query):
        return ResolveResult(status="found", identity=_identity_for_symbol(query, catalog), query=query)

    # ── 通道 3：英文名 rapidfuzz 模糊匹配（curated 名单便利通道）──────────────
    names = [e["name"] for e in catalog]
    matches = fuzz_process.extract(
        query, names, scorer=fuzz.WRatio, limit=_AMBIGUOUS_MAX_CANDIDATES, score_cutoff=_FUZZY_THRESHOLD
    )
    if not matches:
        return ResolveResult(status="none", query=query)
    if len(matches) == 1 or (matches[0][1] - matches[1][1] >= 10):
        matched_name = matches[0][0]
        entry = next(e for e in catalog if e["name"] == matched_name)
        return ResolveResult(status="found", identity=_entry_to_identity(entry), query=query)
    candidates = []
    for matched_name, _score, _idx in matches:
        entry = next((e for e in catalog if e["name"] == matched_name), None)
        if entry:
            candidates.append(entry["symbol"])
    return ResolveResult(status="ambiguous", candidates=candidates, query=query)
