from __future__ import annotations

import re

from .models import Company


COMPANIES = [
    Company(name="NVIDIA Corporation", symbol="NVDA", exchange="NASDAQ", aliases=["英伟达", "nvidia", "nvda"]),
    Company(name="Alibaba Group Holding Limited", symbol="BABA", exchange="NYSE", aliases=["阿里巴巴", "alibaba", "baba"]),
    Company(name="Intel Corporation", symbol="INTC", exchange="NASDAQ", aliases=["英特尔", "intel", "intc"]),
    Company(name="Microsoft Corporation", symbol="MSFT", exchange="NASDAQ", aliases=["微软", "microsoft", "msft"]),
    Company(name="Apple Inc.", symbol="AAPL", exchange="NASDAQ", aliases=["苹果", "apple", "aapl"]),
    Company(name="Amazon.com, Inc.", symbol="AMZN", exchange="NASDAQ", aliases=["亚马逊", "amazon", "amzn"]),
    Company(name="Tesla, Inc.", symbol="TSLA", exchange="NASDAQ", aliases=["特斯拉", "tesla", "tsla"]),
    Company(name="Advanced Micro Devices, Inc.", symbol="AMD", exchange="NASDAQ", aliases=["超威半导体", "amd"]),
    Company(name="Meta Platforms, Inc.", symbol="META", exchange="NASDAQ", aliases=["meta", "脸书"]),
    Company(name="Alphabet Inc.", symbol="GOOGL", exchange="NASDAQ", aliases=["谷歌", "google", "alphabet", "googl"]),
]


def resolve_companies(text: str, limit: int = 3) -> list[Company]:
    lowered = text.lower()
    matches: list[Company] = []
    for company in COMPANIES:
        if any(alias.lower() in lowered for alias in company.aliases):
            matches.append(company)

    if not matches:
        symbols = re.findall(r"\b[A-Z]{1,5}\b", text)
        by_symbol = {company.symbol: company for company in COMPANIES}
        matches = [by_symbol[symbol] for symbol in symbols if symbol in by_symbol]

    unique: list[Company] = []
    seen: set[str] = set()
    for company in matches:
        if company.symbol not in seen:
            unique.append(company)
            seen.add(company.symbol)
    return unique[:limit]
