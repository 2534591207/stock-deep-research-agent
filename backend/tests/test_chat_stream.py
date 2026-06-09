"""tests/test_chat_stream.py — POST /chat/stream NDJSON live progress + build_report sink.

Two layers, fully offline (no real network / OpenAI):

  (1) HTTP layer — POST /chat/stream via Starlette TestClient streaming:
      - A scripted fake LLM emits a generate_report tool call against fake
        market-data / news / SEC providers; the stream must carry per-stock
        stage events (incl. a "__batch__" "compare" event) and end with a single
        {"type":"done", ...} line whose reports list has correct download_refs.
      - A pure-chat turn (no tool call) yields a done event with reply set and
        reports null, and NO stage events.

  (2) Unit layer — build_report with a contextvar sink set collects the 10 stage
      ids in order for a 1-stock and a 2-stock run (fake provider + fake news/SEC).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from models import (
    Bar,
    BusinessRiskItem,
    BusinessRisks,
    CompanyIdentity,
    EventEvidence,
    FilingHighlight,
    FilingHighlights,
    FinancialFact,
    NewsItem,
    Quote,
)
from services.market_data import FakeMarketData
from services.progress import report_progress


# ---------------------------------------------------------------------------
# Bar / quote / provider factories (catalog-known symbols MSFT, NVDA)
# ---------------------------------------------------------------------------

def _bars(symbol: str = "MSFT") -> list[Bar]:
    prices = [
        100.0, 101.5, 103.0, 102.0, 104.5, 103.5, 105.0, 107.0, 106.0, 108.0,
        109.0, 107.5, 110.0, 111.0, 109.5, 112.0, 113.0, 114.0, 112.5, 115.0,
    ]
    bars = []
    for i, p in enumerate(prices):
        day = f"2024-01-{i + 2:02d}"
        bars.append(Bar(
            date=day, open=p - 0.5, high=p + 1.0, low=p - 1.0,
            close=p, adjusted_close=p, volume=1_000_000.0,
        ))
    return bars


def _quote(symbol: str = "MSFT") -> Quote:
    return Quote(
        symbol=symbol, price=115.0, quote_time="2024-01-21 16:00:00",
        partial_market=True, source="Yahoo Finance",
        freshness="Partial-market reference price; not for trading.",
    )


def _fake_provider(symbols: list[str]) -> FakeMarketData:
    return FakeMarketData(
        bars={s: _bars(s) for s in symbols},
        quotes={s: _quote(s) for s in symbols},
    )


# ---------------------------------------------------------------------------
# Deterministic bonus-section fakes (news / SEC) — same contract as test_report.
# ---------------------------------------------------------------------------

def _fake_news_collector(identity: CompanyIdentity, significant_moves):
    return [
        EventEvidence(
            date="2024-01-09", pct_move=0.0312, direction="up",
            attribution_confidence="Low",
            news=[NewsItem(
                title=f"{identity.name} reports quarterly results",
                url="https://news.example.com/earnings", source="example.com",
                published_date="2024-01-09",
                explanation="Article reports the company's quarterly results.",
            )],
        ),
    ]


class _FakeSecProvider:
    def get_filing_highlights(self, identity: CompanyIdentity) -> FilingHighlights:
        return FilingHighlights(
            cik="0000789019",
            recent_filings=[FilingHighlight(
                form="10-K", filed_date="2023-07-27",
                url="https://www.sec.gov/Archives/edgar/data/789019/10k.htm",
                description="Annual report",
            )],
            key_financials=[FinancialFact(
                label="Revenue", value=211915000000.0, unit="USD", period="FY2023",
                source_url="https://data.sec.gov/x.json",
            )],
        )

    def get_business_risks(self, identity: CompanyIdentity) -> BusinessRisks:
        src = "https://www.sec.gov/Archives/edgar/data/789019/10k.htm"
        return BusinessRisks(
            source_form="10-K (filed 2023-07-27)", source_url=src,
            items=[BusinessRiskItem(
                title="We face intense competition across our businesses.",
                summary=None, source_form="10-K", source_url=src,
            )],
        )


@pytest.fixture()
def _report_fakes():
    """Wire services.report to deterministic provider/news/SEC fakes + stub image host."""
    import services.report as report_module
    import services.image_host as image_host

    orig = (
        report_module._provider, report_module._today_override,
        report_module._news_collector, report_module._sec_provider,
        image_host.upload_png,
    )
    report_module._today_override = date(2024, 1, 21)
    report_module._news_collector = _fake_news_collector
    report_module._sec_provider = _FakeSecProvider()
    image_host.upload_png = lambda data, dest_filename, settings, *, client=None: None
    try:
        yield report_module
    finally:
        (report_module._provider, report_module._today_override,
         report_module._news_collector, report_module._sec_provider,
         image_host.upload_png) = orig


# ---------------------------------------------------------------------------
# (2) Unit layer — build_report emits the 10 stage ids in order via the sink.
# ---------------------------------------------------------------------------

EXPECTED_PER_STOCK_LOOP1 = ["identify", "market_data", "metrics", "risk"]
EXPECTED_PER_STOCK_LOOP2 = ["chart", "events", "filings", "risk_factors", "assemble"]


class TestBuildReportSink:
    def _collect(self, symbols):
        from services.report import build_report
        events: list[dict] = []
        token = report_progress.set(lambda ev: events.append(ev))
        try:
            build_report(symbols, "最近一个月", _fake_provider(symbols), today=date(2024, 1, 21))
        finally:
            report_progress.reset(token)
        return events

    def test_single_stock_collects_ten_stage_ids_in_order(self, _report_fakes):
        events = self._collect(["MSFT"])
        # Only "start" events define ordering; "done" mirror them.
        starts = [(e["symbol"], e["stage"]) for e in events
                  if e["type"] == "stage" and e["status"] == "start"]
        expected = (
            [("MSFT", s) for s in EXPECTED_PER_STOCK_LOOP1]
            + [("__batch__", "compare")]
            + [("MSFT", s) for s in EXPECTED_PER_STOCK_LOOP2]
        )
        assert starts == expected
        # Every start has a matching done (no errors in the happy path).
        dones = [(e["symbol"], e["stage"]) for e in events
                 if e["type"] == "stage" and e["status"] == "done"]
        assert dones == expected

    def test_two_stock_collects_stage_ids_in_order(self, _report_fakes):
        events = self._collect(["MSFT", "NVDA"])
        starts = [(e["symbol"], e["stage"]) for e in events
                  if e["type"] == "stage" and e["status"] == "start"]
        expected = (
            [("MSFT", s) for s in EXPECTED_PER_STOCK_LOOP1]
            + [("NVDA", s) for s in EXPECTED_PER_STOCK_LOOP1]
            + [("__batch__", "compare")]
            + [("MSFT", s) for s in EXPECTED_PER_STOCK_LOOP2]
            + [("NVDA", s) for s in EXPECTED_PER_STOCK_LOOP2]
        )
        assert starts == expected

    def test_no_sink_is_silent_no_op(self, _report_fakes):
        """build_report without a sink set must not raise and returns normally."""
        from services.report import build_report
        # Ensure no sink is set in this context.
        assert report_progress.get() is None
        result = build_report(["MSFT"], "最近一个月", _fake_provider(["MSFT"]),
                              today=date(2024, 1, 21))
        assert len(result.reports) == 1


# ---------------------------------------------------------------------------
# (1) HTTP layer — POST /chat/stream
# ---------------------------------------------------------------------------

def _per_stock_payload_from_real_build(symbols):
    """Run the real build_report (with fakes wired by the caller) and return the
    generate_report tool output dict, so the ToolMessage mirrors production."""
    from services.report import build_report
    result = build_report(symbols, "最近一个月", _fake_provider(symbols),
                          today=date(2024, 1, 21))
    return result.model_dump()


class _ScriptedReportAgent:
    """Fake compiled agent whose .invoke runs the REAL build_report (so the sink
    fires) then returns a message list containing the generate_report ToolMessage
    and a final AIMessage — mirroring the production ReAct trace shape."""

    def __init__(self, symbols, reply):
        self._symbols = symbols
        self._reply = reply

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        # Running build_report here (inside the worker thread the endpoint spawns)
        # exercises the contextvar sink end-to-end.
        payload = _per_stock_payload_from_real_build(self._symbols)
        return {"messages": [
            HumanMessage(content="report please"),
            AIMessage(content=""),
            ToolMessage(content=json.dumps(payload), tool_call_id="call_report_1"),
            AIMessage(content=self._reply),
        ]}


class _PureChatAgent:
    """Fake agent that returns a plain AIMessage with no tool call."""

    def __init__(self, reply):
        self._reply = reply

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        return {"messages": [
            HumanMessage(content="hi"),
            AIMessage(content=self._reply),
        ]}


@pytest.fixture()
def app_module():
    with patch("app.require_keys", return_value=None):
        import app as app_module
        saved = dict(app_module._report_store)
        app_module._report_store.clear()
        try:
            yield app_module
        finally:
            app_module._report_store.clear()
            app_module._report_store.update(saved)


def _stream_lines(client, body):
    with client.stream("POST", "/chat/stream", json=body) as r:
        assert r.status_code == 200
        return [json.loads(line) for line in r.iter_lines() if line]


class TestChatStreamReportTurn:
    def test_stage_events_and_done_with_reports(self, app_module, _report_fakes):
        symbols = ["MSFT", "NVDA"]
        agent = _ScriptedReportAgent(symbols, reply="Two reports ready.")
        sid = "s-stream-report"
        with patch.object(app_module, "_get_agent", return_value=agent):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            lines = _stream_lines(client, {"session_id": sid, "message": "report please"})

        stage_events = [l for l in lines if l.get("type") == "stage"]
        # (a) per-stock stage events for each stock, plus a __batch__ compare event.
        for sym in symbols:
            stages_for = {e["stage"] for e in stage_events if e["symbol"] == sym}
            for expected in EXPECTED_PER_STOCK_LOOP1 + EXPECTED_PER_STOCK_LOOP2:
                assert expected in stages_for, f"missing {expected} for {sym}"
        assert any(e["symbol"] == "__batch__" and e["stage"] == "compare"
                   for e in stage_events)

        # (b) the LAST line is the done event with reports populated.
        done = lines[-1]
        assert done["type"] == "done"
        assert done["reply"] == "Two reports ready."
        assert done["reports"] is not None
        got = {r["symbol"]: r["download_ref"] for r in done["reports"]}
        assert set(got) == {"MSFT", "NVDA"}
        for r in done["reports"]:
            assert r["download_ref"] == f"/report/{sid}/{r['report_id']}"
            assert set(r) == {"report_id", "title", "symbol", "download_ref"}

    def test_single_stock_stream(self, app_module, _report_fakes):
        agent = _ScriptedReportAgent(["MSFT"], reply="One report ready.")
        sid = "s-stream-one"
        with patch.object(app_module, "_get_agent", return_value=agent):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            lines = _stream_lines(client, {"session_id": sid, "message": "report MSFT"})
        stage_events = [l for l in lines if l.get("type") == "stage"]
        assert any(e["symbol"] == "__batch__" and e["stage"] == "compare"
                   for e in stage_events)
        done = lines[-1]
        assert done["type"] == "done"
        assert len(done["reports"]) == 1
        assert done["reports"][0]["symbol"] == "MSFT"


class TestChatTwoStockSingleCall:
    """A single generate_report call with 2 stocks (real build_report) must
    surface BOTH per-stock reports and carry the cross-stock §3 relative rank."""

    def test_one_call_two_stocks_lists_two_with_cross_rank(self, app_module, _report_fakes):
        symbols = ["MSFT", "NVDA"]
        sid = "s-two-one-call"
        # ONE generate_report ToolMessage covering BOTH stocks (the correct shape).
        agent = _ScriptedReportAgent(symbols, reply="已各生成一份。")
        with patch.object(app_module, "_get_agent", return_value=agent):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            chat_resp = client.post(
                "/chat", json={"session_id": sid, "message": "report MSFT and NVDA"}
            )
            list_resp = client.get(f"/report/{sid}")
            msft_resp = client.get(f"/report/{sid}/MSFT-{_batch_hash(chat_resp)}")

        body = chat_resp.json()
        # /chat reports has 2 with correct download_refs.
        assert len(body["reports"]) == 2
        assert {r["symbol"] for r in body["reports"]} == {"MSFT", "NVDA"}
        for r in body["reports"]:
            assert r["download_ref"] == f"/report/{sid}/{r['report_id']}"
        # GET /report/{sid} lists 2.
        assert len(list_resp.json()["reports"]) == 2
        # Cross-stock §3 relative rank present (names the batch peers).
        assert msft_resp.status_code == 200
        assert "within this batch" in msft_resp.text
        assert "NVDA" in msft_resp.text


def _batch_hash(chat_resp) -> str:
    """Extract the 8-hex batch hash from a returned MSFT report_id (MSFT-<hash>)."""
    for r in chat_resp.json()["reports"]:
        if r["symbol"] == "MSFT":
            return r["report_id"].split("-", 1)[1]
    raise AssertionError("no MSFT report in response")


class _DocEmbedder:
    def _vec(self, t):
        t = t.lower()
        return [float("risk" in t), float("revenue" in t)]

    def embed_documents(self, chunks):
        return [self._vec(c) for c in chunks]

    def embed_query(self, q):
        return self._vec(q)


class _DocLLM:
    def invoke(self, messages):
        class _R:
            content = "这是一份财报，涉及营收与风险。"

        return _R()


class _ScriptedDocAgent:
    """Fake agent whose .invoke runs the REAL analyze_document tool (so the
    __doc__ stage events fire through the contextvar sink) and returns a trace
    with the tool ToolMessage + a final AIMessage. Mirrors a document turn."""

    def __init__(self, reply):
        self._reply = reply

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        import json as _json

        import tools as _tools

        out = _tools.analyze_document.invoke({"question": "分析这个财报"})
        return {"messages": [
            HumanMessage(content="分析这个财报"),
            AIMessage(content=""),
            ToolMessage(content=_json.dumps(out), tool_call_id="call_doc_1"),
            AIMessage(content=self._reply),
        ]}


class TestChatStreamDocumentTurn:
    """A document turn streams __doc__ stages then a done event with reports null."""

    def test_doc_stages_then_done_null_reports(self, app_module):
        from services import doc_store
        from services import document as docmod

        sid = "s-doc-stream"
        text = (
            "Revenue grew strongly this period.\n\n"
            "Risk factors include intense competition and regulation."
        )
        doc = docmod.build_uploaded_doc(text.encode("utf-8"), "fin.txt",
                                        embedder=_DocEmbedder())
        doc_store.clear()
        doc_store.put_document(sid, doc)

        import tools as _tools
        _tools.set_doc_embedder(_DocEmbedder())
        _tools.set_doc_llm(_DocLLM())
        agent = _ScriptedDocAgent(reply="这份文件是财报；其主要风险为竞争与监管。")
        try:
            with patch.object(app_module, "_get_agent", return_value=agent):
                client = TestClient(app_module.app, raise_server_exceptions=False)
                lines = _stream_lines(
                    client, {"session_id": sid, "message": "分析这个财报"}
                )
        finally:
            _tools.set_doc_embedder(None)
            _tools.set_doc_llm(None)
            doc_store.clear()

        stage_events = [l for l in lines if l.get("type") == "stage"]
        doc_stages = {e["stage"] for e in stage_events if e["symbol"] == "__doc__"}
        for expected in ("doc_load", "doc_parse", "doc_locate", "doc_summarize"):
            assert expected in doc_stages, f"missing {expected}"

        done = lines[-1]
        assert done["type"] == "done"
        assert done["reply"] == "这份文件是财报；其主要风险为竞争与监管。"
        # Document turn → reports null (report store untouched).
        assert done["reports"] is None


class TestChatStreamPureChat:
    def test_pure_chat_done_with_null_reports_no_stages(self, app_module):
        agent = _PureChatAgent(reply="Hello, I can analyze US stocks.")
        with patch.object(app_module, "_get_agent", return_value=agent):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            lines = _stream_lines(client, {"session_id": "s-chat", "message": "hi"})

        # (c) no stage events, and the done event has reply + reports null.
        assert not [l for l in lines if l.get("type") == "stage"]
        done = lines[-1]
        assert done["type"] == "done"
        assert done["reply"] == "Hello, I can analyze US stocks."
        assert done["reports"] is None


# ---------------------------------------------------------------------------
# Token streaming — a streaming-capable fake model driven through the REAL
# create_react_agent so the LLM's on_llm_new_token callback fires on the worker
# thread, pushing {"type":"token",...} events onto the SAME queue as stage events.
# ---------------------------------------------------------------------------

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402


class _StreamingFakeChatModel(BaseChatModel):
    """A minimal streaming-capable fake chat model.

    Mirrors ChatOpenAI(streaming=True): each ``_generate`` emits the reply's
    space-separated tokens via run_manager.on_llm_new_token (so attached
    callbacks fire during a normal .invoke()), then returns the full AIMessage.
    Used through the REAL create_react_agent so the token-streaming path in
    /chat/stream is exercised end-to-end. bind_tools() is a no-op (this fake
    never emits tool calls — it produces a single natural-language answer).
    """

    def __init__(self, replies, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, "_idx", 0)
        object.__setattr__(self, "_replies", list(replies))

    @property
    def _llm_type(self) -> str:
        return "streaming-fake-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        i = self._idx
        object.__setattr__(self, "_idx", i + 1)
        text = self._replies[i]
        if run_manager is not None:
            for word in text.split(" "):
                run_manager.on_llm_new_token(word)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    def bind_tools(self, tools, **kwargs):  # react agent calls bind_tools
        return self


class TestChatStreamTokenStreaming:
    def test_token_events_then_done_with_full_reply(self, app_module):
        from agent import build_agent

        reply = "Hello I can analyze US stocks"
        model = _StreamingFakeChatModel([reply])
        agent = build_agent(model=model)
        with patch.object(app_module, "_get_agent", return_value=agent):
            client = TestClient(app_module.app, raise_server_exceptions=False)
            lines = _stream_lines(
                client, {"session_id": "s-tok", "message": "hi"}
            )

        # (a) token events appear for the final answer, in order.
        token_events = [l for l in lines if l.get("type") == "token"]
        assert token_events, "expected token events"
        streamed = " ".join(e["text"] for e in token_events)
        assert streamed == reply

        # (b) the final line is the done event carrying the FULL reply + reports null.
        done = lines[-1]
        assert done["type"] == "done"
        assert done["reply"] == reply
        assert done["reports"] is None
