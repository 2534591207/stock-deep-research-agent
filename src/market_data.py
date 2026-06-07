from __future__ import annotations

import math
import os
import random
from datetime import date, timedelta

import httpx

from .models import Company, TimeRange


class MarketDataError(RuntimeError):
    pass


class MarketDataProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("TWELVE_DATA_API_KEY", "").strip()

    def get_history(self, company: Company, period: TimeRange) -> dict:
        if self.api_key:
            return self._get_twelve_data_history(company, period)
        return self._get_demo_history(company, period)

    def _get_twelve_data_history(self, company: Company, period: TimeRange) -> dict:
        params = {
            "symbol": company.symbol,
            "interval": "1day",
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
            "apikey": self.api_key,
        }
        response = httpx.get("https://api.twelvedata.com/time_series", params=params, timeout=25)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise MarketDataError(payload.get("message", "Twelve Data 返回错误"))
        values = payload.get("values", [])
        if len(values) < 2:
            raise MarketDataError(f"{company.symbol} 返回的历史数据不足")
        bars = [
            {
                "date": item["datetime"],
                "open": float(item["open"]),
                "high": float(item["high"]),
                "low": float(item["low"]),
                "close": float(item["close"]),
                "volume": int(item["volume"]) if item.get("volume") else None,
            }
            for item in reversed(values)
        ]
        return {
            "bars": bars,
            "source": "Twelve Data",
            "freshness": "已完成交易日日线",
            "is_demo": False,
        }

    def _get_demo_history(self, company: Company, period: TimeRange) -> dict:
        seed = sum(ord(char) for char in company.symbol)
        rng = random.Random(seed)
        dates: list[date] = []
        cursor = period.start_date
        while cursor <= period.end_date:
            if cursor.weekday() < 5:
                dates.append(cursor)
            cursor += timedelta(days=1)
        if len(dates) < 2:
            raise MarketDataError("分析时间范围内没有足够交易日")

        price = 70 + seed % 170
        bars = []
        for index, trading_date in enumerate(dates):
            drift = math.sin(index / 5 + seed) * 0.009
            shock = rng.uniform(-0.026, 0.026)
            open_price = price
            close_price = max(1, price * (1 + drift + shock))
            high = max(open_price, close_price) * (1 + rng.uniform(0.002, 0.016))
            low = min(open_price, close_price) * (1 - rng.uniform(0.002, 0.016))
            bars.append(
                {
                    "date": trading_date.isoformat(),
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close_price, 2),
                    "volume": rng.randint(8_000_000, 90_000_000),
                }
            )
            price = close_price
        return {
            "bars": bars,
            "source": "本地演示快照生成器",
            "freshness": "演示数据，配置 TWELVE_DATA_API_KEY 后使用真实行情",
            "is_demo": True,
        }
