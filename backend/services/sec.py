"""services/sec.py — SEC EDGAR bonus 充实：Financial & Filing Highlights + Business Risks.

诚实红线（与 models.py 共享契约一致）：
  - **绝不**硬编码任何 ticker 的 CIK —— 一律动态解析自 SEC 官方
    https://www.sec.gov/files/company_tickers.json（内存缓存）。
  - 财务数字只取自 SEC XBRL companyfacts（确定性），绝不编造。
  - 经营风险标题**逐字**取自真实 10-K/20-F，绝不发明。
  - 任一外部源不可用 / 抓取失败 → 该节如实降级（honest `note`），
    函数**永不 raise**，绝不阻塞核心行情分析。

SEC 合规：每个 SEC HTTP 请求必须带 `User-Agent: <settings.sec_user_agent>`
（SEC 要求可联系的 UA）；请求节制（顺序、单次少量）。

`fetcher` 可注入：默认走 httpx + UA header；测试注入 FakeFetcher 返回 canned 字节，
故全部用例可完全离线运行。
"""
from __future__ import annotations

import json
import re
from typing import Callable, Optional

from bs4 import BeautifulSoup

from config import settings
from models import (
    BusinessRiskItem,
    BusinessRisks,
    CompanyIdentity,
    FilingHighlight,
    FilingHighlights,
    FinancialFact,
)

# ===== SEC 端点 =====
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
_ARCHIVES_DOC_URL = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{primary_doc}"
)

# 申报亮点关注的表单（顺序即优先展示顺序）。
_HIGHLIGHT_FORMS = ("10-K", "10-Q", "8-K", "20-F")
_MAX_FILINGS = 5

# companyfacts 关注的 us-gaap 概念：(展示 label, 候选 XBRL tag 列表，按优先级)。
_KEY_FINANCIAL_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Revenue",
        ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ),
    ("Net Income", ("NetIncomeLoss",)),
    ("Total Assets", ("Assets",)),
)

# 风险因素：年报表单 → Item 1A（10-K）/ Item 3.D（20-F）。
_MAX_RISK_ITEMS = 8
_ANNUAL_FORMS = ("10-K", "20-F")

# Fetcher 契约：给 URL，返回原始 bytes。默认实现带 SEC UA header。
Fetcher = Callable[[str], bytes]

# ticker→CIK 内存缓存（进程级；首个请求触发一次拉取）。
_ticker_cik_cache: Optional[dict[str, int]] = None


# ===========================================================================
# 默认 fetcher（带 SEC User-Agent，httpx）
# ===========================================================================
def _default_fetcher(url: str) -> bytes:
    """默认 HTTP 取数：所有请求带 SEC 要求的可联系 User-Agent。失败 raise（由调用方降级）。"""
    import httpx

    ua = (settings.sec_user_agent or "").strip()
    if not ua:
        # SEC 强制要求 UA；无配置则不发请求（上层据此如实降级，绝不无 UA 打 SEC）。
        raise RuntimeError("SEC requests require settings.sec_user_agent (contactable User-Agent).")
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    resp = httpx.get(url, headers=headers, timeout=20.0, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


def _resolve_fetcher(fetcher: Optional[Fetcher]) -> Fetcher:
    return fetcher if fetcher is not None else _default_fetcher


# ===========================================================================
# 动态 ticker → CIK（绝不硬编码）
# ===========================================================================
def _build_ticker_cik_map(raw: object) -> dict[str, int]:
    """把 company_tickers.json 解析成 {TICKER_UPPER: cik_int}。

    SEC 该文件形如 {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}。
    """
    mapping: dict[str, int] = {}
    if not isinstance(raw, dict):
        return mapping
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        cik = entry.get("cik_str")
        if not ticker or cik is None:
            continue
        try:
            mapping[str(ticker).upper()] = int(cik)
        except (TypeError, ValueError):
            continue
    return mapping


def _load_ticker_cik_map(fetcher: Fetcher) -> dict[str, int]:
    """加载（并内存缓存）ticker→CIK 映射。失败 → 空 dict（调用方据此降级）。"""
    global _ticker_cik_cache
    if _ticker_cik_cache is not None:
        return _ticker_cik_cache
    try:
        raw_bytes = fetcher(_COMPANY_TICKERS_URL)
        data = json.loads(raw_bytes)
    except Exception:  # noqa: BLE001 — 网络/解析任何失败都不应抛出，降级即可
        return {}
    mapping = _build_ticker_cik_map(data)
    # 仅在拉取到非空映射时缓存，避免把一次瞬时失败固化成空表。
    if mapping:
        _ticker_cik_cache = mapping
    return mapping


def resolve_cik(symbol: str, *, fetcher: Optional[Fetcher] = None) -> Optional[int]:
    """ticker → CIK 整数（**动态**解析自 company_tickers.json，绝不硬编码）。未命中 → None。"""
    f = _resolve_fetcher(fetcher)
    mapping = _load_ticker_cik_map(f)
    return mapping.get((symbol or "").strip().upper())


def _cik10(cik_int: int) -> str:
    """data.sec.gov 要求 10 位零填充 CIK（如 320193 → '0000320193'）。"""
    return f"{int(cik_int):010d}"


def reset_cache() -> None:
    """清空内存缓存（仅供测试隔离使用）。"""
    global _ticker_cik_cache
    _ticker_cik_cache = None


# ===========================================================================
# 通用工具
# ===========================================================================
def _norm_ws(text: str) -> str:
    """折叠所有空白（含 bs4 由 &nbsp; 转成的不间断空格 \\xa0）为单空格并 strip。"""
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _fetch_json(fetcher: Fetcher, url: str) -> Optional[object]:
    """取 URL 并解析 JSON；任何失败 → None（绝不抛出）。"""
    try:
        return json.loads(fetcher(url))
    except Exception:  # noqa: BLE001
        return None


def _iter_recent_filings(submissions: dict) -> list[dict]:
    """把 submissions.filings.recent 的列向（columnar）结构转成逐行 dict。"""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    rows: list[dict] = []
    keys = ("form", "filingDate", "accessionNumber", "primaryDocument", "primaryDocDescription")
    for i in range(len(forms)):
        row = {}
        for k in keys:
            col = recent.get(k) or []
            row[k] = col[i] if i < len(col) else None
        rows.append(row)
    return rows


def _filing_url(cik_int: int, accession: str, primary_doc: Optional[str]) -> str:
    """构造 EDGAR Archives 主文档 URL。"""
    accession_nodash = (accession or "").replace("-", "")
    return _ARCHIVES_DOC_URL.format(
        cik_int=int(cik_int),
        accession_nodash=accession_nodash,
        primary_doc=primary_doc or "",
    )


# ===========================================================================
# Filing Highlights
# ===========================================================================
def _extract_key_financials(facts: dict, source_url: str) -> list[FinancialFact]:
    """从 companyfacts 提取若干关键 us-gaap 年度（FY）USD 事实。无则返回空表（不编造）。"""
    usgaap = (facts.get("facts") or {}).get("us-gaap") or {}
    out: list[FinancialFact] = []
    for label, tags in _KEY_FINANCIAL_CONCEPTS:
        fact = _latest_annual_usd(usgaap, tags)
        if fact is None:
            continue
        value, period = fact
        out.append(
            FinancialFact(
                label=label,
                value=value,
                unit="USD",
                period=period,
                source_url=source_url,
            )
        )
    return out


def _latest_annual_usd(usgaap: dict, tags: tuple[str, ...]) -> Optional[tuple[float, Optional[str]]]:
    """在候选 tag 中找到最新一笔年度（fp=FY）USD 数值。返回 (value, 'FY{year}')。"""
    for tag in tags:
        concept = usgaap.get(tag)
        if not isinstance(concept, dict):
            continue
        usd_units = (concept.get("units") or {}).get("USD")
        if not isinstance(usd_units, list):
            continue
        annual = [
            u
            for u in usd_units
            if isinstance(u, dict)
            and u.get("fp") == "FY"
            and u.get("form") in _ANNUAL_FORMS
            and u.get("val") is not None
            and u.get("fy") is not None
        ]
        if not annual:
            continue
        # 取财年最大（最新），同财年再按申报期末 'end' 取最新。
        annual.sort(key=lambda u: (u.get("fy", 0), u.get("end", "")))
        latest = annual[-1]
        try:
            value = float(latest["val"])
        except (TypeError, ValueError, KeyError):
            continue
        period = f"FY{latest['fy']}" if latest.get("fy") is not None else None
        return value, period
    return None


def get_filing_highlights(
    identity: CompanyIdentity, *, fetcher: Optional[Fetcher] = None
) -> FilingHighlights:
    """SEC 申报 + 财务亮点。CIK 动态解析；任何失败如实降级（honest note），**永不 raise**。"""
    f = _resolve_fetcher(fetcher)
    symbol = identity.symbol

    cik_int = resolve_cik(symbol, fetcher=f)
    if cik_int is None:
        # 许多 ADR 不在 company_tickers 映射中 —— 如实说明，不编造。
        return FilingHighlights(
            note=f"SEC filing data not available for {symbol} (no matching SEC filer)."
        )

    cik10 = _cik10(cik_int)

    # ── 最近申报（submissions） ──────────────────────────────────────────────
    recent_filings: list[FilingHighlight] = []
    submissions = _fetch_json(f, _SUBMISSIONS_URL.format(cik10=cik10))
    if isinstance(submissions, dict):
        for row in _iter_recent_filings(submissions):
            form = row.get("form")
            if form not in _HIGHLIGHT_FORMS:
                continue
            filed = row.get("filingDate") or ""
            url = _filing_url(cik_int, row.get("accessionNumber") or "", row.get("primaryDocument"))
            recent_filings.append(
                FilingHighlight(
                    form=form,
                    filed_date=filed,
                    url=url,
                    description=row.get("primaryDocDescription") or None,
                )
            )
            if len(recent_filings) >= _MAX_FILINGS:
                break

    # ── 关键财务（companyfacts XBRL） ────────────────────────────────────────
    facts_url = _COMPANYFACTS_URL.format(cik10=cik10)
    key_financials: list[FinancialFact] = []
    facts = _fetch_json(f, facts_url)
    if isinstance(facts, dict):
        key_financials = _extract_key_financials(facts, facts_url)

    # 两路都空 → 如实降级。
    note: Optional[str] = None
    if not recent_filings and not key_financials:
        note = f"SEC filing data could not be retrieved for {symbol}."

    return FilingHighlights(
        cik=cik10,
        recent_filings=recent_filings,
        key_financials=key_financials,
        note=note,
    )


# ===========================================================================
# Business Risks（10-K Item 1A / 20-F Item 3.D）
# ===========================================================================
# 风险章节定位（用宽松空白匹配——HTML 提取文本里空白不规则）。
#
# 真实申报里 "Item 1A. Risk Factors" / "D. Risk Factors" 会出现 *很多次*：
# 目录、正文 MD&A / Item 7 里的交叉引用（“See …”/“Refer to …”）等。
# 若简单取「最后一次命中」会落到正文末尾的交叉引用，窗口越过整章 → 抓到封面/
# 其他 Item 的加粗文本（live run 复现的 bug）。因此：
#   - START 锚点：跳过交叉引用（前缀含 see/refer/“—”/引号 等），在「真正的小节标题」
#     候选里选「向后 lookahead 内风险标题最多」者（再以最短间隔 tie-break）。
#   - 章节内按文档顺序前向收集「像风险标题的加粗句」，遇到下一个真正的 Item 边界停止，
#     并用一个宽松字符窗口 + 数量上限兜底（避免被章节内的内联交叉引用提前截断）。
_ITEM_1A_RE = re.compile(r"item\s*1a\.?\s*risk\s*factors", re.IGNORECASE)
# 20-F 的风险小节标题就是 "D. Risk Factors"（前面的 "Item 3 / Key Information" 常分散在别处）。
_ITEM_3D_RE = re.compile(r"d\.\s*risk\s*factors", re.IGNORECASE)

# 下一个「真正的」顶层 Item 边界（仅顶层；不含会被内联引用伪装成标题的子小节）。
_NEXT_ITEM_10K_RE = re.compile(r"^\s*item\s*(?:1b|1c|2|3|4)\b", re.IGNORECASE)
_NEXT_ITEM_20F_RE = re.compile(r"^\s*item\s*(?:4|4a|5)\b", re.IGNORECASE)

# 交叉引用前缀：锚点紧前若是 see/refer to/“in conjunction with”/破折号/引号 → 是引用而非标题。
_XREF_PREFIX_RE = re.compile(
    r"(?:see|refer\s+to|conjunction\s+with|—|–|\"|“|”|\bin\b)\s*[\"“]?\s*[—–-]?\s*$",
    re.IGNORECASE,
)

# 风险标题须以句末标点收尾（现代 10-K 每条风险是一句完整的加粗句）。
_TITLE_END_PUNCT_RE = re.compile(r"[.!?][\"\)’”]?$")

# 封面/样板红线：命中即**绝不**作为风险标题（电话/“fiscal year ended”/Registrant/
# Commission File/incorporated/地址邮编/“(IRS Employer”/“Securities registered”/裸日期 等）。
_COVER_PAGE_RE = re.compile(
    r"(?:telephone|fiscal\s+year\s+ended|registrant|commission\s+file|incorporated"
    r"|\bzip\b|\(irs|securities\s+registered|area\s+code|identification\s+(?:no|number)"
    r"|\bi\.r\.s\.|\bcik\b)",
    re.IGNORECASE,
)

# 类别小标题（“Risks Related to …”/“Summary of Risk Factors”/“The following …”）不是单条风险。
_CATEGORY_HEADER_RE = re.compile(
    r"^(?:risks?\s+related\s+to|summary\s+of\s+risk|risk\s+factors?\b|certain\s+"
    r"|the\s+following|other\s+risk)",
    re.IGNORECASE,
)

# START 锚点向后看的最大字符跨度（容纳 20-F “Summary of Risk Factors” 长前言后才出现首条风险）。
_RISK_LOOKAHEAD_CHARS = 16000
# 风险小节正文的宽松字符上限（兜底，配合数量上限）。
_RISK_WINDOW_CHARS = 120000


def _find_latest_annual_filing(
    submissions: dict, preferred_form: str
) -> Optional[tuple[str, str, Optional[str], Optional[str]]]:
    """找最新年报。优先 preferred_form（10-K 或 20-F），否则在年报集合里取最新。

    返回 (form, filingDate, accessionNumber, primaryDocument)。
    """
    rows = _iter_recent_filings(submissions)

    def _candidates(form_filter: tuple[str, ...]) -> list[dict]:
        return [r for r in rows if r.get("form") in form_filter]

    # 先按偏好表单，再回退到任意年报表单（10-K / 20-F）。
    for form_filter in ((preferred_form,), _ANNUAL_FORMS):
        cands = _candidates(form_filter)
        if not cands:
            continue
        # filingDate 形如 'YYYY-MM-DD'，字符串排序即时间序。
        cands.sort(key=lambda r: r.get("filingDate") or "")
        chosen = cands[-1]
        return (
            chosen.get("form"),
            chosen.get("filingDate") or "",
            chosen.get("accessionNumber"),
            chosen.get("primaryDocument"),
        )
    return None


def _looks_like_heading(text: str) -> bool:
    """判断一段文本是否像风险因素标题（保守，宁缺毋滥，避免把正文当标题）。"""
    text = _norm_ws(text)
    if not text:
        return False
    if len(text) < 12 or len(text) > 250:
        return False
    if not text[0].isalpha():
        return False
    word_count = len(text.split())
    if word_count < 3 or word_count > 35:
        return False
    return True


def _is_cover_page_text(text: str) -> bool:
    """命中封面/样板红线（电话/“fiscal year ended”/Registrant/Commission File/邮编/裸日期 等）。"""
    return bool(_COVER_PAGE_RE.search(_norm_ws(text)))


def _is_risk_title(text: str) -> bool:
    """是否为单条风险因素标题（现代 10-K/20-F：一句以句末标点收尾的完整加粗句）。

    诚实红线：**绝不**把封面样板（电话/财年/Registrant…）或类别小标题
    （“Risks Related to …”/“Summary of Risk Factors”）当作风险标题。
    """
    text = _norm_ws(text)
    if not (25 <= len(text) <= 320):
        return False
    if not text[0].isalpha():
        return False
    word_count = len(text.split())
    if word_count < 5 or word_count > 45:
        return False
    if not _TITLE_END_PUNCT_RE.search(text):
        return False  # 完整句子才是风险标题；目录/类别标题通常无句末标点。
    if _is_cover_page_text(text):
        return False  # 封面样板 —— 绝不作为风险。
    if _CATEGORY_HEADER_RE.match(text):
        return False  # 类别小标题，不是单条风险。
    return True


def _looks_like_next_item(text: str, next_item_re: re.Pattern) -> bool:
    """文本是否是下一个「真正的」顶层 Item 标题（用于前向收集时停止）。"""
    return bool(next_item_re.match(_norm_ws(text)))


def _is_bold(node) -> bool:
    """节点是否加粗（<b>/<strong> 或 style 含 font-weight:bold / 600 / 700）。"""
    name = getattr(node, "name", None)
    if name in ("b", "strong"):
        return True
    if hasattr(node, "get"):
        style = (node.get("style") or "").lower()
        if "font-weight" in style and re.search(r"font-weight\s*:\s*(bold|[6-9]00)", style):
            return True
    return False


def _summary_after(node) -> Optional[str]:
    """取加粗标题节点之后、第一段非加粗正文的首句/两句作为忠实简述。无则 None。"""
    block = node
    # 上溯到块级祖先（p/div/td/li），以便取其后续兄弟正文。
    for _ in range(6):
        parent = getattr(block, "parent", None)
        if parent is None or getattr(parent, "name", None) in ("body", "html", "[document]", None):
            break
        block = parent
        if getattr(block, "name", None) in ("p", "div", "td", "li"):
            break
    sib = block
    for _ in range(12):  # 限定向后看的步数，避免扫全文。
        sib = getattr(sib, "next_sibling", None)
        if sib is None:
            break
        get_text = getattr(sib, "get_text", None)
        text = _norm_ws(get_text(" ") if get_text else str(sib))
        if not text:
            continue
        # 紧跟另一个加粗标题 → 该风险无正文解释，summary 留空。
        if hasattr(sib, "find"):
            inner_bold = sib.find(["b", "strong"])
            if _is_bold(sib) or (inner_bold and _looks_like_heading(_norm_ws(inner_bold.get_text()))):
                return None
        return _first_sentences(text, max_sentences=2)
    return None


def _first_sentences(text: str, max_sentences: int = 2) -> str:
    """截取前 max_sentences 句（朴素按句号/问号/感叹号切）。不增删字词，仅截断。"""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    snippet = " ".join(parts[:max_sentences]).strip()
    # 控制长度上限，避免摘录过长（仍是逐字截断，不改写）。
    return snippet[:400].strip()


def _collect_bold_nodes(soup: BeautifulSoup, full_text: str) -> list[tuple[int, str, object]]:
    """收集全文加粗节点，去重(按文本)，并附其在规整全文里的首个字符位置。按位置升序返回。

    返回 [(pos, title_text, node), ...]；pos<0（定位不到）者已剔除。
    """
    info: list[tuple[int, str, object]] = []
    seen: set[str] = set()
    for node in soup.find_all(["b", "strong", "span", "div", "p"]):
        if not _is_bold(node):
            continue
        title = _norm_ws(node.get_text())
        if not title or title in seen:
            continue
        seen.add(title)
        pos = full_text.find(title)
        if pos >= 0:
            info.append((pos, title, node))
    info.sort(key=lambda x: x[0])
    return info


def _pick_section_start(
    full_text: str, start_re: re.Pattern, risk_positions: list[int]
) -> Optional[int]:
    """在所有 start 锚点里选「真正的风险小节起点」字符位置；选不出 → None。

    规则（解决真实申报里锚点出现数十次的歧义）：
      - 跳过交叉引用锚点（紧前是 see/refer to/破折号/引号 → 是“See …”引用而非小节标题）。
      - 在剩余「真标题」候选里，按其向后 lookahead 窗口内的**风险标题数量**取最多者；
        并列时取「到首条风险标题间隔最短」「位置更靠前」者。
    封面/目录锚点 lookahead 内没有风险标题 → 自然出局。
    """
    import bisect

    best_key: Optional[tuple[int, int, int]] = None
    best_pos: Optional[int] = None
    for m in start_re.finditer(full_text):
        prefix = full_text[max(0, m.start() - 24) : m.start()]
        if _XREF_PREFIX_RE.search(prefix):
            continue  # 交叉引用，不是真正的小节标题。
        sec_start = m.end()
        lo = bisect.bisect_left(risk_positions, sec_start)
        hi = bisect.bisect_right(risk_positions, sec_start + _RISK_LOOKAHEAD_CHARS)
        count = hi - lo
        if count == 0:
            continue  # 该锚点后并无风险标题 → 不是风险小节。
        gap = risk_positions[lo] - sec_start
        key = (count, -gap, -sec_start)  # 风险标题更多 > 间隔更短 > 位置更靠前。
        if best_key is None or key > best_key:
            best_key = key
            best_pos = sec_start
    return best_pos


def _extract_risk_items_from_html(
    html: str, start_re: re.Pattern, next_item_re: re.Pattern
) -> list[tuple[str, Optional[str]]]:
    """从 10-K/20-F HTML 抽取风险因素「标题(逐字) + 忠实简述」。

    思路（贴合真实申报；修复 live run 复现的「封面样板被当成风险」bug）：
      1) 解析 DOM，取规整全文文本；收集所有加粗节点及其字符位置。
      2) 用 `_pick_section_start` 在众多 start 锚点里选「真正的风险小节起点」
         （跳过 “See …” 交叉引用；按其后风险标题密度择优）。
      3) 自该起点起按文档顺序前向收集「像单条风险标题的加粗句」（`_is_risk_title`），
         遇到下一个真正的顶层 Item 边界即停；并用宽松字符窗口 + 数量上限兜底。
      4) 诚实红线：最终再过滤掉任何命中封面样板的标题。
    任一步无法可靠定位 → 返回空列表（调用方据此如实降级，绝不编造）。
    """
    soup = BeautifulSoup(html, "html.parser")
    full_text = _norm_ws(soup.get_text(" "))

    if not start_re.search(full_text):
        return []

    info = _collect_bold_nodes(soup, full_text)
    risk_positions = sorted(pos for pos, title, _ in info if _is_risk_title(title))
    if not risk_positions:
        return []  # 章节里没有任何「像风险标题」的加粗句 → 如实降级（诚实守卫）。

    sec_start = _pick_section_start(full_text, start_re, risk_positions)
    if sec_start is None:
        return []  # 无法可靠隔离风险小节 → 如实降级。

    out: list[tuple[str, Optional[str]]] = []
    started = False
    for pos, title, node in info:
        if pos < sec_start:
            continue
        if pos > sec_start + _RISK_WINDOW_CHARS:
            break  # 超出风险小节宽松窗口，停止。
        if started and _looks_like_next_item(title, next_item_re):
            break  # 已进入小节后遇到下一个真正的 Item 边界，停止。
        if _is_risk_title(title):
            started = True
            out.append((title, _summary_after(node)))
            if len(out) >= _MAX_RISK_ITEMS:
                break

    # 诚实红线：剔除任何命中封面样板的标题（双保险）。
    return [(title, summary) for title, summary in out if not _is_cover_page_text(title)]


def get_business_risks(
    identity: CompanyIdentity, *, fetcher: Optional[Fetcher] = None
) -> BusinessRisks:
    """SEC 经营风险（10-K Item 1A / 20-F Item 3.D）。逐字标题；失败如实降级，**永不 raise**。"""
    f = _resolve_fetcher(fetcher)
    symbol = identity.symbol

    cik_int = resolve_cik(symbol, fetcher=f)
    if cik_int is None:
        return BusinessRisks(
            note=f"SEC filing data not available for {symbol} (no matching SEC filer)."
        )

    submissions = _fetch_json(f, _SUBMISSIONS_URL.format(cik10=_cik10(cik_int)))
    if not isinstance(submissions, dict):
        return BusinessRisks(
            note="Could not extract risk factors from the latest filing; see source."
        )

    # ADR / 外国私人发行人报 20-F；其余报 10-K。
    preferred = "20-F" if identity.instrument == "ADR" else "10-K"
    found = _find_latest_annual_filing(submissions, preferred)
    if found is None:
        return BusinessRisks(
            note="Could not extract risk factors from the latest filing; see source."
        )
    form, filed_date, accession, primary_doc = found
    source_url = _filing_url(cik_int, accession or "", primary_doc)
    source_form = f"{form} (filed {filed_date})" if filed_date else form

    # 抓取主文档 HTML。
    try:
        html_bytes = f(source_url)
        html = html_bytes.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return BusinessRisks(
            note="Could not extract risk factors from the latest filing; see source.",
            source_url=source_url,
        )

    if form == "20-F":
        headings = _extract_risk_items_from_html(html, _ITEM_3D_RE, _NEXT_ITEM_20F_RE)
    else:
        headings = _extract_risk_items_from_html(html, _ITEM_1A_RE, _NEXT_ITEM_10K_RE)

    if not headings:
        return BusinessRisks(
            note="Could not extract risk factors from the latest filing; see source.",
            source_form=source_form,
            source_url=source_url,
        )

    items = [
        BusinessRiskItem(
            title=title,
            summary=summary,
            source_form=source_form,
            source_url=source_url,
        )
        for title, summary in headings
    ]
    return BusinessRisks(items=items, source_form=source_form, source_url=source_url)


# ===========================================================================
# FakeFetcher（测试用：canned bytes/JSON，零网络）
# ===========================================================================
class FakeFetcher:
    """离线测试 fetcher：按 URL 返回预置 bytes / JSON，或抛出预置异常。

    用法：
        fake = FakeFetcher({
            "https://www.sec.gov/files/company_tickers.json": {"0": {...}},
            submissions_url: {...},          # dict / list → 自动 json.dumps
            companyfacts_url: {...},
            doc_url: b"<html>...</html>",     # bytes → 原样返回
        })
        fake(url) -> bytes

    传入 Exception 实例/类 → 调用时抛出（验证降级路径）。
    支持 substring 匹配：键为 URL 子串即可命中（便于不在测试里拼完整 URL）。
    """

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        entry = self._lookup(url)
        if entry is None:
            raise RuntimeError(f"FakeFetcher: no canned response for {url!r}")
        if isinstance(entry, Exception):
            raise entry
        if isinstance(entry, type) and issubclass(entry, Exception):
            raise entry(f"FakeFetcher: simulated failure for {url!r}")
        if isinstance(entry, bytes):
            return entry
        if isinstance(entry, str):
            return entry.encode("utf-8")
        # dict / list → JSON bytes
        return json.dumps(entry).encode("utf-8")

    def _lookup(self, url: str) -> object:
        if url in self._responses:
            return self._responses[url]
        for key, value in self._responses.items():
            if key in url:
                return value
        return None
