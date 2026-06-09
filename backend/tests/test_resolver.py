"""tests/test_resolver.py — resolver 验收测试。

AC-H1: MSFT / AMZN（非固定样本）→ found
AC-H4: 多匹配输入 → ambiguous（带候选列表）
AC-H5: 阿里巴巴 → found: BABA / NYSE / ADR（绝不混 9988.HK）
AC-H6: 小米 → none（未找到美股标的，不编码）
英伟达 → found: NVDA（中文别名通道）
"""
import pytest
from services.resolver import resolve


class TestTickerDirectPassthrough:
    """AC-H1：精确 ticker 直通，证明不依赖固定股票。"""

    def test_msft_found(self):
        result = resolve("MSFT")
        assert result.status == "found"
        assert result.identity is not None
        assert result.identity.symbol == "MSFT"
        assert result.identity.exchange == "NASDAQ"
        assert result.identity.instrument == "common"
        assert result.query == "MSFT"

    def test_amzn_found(self):
        result = resolve("AMZN")
        assert result.status == "found"
        assert result.identity is not None
        assert result.identity.symbol == "AMZN"
        assert result.identity.exchange == "NASDAQ"
        assert result.identity.instrument == "common"

    def test_ticker_case_insensitive(self):
        """ticker 匹配大小写不敏感。"""
        result = resolve("msft")
        assert result.status == "found"
        assert result.identity.symbol == "MSFT"


class TestChineseAliasChannel:
    """AC-H5：中文别名通道——阿里巴巴 → BABA/NYSE/ADR，绝不混 9988.HK。"""

    def test_alibaba_chinese_found(self):
        result = resolve("阿里巴巴")
        assert result.status == "found"
        assert result.identity is not None
        assert result.identity.symbol == "BABA"
        assert result.identity.exchange == "NYSE"
        assert result.identity.instrument == "ADR"
        assert result.query == "阿里巴巴"

    def test_alibaba_not_hkex(self):
        """严格断言：不返回港股 9988.HK。"""
        result = resolve("阿里巴巴")
        assert result.identity.symbol != "9988"
        assert result.identity.exchange != "HKEX"

    def test_nvidia_chinese_found(self):
        """英伟达 → NVDA（中文别名通道）。"""
        result = resolve("英伟达")
        assert result.status == "found"
        assert result.identity is not None
        assert result.identity.symbol == "NVDA"
        assert result.identity.exchange == "NASDAQ"
        assert result.identity.instrument == "common"


class TestNoneResolution:
    """AC-H6：未找到美股标的 → none，不编码。"""

    def test_xiaomi_none(self):
        """小米未在美股 catalog → none。"""
        result = resolve("小米")
        assert result.status == "none"
        assert result.identity is None
        assert result.query == "小米"

    def test_unknown_ticker_none(self):
        """随机无意义 ticker → none。"""
        result = resolve("ZZZZNOTEXIST")
        assert result.status == "none"
        assert result.identity is None

    def test_empty_string_none(self):
        """空字符串 → none。"""
        result = resolve("")
        assert result.status == "none"


class TestAmbiguousResolution:
    """AC-H4：多匹配输入 → ambiguous，带候选列表，供 agent 只问一个澄清问题。"""

    def test_corporation_ambiguous(self):
        """'Corporation' 匹配多个 catalog 条目（NVIDIA/Intel/Microsoft/Costco）→ ambiguous。"""
        result = resolve("Corporation")
        assert result.status == "ambiguous"
        assert result.identity is None
        assert result.candidates is not None
        assert len(result.candidates) >= 2, "ambiguous 应返回至少 2 个候选"
        assert result.query == "Corporation"

    def test_ambiguous_candidates_are_symbols(self):
        """candidates 列表内容应为 symbol 字符串（供 agent 展示）。"""
        result = resolve("Corporation")
        assert result.status == "ambiguous"
        # 每个候选应是非空字符串（symbol）
        for sym in result.candidates:
            assert isinstance(sym, str)
            assert len(sym) > 0


class TestStatusMutualExclusion:
    """严格区分 ambiguous 与 none（不得混用）。"""

    def test_none_has_no_candidates(self):
        result = resolve("小米")
        assert result.status == "none"
        # none 状态下 candidates 应为 None 或空
        assert not result.candidates

    def test_found_has_identity_not_candidates(self):
        result = resolve("MSFT")
        assert result.status == "found"
        assert result.identity is not None
        assert not result.candidates

    def test_ambiguous_has_candidates_not_identity(self):
        result = resolve("Corporation")
        assert result.status == "ambiguous"
        assert result.identity is None
        assert result.candidates is not None and len(result.candidates) >= 2
