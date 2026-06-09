"""services/compare.py — 横向比较与相对排名（纯函数，无 IO）。

rank(stocks) -> RankingResult | None

规则：
- 可排名 = status=="ok" AND risk 非 None AND absolute_level != "Undetermined"
- 按 risk_score 降序排列；risk_score 相等 → 并列同名次（1,1,3 式）
- 可排名数 < 2 → 返回 None（AC-C3）
- absolute_level=="Undetermined" → 进 excluded，不进 items（AC-C4）
- caveat 含「仅限本次所选股票与区间」（AC-C5）
"""
from __future__ import annotations

from models import RankingItem, RankingResult, StockAnalysis

_CAVEAT = (
    "Relative ranking is limited to the selected stocks and this analysis period only."
    " 仅限本次所选股票与区间。"
)


def rank(stocks: list[StockAnalysis]) -> RankingResult | None:
    """对 StockAnalysis 列表进行风险排名，可排名数 < 2 时返回 None。"""
    rankable: list[StockAnalysis] = []
    excluded: list[str] = []

    for s in stocks:
        symbol = s.identity.symbol if s.identity else "UNKNOWN"
        if s.status == "ok" and s.risk is not None:
            if s.risk.absolute_level == "Undetermined":
                excluded.append(symbol)
            else:
                rankable.append(s)
        # status != "ok" or risk is None → silently skip (not excluded list)

    if len(rankable) < 2:
        return None

    # 按 risk_score 降序排列
    sorted_stocks = sorted(rankable, key=lambda s: s.risk.risk_score, reverse=True)

    items: list[RankingItem] = []
    current_rank = 1
    for i, s in enumerate(sorted_stocks):
        symbol = s.identity.symbol if s.identity else "UNKNOWN"
        if i > 0:
            prev_score = sorted_stocks[i - 1].risk.risk_score
            if s.risk.risk_score < prev_score:
                current_rank = i + 1
        items.append(RankingItem(symbol=symbol, rank=current_rank, risk_score=s.risk.risk_score))

    return RankingResult(items=items, excluded=excluded, caveat=_CAVEAT)
