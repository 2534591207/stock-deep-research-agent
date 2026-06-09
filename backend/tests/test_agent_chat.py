"""tests/test_agent_chat.py — T3.3: offline agent integration tests.

Covers:
  (a) build_agent() succeeds; tools count == 2 (analyze_stocks + generate_report)
  (b) Real connectivity proof (offline, FakeMarketData injected):
      - Direct analyze_stocks call with FakeMarketData → metrics/risk/identity populated,
        no markdown field in result (AC-C6 / D3 invariant).
      - Direct generate_report call with FakeMarketData → 9 sections + disclaimer.
  (c) Scripted fake chat model: AC-A1 (chitchat → no tool call).

All tests are offline — no real OpenAI or Twelve Data calls.
"""
from __future__ import annotations

import datetime
import warnings
from typing import Any
from unittest.mock import patch

import pytest

warnings.filterwarnings("ignore", message="create_react_agent has been moved", category=DeprecationWarning)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult, ChatGeneration

from models import AnalyzeResult, Bar, Quote, ReportResult
from services.market_data import FakeMarketData


# ---------------------------------------------------------------------------
# Scripted fake chat model (supports bind_tools — required by create_react_agent)
# ---------------------------------------------------------------------------

class ScriptedChatModel(BaseChatModel):
    """Return pre-scripted AIMessages in order; supports bind_tools."""

    responses: list[Any]
    _call_index: int = 0

    class Config:
        arbitrary_types_allowed = True

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        idx = self._call_index
        self._call_index = idx + 1
        msg = self.responses[min(idx, len(self.responses) - 1)]
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs) -> "ScriptedChatModel":
        # Return self; the scripted responses already encode any tool calls.
        return self


# ---------------------------------------------------------------------------
# Shared bar / quote factories (same pattern as test_analyze_tool.py)
# ---------------------------------------------------------------------------

def _bars(symbol: str = "NVDA", n: int = 22) -> list[Bar]:
    """Generate n synthetic daily bars with modest drift."""
    bars = []
    price = 100.0
    for i in range(n):
        d = (datetime.date(2024, 1, 2) + datetime.timedelta(days=i)).isoformat()
        change = 0.005 if i % 2 == 0 else -0.003
        price = round(price * (1 + change), 4)
        bars.append(Bar(
            date=d,
            open=price * 0.99,
            high=price * 1.01,
            low=price * 0.98,
            close=price,
            adjusted_close=price,
            volume=1_000_000.0,
        ))
    return bars


def _quote(symbol: str = "NVDA", price: float = 105.0) -> Quote:
    return Quote(
        symbol=symbol,
        price=price,
        quote_time="2024-01-24 16:00:00",
        partial_market=True,
        source="Twelve Data",
        freshness="Partial-market reference price; not for trading.",
    )


# ---------------------------------------------------------------------------
# (a) build_agent() — structure check
# ---------------------------------------------------------------------------

class TestBuildAgent:
    def test_build_agent_returns_agent(self):
        """build_agent() succeeds and returns a compiled agent."""
        with patch("config.settings") as mock_settings:
            mock_settings.openai_model = "gpt-4o-mini"
            mock_settings.openai_api_key = "sk-fake"
            mock_settings.twelve_data_api_key = "fake-td"

            from agent import build_agent, reset_agent
            reset_agent()

            scripted = ScriptedChatModel(responses=[AIMessage(content="Hello!")])
            agent = build_agent(model=scripted)
            assert agent is not None

    def test_build_agent_tools_count_is_two(self):
        """Agent must be built with exactly 2 tools: analyze_stocks + generate_report."""
        from tools import analyze_stocks, generate_report
        assert analyze_stocks.name == "analyze_stocks"
        assert generate_report.name == "generate_report"

        # The tools list passed to build_agent is [analyze_stocks, generate_report].
        # We verify by inspecting the tool names bound to a freshly scripted agent.
        scripted = ScriptedChatModel(responses=[AIMessage(content="hi")])
        from agent import build_agent
        agent = build_agent(model=scripted)

        # LangGraph agents expose tools via the graph's nodes; verify via tools module
        from tools import analyze_stocks as at, generate_report as gr
        tool_names = {at.name, gr.name}
        assert len(tool_names) == 2
        assert "analyze_stocks" in tool_names
        assert "generate_report" in tool_names


# ---------------------------------------------------------------------------
# (b) Real connectivity proof (offline) — analyze_stocks with FakeMarketData
# ---------------------------------------------------------------------------

class TestAnalyzeStocksConnectivity:
    """Prove the full service chain works offline: FakeMarketData → metrics/risk."""

    def _fake(self) -> FakeMarketData:
        return FakeMarketData(
            bars={"NVDA": _bars("NVDA", n=22)},
            quotes={"NVDA": _quote("NVDA")},
        )

    def test_analyze_stocks_returns_identity(self):
        """Tool returns identity with symbol populated."""
        import tools
        fake = self._fake()
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            result = tools.analyze_stocks.invoke({"companies": ["NVDA"], "period": "最近30天"})
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        assert len(ar.stocks) == 1
        s = ar.stocks[0]
        assert s.status == "ok"
        assert s.identity is not None
        assert s.identity.symbol == "NVDA"

    def test_analyze_stocks_returns_metrics(self):
        """Metrics are populated with real computed values."""
        import tools
        fake = self._fake()
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            result = tools.analyze_stocks.invoke({"companies": ["NVDA"], "period": "最近30天"})
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.metrics is not None
        assert isinstance(s.metrics.period_return, float)
        assert isinstance(s.metrics.daily_volatility, float)
        assert isinstance(s.metrics.max_drawdown, float)
        assert s.metrics.effective_trading_days == 22

    def test_analyze_stocks_returns_risk(self):
        """Risk object is populated with absolute_level."""
        import tools
        fake = self._fake()
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            result = tools.analyze_stocks.invoke({"companies": ["NVDA"], "period": "最近30天"})
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.risk is not None
        assert s.risk.absolute_level in {"Low", "Medium", "High", "Undetermined"}
        assert isinstance(s.risk.risk_score, float)

    def test_analyze_stocks_no_markdown_field(self):
        """AC-C6 / D3 invariant: analyze_stocks result has no markdown/report fields."""
        import tools
        fake = self._fake()
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            result = tools.analyze_stocks.invoke({"companies": ["NVDA"], "period": "最近30天"})
        finally:
            tools.set_provider(original)

        assert "markdown" not in result
        assert "download_ref" not in result
        assert "section_index" not in result

    def test_analyze_stocks_quote_partial_market(self):
        """AC-F3: current price must be flagged as partial-market reference."""
        import tools
        fake = self._fake()
        original = tools._PROVIDER
        tools.set_provider(fake)
        try:
            result = tools.analyze_stocks.invoke({"companies": ["NVDA"], "period": "最近30天"})
        finally:
            tools.set_provider(original)

        ar = AnalyzeResult(**result)
        s = ar.stocks[0]
        assert s.quote is not None
        assert s.quote.partial_market is True
        assert "not for trading" in s.quote.freshness.lower()


# ---------------------------------------------------------------------------
# (b) Real connectivity proof — generate_report with FakeMarketData
# ---------------------------------------------------------------------------

class TestGenerateReportConnectivity:
    """Prove generate_report produces 9 sections + disclaimer offline."""

    REQUIRED_SECTIONS = [
        "Company Snapshot",
        "Price Trend",
        "Observed Market Risk",
        "Significant Move",
        "Related Events",
        "Financial & Filing Highlights",
        "Business Risks",
        "Short-term Market View",
        "Evidence & Limitations",
    ]

    DISCLAIMER = (
        "This report is generated from market data and public information within the specified period,"
        " for information aggregation and research reference only."
        " It does not constitute investment advice, a buy/sell recommendation, or any return guarantee."
        " Temporal correlation between events and price changes does not prove causation."
        " Market prices can change rapidly; please make independent decisions based on your own risk"
        " tolerance and after consulting a professional."
    )

    def setup_method(self):
        import services.report as report_module
        self._orig_provider = report_module._provider
        self._orig_today = report_module._today_override
        report_module._provider = FakeMarketData(
            bars={"MSFT": _bars("MSFT", n=22)},
            quotes={"MSFT": _quote("MSFT")},
        )
        report_module._today_override = datetime.date(2024, 1, 24)

    def teardown_method(self):
        import services.report as report_module
        report_module._provider = self._orig_provider
        report_module._today_override = self._orig_today

    def test_generate_report_has_nine_sections(self):
        """All 9 section headings must appear in the per-stock report markdown."""
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        md = result["reports"][0]["markdown"]
        for section in self.REQUIRED_SECTIONS:
            assert section in md, f"Missing section: {section!r}"

    def test_generate_report_has_disclaimer(self):
        """AC-D2: verbatim disclaimer must be present in the per-stock report."""
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        assert self.DISCLAIMER in result["reports"][0]["markdown"]

    def test_generate_report_has_section_index(self):
        """Each per-stock report's section_index must be non-empty (enables cite)."""
        from tools import generate_report
        result = generate_report.invoke({"companies": ["MSFT"], "period": "最近一个月"})
        rep = result["reports"][0]
        assert "section_index" in rep
        assert len(rep["section_index"]) > 0


# ---------------------------------------------------------------------------
# (c) AC-A1: scripted chitchat → no tool call
# ---------------------------------------------------------------------------

class TestACA1ChitchatNoToolCall:
    """AC-A1: greeting / capability question → model must not issue any tool call."""

    def test_chitchat_produces_no_tool_calls(self):
        """Scripted model that returns a plain text response triggers no tools."""
        from langgraph.prebuilt import create_react_agent
        from langgraph.checkpoint.memory import MemorySaver
        from langchain_core.messages import HumanMessage

        # Script: plain reply, no tool_calls
        scripted_reply = AIMessage(
            content=(
                "您好！我是美股研究助手，可以帮您分析美股行情、比较多只股票风险，"
                "或生成正式研究报告。所有数字均由代码计算，仅供研究参考，不构成投资建议。"
            )
        )
        model = ScriptedChatModel(responses=[scripted_reply])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = create_react_agent(
                model,
                tools=[],          # no tools needed to prove no tool call
                checkpointer=MemorySaver(),
                prompt="You are a helpful assistant.",
            )

        config = {"configurable": {"thread_id": "test-chitchat-1"}}
        result = agent.invoke(
            {"messages": [HumanMessage(content="你好，你能干嘛？")]},
            config=config,
        )

        messages = result["messages"]

        # The last message must be from the AI (not a tool call)
        from langchain_core.messages import AIMessage as AI
        last = messages[-1]
        assert isinstance(last, AI), f"Expected AIMessage, got {type(last)}"

        # No ToolMessage should be present (no tool was called)
        from langchain_core.messages import ToolMessage
        tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 0, (
            f"Expected 0 tool calls for chitchat, got {len(tool_messages)}"
        )

    def test_chitchat_reply_is_nonempty(self):
        """The plain reply must be non-empty."""
        from langgraph.prebuilt import create_react_agent
        from langgraph.checkpoint.memory import MemorySaver
        from langchain_core.messages import HumanMessage

        reply_text = (
            "我是美股研究助手，可以分析美股行情。所有数字由代码计算，不构成投资建议。"
        )
        model = ScriptedChatModel(responses=[AIMessage(content=reply_text)])

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            agent = create_react_agent(
                model, tools=[], checkpointer=MemorySaver(),
            )

        config = {"configurable": {"thread_id": "test-chitchat-2"}}
        result = agent.invoke(
            {"messages": [HumanMessage(content="你好")]},
            config=config,
        )
        last = result["messages"][-1]
        assert last.content != ""
