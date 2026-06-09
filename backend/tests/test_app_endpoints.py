"""tests/test_app_endpoints.py — FULL offline interface coverage for app.py.

Every endpoint and every branch of backend/app.py is exercised through
fastapi.testclient.TestClient with **zero real network / OpenAI**:

  - GET  /health                       → 200 {ok: true}            (no agent/key dep)
  - POST /chat (happy path)            → 200 {reply: <str>}
  - POST /chat producing a report      → then GET /report/{sid}/latest → 200 text/markdown
  - GET  /report/{unknown}/latest      → 404
  - POST /chat when the agent raises   → 500 with detail
  - POST /chat with missing/invalid body → 422

How isolation is achieved
-------------------------
* ``app.require_keys`` is patched to a no-op so lifespan startup never aborts
  when .env keys are absent (mirrors the project's own test_health.py).
* ``app._get_agent`` is monkeypatched to return a *fake* agent whose ``.invoke``
  returns a canned ``{"messages": [...]}``. No ChatOpenAI, no LangGraph, no I/O.
* The report path injects a genuine ``langchain_core.messages.ToolMessage`` whose
  JSON content carries a ``"markdown"`` key, which is exactly what
  ``app._persist_report`` scans for — so the in-memory report store gets populated
  through the real production code path.

The fake agent never computes any numbers and never asserts any causation; it is
purely a transport stand-in for the LLM/ReAct layer so the HTTP surface can be
verified deterministically offline.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Fake agent transport stand-ins
# ---------------------------------------------------------------------------

# A representative report markdown. Content is irrelevant to the HTTP contract;
# the test only asserts the bytes round-trip unchanged from store → response.
_REPORT_MARKDOWN = (
    "# US Stock Research Report\n\n"
    "_Data source: Yahoo Finance (free, DELAYED — not real-time). "
    "Current price is a delayed reference price, not for trading._\n\n"
    "## 1. Overview\nAAPL over the last 30 days.\n"
)


def _tool_message(payload: dict, *, tool_call_id: str = "call_report_1") -> ToolMessage:
    """Build a ToolMessage exactly like a tool would emit.

    ``ReportResult.model_dump()`` serialises to a dict containing a ``reports``
    list; the agent serialises tool results to a JSON string in ``.content``.
    """
    return ToolMessage(content=json.dumps(payload), tool_call_id=tool_call_id)


def _report_payload(*reports: dict) -> dict:
    """generate_report tool output shape: {"reports": [per-stock dict, ...]}.

    Each per-stock dict mirrors PerStockReport.model_dump():
    {report_id, title, symbol, markdown, section_index}.
    """
    return {"reports": list(reports)}


def _per_stock(symbol: str, markdown: str, *, report_id: str | None = None,
               title: str | None = None) -> dict:
    rid = report_id or f"{symbol}-deadbeef"
    return {
        "report_id": rid,
        "title": title or f"{symbol} report",
        "symbol": symbol,
        "markdown": markdown,
        "section_index": [],
    }


def _seed(app_module, sid: str, *reports) -> None:
    """Seed the per-session ordered report list with StoredReport entries.

    Accepts either (symbol, markdown) tuples or raw markdown strings (auto-named).
    """
    items = []
    for i, r in enumerate(reports):
        if isinstance(r, tuple):
            symbol, markdown = r
        else:
            symbol, markdown = f"SYM{i}", r
        items.append(app_module.StoredReport(
            report_id=f"{symbol}-seed{i}",
            title=f"{symbol} report",
            symbol=symbol,
            markdown=markdown,
        ))
    app_module._report_store[sid] = items


class _FakeAgent:
    """Minimal stand-in for the compiled LangGraph agent.

    ``.invoke(state, config=...)`` returns a pre-baked message list. The returned
    sequence and the final message's ``.content`` are fully controlled per
    instance so each test can pin the exact reply / report behaviour.
    """

    def __init__(self, messages: list[Any]) -> None:
        self._messages = messages
        self.calls: list[dict] = []

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        # Record the call so tests can assert the message/thread plumbing.
        self.calls.append({"state": state, "config": config})
        return {"messages": list(self._messages)}


class _RaisingAgent:
    """Stand-in whose ``.invoke`` raises, to exercise the 500 branch."""

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        raise RuntimeError("boom: simulated agent failure")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_module():
    """Import the app module with require_keys patched, and a clean report store.

    The report store is module-global; we snapshot-and-restore it so tests stay
    independent regardless of execution order.
    """
    with patch("app.require_keys", return_value=None):
        import app as app_module  # imported lazily so the patch is in force

        saved_store = dict(app_module._report_store)
        app_module._report_store.clear()
        try:
            yield app_module
        finally:
            app_module._report_store.clear()
            app_module._report_store.update(saved_store)


def _client(app_module) -> TestClient:
    """Build a TestClient that surfaces handler exceptions (so 500s are real)."""
    return TestClient(app_module.app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_200_ok_true(self, app_module):
        with _client(app_module) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_health_independent_of_agent(self, app_module):
        """/health must not touch _get_agent at all."""
        with patch.object(app_module, "_get_agent") as get_agent:
            with _client(app_module) as client:
                resp = client.get("/health")
            assert resp.status_code == 200
            get_agent.assert_not_called()


# ---------------------------------------------------------------------------
# POST /chat — happy path (no report produced)
# ---------------------------------------------------------------------------

class TestChatHappyPath:
    def test_chat_returns_reply_string(self, app_module):
        fake = _FakeAgent([
            HumanMessage(content="分析一下 AAPL 最近一个月"),
            AIMessage(content="Here is the delayed-data analysis for AAPL."),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-happy", "message": "分析一下 AAPL 最近一个月"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"reply"}
        assert isinstance(body["reply"], str)
        assert body["reply"] == "Here is the delayed-data analysis for AAPL."

    def test_chat_threads_session_id_into_config(self, app_module):
        """thread_id must equal session_id (drives MemorySaver multi-turn memory)."""
        fake = _FakeAgent([AIMessage(content="ok")])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "sess-XYZ", "message": "hi"},
                )

        assert resp.status_code == 200
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["config"] == {"configurable": {"thread_id": "sess-XYZ"}}
        assert call["state"] == {"messages": [{"role": "user", "content": "hi"}]}

    def test_chat_non_string_content_is_stringified(self, app_module):
        """If the last message content is not a str, it is coerced via str()."""
        # LangChain allows list/dict content blocks; the handler stringifies them.
        fake = _FakeAgent([AIMessage(content=[{"type": "text", "text": "blocky"}])])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-blocks", "message": "hi"},
                )

        assert resp.status_code == 200
        reply = resp.json()["reply"]
        assert isinstance(reply, str)
        assert "blocky" in reply

    def test_chat_without_report_leaves_store_empty(self, app_module):
        """A turn with no generate_report ToolMessage must not populate the store."""
        fake = _FakeAgent([AIMessage(content="no report here")])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-noreport", "message": "just chat"},
                )
                assert resp.status_code == 200
                # No report was produced → /report/.../latest is 404.
                report_resp = client.get("/report/s-noreport/latest")
        assert report_resp.status_code == 404
        assert "s-noreport" not in app_module._report_store


# ---------------------------------------------------------------------------
# POST /chat producing a report → GET /report/{sid}/latest
# ---------------------------------------------------------------------------

class TestChatProducesReportThenFetch:
    def test_report_path_populates_store_and_is_served(self, app_module):
        # generate_report tool output shape: {"reports": [per-stock dict, ...]}.
        report_payload = _report_payload(
            _per_stock("AAPL", _REPORT_MARKDOWN, report_id="AAPL-abc123")
        )
        fake = _FakeAgent([
            HumanMessage(content="给我一份 AAPL 的报告"),
            AIMessage(content="", ),  # the tool-call turn (content empty)
            _tool_message(report_payload),
            AIMessage(content="Your report is ready."),
        ])
        sid = "s-report"
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                chat_resp = client.post(
                    "/chat",
                    json={"session_id": sid, "message": "给我一份 AAPL 的报告"},
                )
                assert chat_resp.status_code == 200
                assert chat_resp.json()["reply"] == "Your report is ready."

                # Single per-stock report fetchable by its id and via /latest.
                by_id_resp = client.get(f"/report/{sid}/AAPL-abc123")
                latest_resp = client.get(f"/report/{sid}/latest")
                list_resp = client.get(f"/report/{sid}")

        assert by_id_resp.status_code == 200
        assert "text/markdown" in by_id_resp.headers.get("content-type", "")
        assert by_id_resp.text == _REPORT_MARKDOWN
        assert latest_resp.text == _REPORT_MARKDOWN
        # List endpoint returns metadata only, newest-first.
        listed = list_resp.json()["reports"]
        assert [r["report_id"] for r in listed] == ["AAPL-abc123"]
        assert listed[0]["symbol"] == "AAPL"
        # The store holds StoredReport entries through the real persist path.
        assert app_module._report_store[sid][0].markdown == _REPORT_MARKDOWN

    def test_two_stock_generation_lists_two_reports(self, app_module):
        """A 2-stock generate_report appends ONE report per stock to the store."""
        sid = "s-two"
        payload = _report_payload(
            _per_stock("NVDA", "# NVDA\n", report_id="NVDA-xx"),
            _per_stock("AAPL", "# AAPL\n", report_id="AAPL-xx"),
        )
        fake = _FakeAgent([
            HumanMessage(content="给我 NVDA 和 AAPL 的报告"),
            AIMessage(content=""),
            _tool_message(payload),
            AIMessage(content="已为 NVDA、AAPL 各生成一份独立报告。"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                chat_resp = client.post(
                    "/chat", json={"session_id": sid, "message": "给我 NVDA 和 AAPL 的报告"}
                )
                list_resp = client.get(f"/report/{sid}")
                nvda_resp = client.get(f"/report/{sid}/NVDA-xx")
                aapl_resp = client.get(f"/report/{sid}/AAPL-xx")

        # /chat returns two ReportRefs with correct download_refs.
        body = chat_resp.json()
        assert {r["report_id"] for r in body["reports"]} == {"NVDA-xx", "AAPL-xx"}
        for r in body["reports"]:
            assert r["download_ref"] == f"/report/{sid}/{r['report_id']}"
        # List has both, newest-first (AAPL appended last).
        listed = list_resp.json()["reports"]
        assert [r["report_id"] for r in listed] == ["AAPL-xx", "NVDA-xx"]
        # Each id returns its own stock's markdown.
        assert nvda_resp.text == "# NVDA\n"
        assert aapl_resp.text == "# AAPL\n"

    def test_two_separate_generate_report_calls_keep_both(self, app_module):
        """REGRESSION (live bug): if the LLM issues TWO generate_report tool
        calls in ONE turn (one per stock), BOTH per-stock reports must be stored
        and surfaced — neither dropped nor overwritten."""
        sid = "s-two-calls"
        nvda_payload = _report_payload(_per_stock("NVDA", "# NVDA\n", report_id="NVDA-1"))
        baba_payload = _report_payload(_per_stock("BABA", "# BABA\n", report_id="BABA-1"))
        # Two distinct generate_report ToolMessages in the SAME turn (the
        # ToolNode-concurrent-call shape that lost a report in production).
        fake = _FakeAgent([
            HumanMessage(content="生成英伟达和阿里巴巴最近三个月的研究报告"),
            AIMessage(content=""),
            _tool_message(nvda_payload, tool_call_id="call_report_nvda"),
            _tool_message(baba_payload, tool_call_id="call_report_baba"),
            AIMessage(content="已为英伟达(NVDA)和阿里巴巴(BABA)各生成一份。"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                chat_resp = client.post(
                    "/chat",
                    json={"session_id": sid, "message": "生成英伟达和阿里巴巴最近三个月的研究报告"},
                )
                list_resp = client.get(f"/report/{sid}")
                nvda_resp = client.get(f"/report/{sid}/NVDA-1")
                baba_resp = client.get(f"/report/{sid}/BABA-1")

        # /chat reports list has BOTH (no loss), with correct download_refs.
        body = chat_resp.json()
        assert {r["report_id"] for r in body["reports"]} == {"NVDA-1", "BABA-1"}
        for r in body["reports"]:
            assert r["download_ref"] == f"/report/{sid}/{r['report_id']}"
        # GET /report/{sid} lists BOTH.
        listed = {r["report_id"] for r in list_resp.json()["reports"]}
        assert listed == {"NVDA-1", "BABA-1"}
        assert nvda_resp.text == "# NVDA\n"
        assert baba_resp.text == "# BABA\n"

    def test_latest_report_reflects_most_recent_turn(self, app_module):
        """The store appends; /latest returns the most-recently appended report."""
        sid = "s-multi"
        first_md = "# First Report\nold"
        second_md = "# Second Report\nnew"

        fake_first = _FakeAgent([
            _tool_message(_report_payload(_per_stock("AAA", first_md, report_id="AAA-1"))),
            AIMessage(content="first done"),
        ])
        fake_second = _FakeAgent([
            _tool_message(_report_payload(_per_stock("BBB", second_md, report_id="BBB-2"))),
            AIMessage(content="second done"),
        ])

        with _client(app_module) as client:
            with patch.object(app_module, "_get_agent", return_value=fake_first):
                client.post("/chat", json={"session_id": sid, "message": "report 1"})
            with patch.object(app_module, "_get_agent", return_value=fake_second):
                client.post("/chat", json={"session_id": sid, "message": "report 2"})
            resp = client.get(f"/report/{sid}/latest")
            list_resp = client.get(f"/report/{sid}")

        assert resp.status_code == 200
        assert resp.text == second_md
        # Both generations persisted (one per stock), newest-first.
        assert [r["report_id"] for r in list_resp.json()["reports"]] == ["BBB-2", "AAA-1"]

    def test_persist_ignores_non_report_tool_messages(self, app_module):
        """A ToolMessage without a 'markdown' key (e.g. analyze_stocks) is skipped.

        Guards the structural invariant that analyze_stocks cannot emit a report.
        """
        sid = "s-analyze-only"
        analyze_payload = {"stocks": [], "ranking": None, "warnings": []}
        fake = _FakeAgent([
            _tool_message(analyze_payload, tool_call_id="call_analyze_1"),
            AIMessage(content="analysis only, no report"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat", json={"session_id": sid, "message": "analyze"}
                )
                assert resp.status_code == 200
                report_resp = client.get(f"/report/{sid}/latest")

        assert report_resp.status_code == 404
        assert sid not in app_module._report_store

    def test_persist_skips_non_json_tool_message(self, app_module):
        """A ToolMessage whose content is not JSON is skipped without crashing."""
        sid = "s-badjson"
        bad = ToolMessage(content="this is not json {", tool_call_id="call_x")
        fake = _FakeAgent([bad, AIMessage(content="done")])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat", json={"session_id": sid, "message": "go"}
                )
                assert resp.status_code == 200
                report_resp = client.get(f"/report/{sid}/latest")

        assert report_resp.status_code == 404
        assert sid not in app_module._report_store


# ---------------------------------------------------------------------------
# GET /report/{unknown}/latest → 404
# ---------------------------------------------------------------------------

class TestReportNotFound:
    def test_unknown_session_returns_404(self, app_module):
        with _client(app_module) as client:
            resp = client.get("/report/does-not-exist/latest")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "No report found for this session."


# ---------------------------------------------------------------------------
# POST /chat when the agent raises → 500 with detail
# ---------------------------------------------------------------------------

class TestChatAgentRaises:
    def test_agent_exception_returns_500_with_detail(self, app_module):
        with patch.object(app_module, "_get_agent", return_value=_RaisingAgent()):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-err", "message": "trigger failure"},
                )

        assert resp.status_code == 500
        detail = resp.json()["detail"]
        # detail is f"{type(exc).__name__}: {exc}" — surfaces the real error.
        assert detail.startswith("RuntimeError:")
        assert "boom: simulated agent failure" in detail

    def test_agent_build_failure_returns_500(self, app_module):
        """If _get_agent itself raises (e.g. build/key error), still a clean 500."""
        def _boom() -> Any:
            raise ValueError("cannot build agent")

        with patch.object(app_module, "_get_agent", side_effect=_boom):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-build-err", "message": "hi"},
                )

        assert resp.status_code == 500
        assert resp.json()["detail"].startswith("ValueError:")
        assert "cannot build agent" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# inline_report_images unit tests
# ---------------------------------------------------------------------------

class TestInlineReportImages:
    """Unit tests for the inline_report_images helper in app.py."""

    def test_existing_png_is_replaced_with_data_uri(self, app_module, tmp_path):
        """A /reports/<name>.png reference whose file exists on disk is replaced
        with a base64 data URI; the raw server path no longer appears."""
        import struct
        import zlib

        # Write a minimal valid 1×1 white PNG into the real _reports directory.
        png_filename = "test_inline_existing.png"
        png_path = app_module._REPORTS_DIR / png_filename
        # Construct a minimal 1x1 white PNG manually (no PIL dependency)
        def _make_minimal_png() -> bytes:
            def _chunk(tag: bytes, data: bytes) -> bytes:
                length = struct.pack(">I", len(data))
                crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
                return length + tag + data + crc
            ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            raw = b"\x00\xFF\xFF\xFF"   # filter byte + RGB white pixel
            idat = _chunk(b"IDAT", zlib.compress(raw))
            iend = _chunk(b"IEND", b"")
            return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend

        png_bytes = _make_minimal_png()
        app_module._REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(png_bytes)
        try:
            markdown = f"# Report\n\n![Price Trend Chart](/reports/{png_filename})\n\nSome text."
            result = app_module.inline_report_images(markdown)

            assert "data:image/png;base64," in result
            assert f"/reports/{png_filename}" not in result

            # The base64 payload must decode back to the exact bytes we wrote.
            import base64, re
            m = re.search(r"data:image/png;base64,([A-Za-z0-9+/=]+)", result)
            assert m is not None
            assert base64.b64decode(m.group(1)) == png_bytes
        finally:
            png_path.unlink(missing_ok=True)

    def test_missing_png_leaves_reference_intact(self, app_module):
        """A /reports/<name>.png reference whose file is absent on disk is left
        unchanged and no exception is raised."""
        markdown = "![Chart](/reports/does_not_exist_ever.png)"
        result = app_module.inline_report_images(markdown)
        assert result == markdown
        assert "data:image/png;base64," not in result

    def test_http_url_left_untouched(self, app_module):
        """Absolute http(s) image targets are not rewritten."""
        markdown = "![Chart](https://example.com/chart.png)"
        assert app_module.inline_report_images(markdown) == markdown

    def test_data_uri_left_untouched(self, app_module):
        """Already-inlined data: targets are not reprocessed."""
        markdown = "![Chart](data:image/png;base64,abc123)"
        assert app_module.inline_report_images(markdown) == markdown

    def test_no_image_markdown_unchanged(self, app_module):
        """Markdown with no image references is returned unchanged."""
        markdown = "# Report\n\nSome text without any images."
        assert app_module.inline_report_images(markdown) == markdown

    def test_get_report_endpoint_inlines_existing_png(self, app_module):
        """GET /report/{sid}/latest inlines a real PNG into the served markdown."""
        import struct, zlib

        sid = "s-inline-get"
        png_filename = "test_inline_get_endpoint.png"
        png_path = app_module._REPORTS_DIR / png_filename

        def _make_minimal_png() -> bytes:
            def _chunk(tag: bytes, data: bytes) -> bytes:
                length = struct.pack(">I", len(data))
                crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
                return length + tag + data + crc
            ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            raw = b"\x00\xFF\xFF\xFF"
            idat = _chunk(b"IDAT", zlib.compress(raw))
            iend = _chunk(b"IEND", b"")
            return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend

        png_bytes = _make_minimal_png()
        app_module._REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        png_path.write_bytes(png_bytes)
        try:
            # Seed the report store with markdown that references the PNG.
            raw_md = f"# Report\n\n![Price Trend Chart](/reports/{png_filename})\n"
            _seed(app_module, sid, ("MSFT", raw_md))

            with _client(app_module) as client:
                resp = client.get(f"/report/{sid}/latest")

            assert resp.status_code == 200
            assert "data:image/png;base64," in resp.text
            assert f"/reports/{png_filename}" not in resp.text
        finally:
            png_path.unlink(missing_ok=True)

    def test_get_report_endpoint_missing_png_leaves_ref_intact(self, app_module):
        """GET /report/{sid}/latest does not crash if a referenced PNG is absent."""
        sid = "s-inline-missing"
        raw_md = "# Report\n\n![Chart](/reports/ghost_file.png)\n"
        _seed(app_module, sid, ("MSFT", raw_md))

        with _client(app_module) as client:
            resp = client.get(f"/report/{sid}/latest")

        assert resp.status_code == 200
        # Reference must remain intact (no crash, no data URI)
        assert "/reports/ghost_file.png" in resp.text
        assert "data:image/png;base64," not in resp.text


# ---------------------------------------------------------------------------
# /chat structured report signal (FIX 2)
# ---------------------------------------------------------------------------

class TestChatReportSignal:
    """Assert the /chat response carries the turn-scoped ``reports`` list when
    generate_report ran this turn, and is absent on non-report turns."""

    def test_generate_report_turn_returns_reports_field(self, app_module):
        """A turn that produces a generate_report ToolMessage must return a
        ``reports`` list of ReportRefs (report_id/title/symbol/download_ref)."""
        report_payload = _report_payload(
            _per_stock("AAPL", _REPORT_MARKDOWN, report_id="AAPL-sig1", title="Apple (AAPL)")
        )
        sid = "s-report-signal"
        fake = _FakeAgent([
            HumanMessage(content="给我一份报告"),
            AIMessage(content="", ),
            _tool_message(report_payload),
            AIMessage(content="已为 苹果(AAPL) 生成一份独立报告，可在右侧「研究报告」列表查看并下载。"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": sid, "message": "给我一份报告"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "reports" in body
        assert len(body["reports"]) == 1
        ref = body["reports"][0]
        assert ref["report_id"] == "AAPL-sig1"
        assert ref["symbol"] == "AAPL"
        assert ref["title"] == "Apple (AAPL)"
        assert ref["download_ref"] == f"/report/{sid}/AAPL-sig1"

    def test_pure_chat_turn_has_no_reports_field(self, app_module):
        """A turn with no generate_report ToolMessage must have no 'reports' key
        in the JSON response (response_model_exclude_none omits it)."""
        fake = _FakeAgent([
            HumanMessage(content="AAPL 最近怎么样"),
            AIMessage(content="AAPL 最近表现不错。"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-no-report-signal", "message": "AAPL 最近怎么样"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "reports" not in body

    def test_analyze_tool_turn_has_no_reports_field(self, app_module):
        """A turn that calls analyze_stocks (no 'reports' key) must not produce
        a reports field — the ToolMessage is not from generate_report."""
        analyze_payload = {"stocks": [], "ranking": None, "warnings": []}
        fake = _FakeAgent([
            HumanMessage(content="compare AAPL and MSFT"),
            AIMessage(content=""),
            _tool_message(analyze_payload, tool_call_id="call_analyze"),
            AIMessage(content="Here is the comparison."),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": "s-analyze-signal", "message": "compare AAPL and MSFT"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "reports" not in body

    def test_old_report_not_resurface_on_followup_turn(self, app_module):
        """A follow-up turn (no new generate_report) must NOT include the
        reports field even though an older report sits in the store (AC-D3)."""
        sid = "s-ac-d3"
        # Seed an old report directly into the store.
        _seed(app_module, sid, ("OLD", "# Old Report\n"))

        # Follow-up turn produces only an AIMessage — no ToolMessage.
        fake = _FakeAgent([
            HumanMessage(content="报告里第一条经营风险是什么"),
            AIMessage(content="第一条是竞争风险。"),
        ])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": sid, "message": "报告里第一条经营风险是什么"},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert "reports" not in body


# ---------------------------------------------------------------------------
# Document-awareness injection (out-of-band /upload → /chat wiring fix)
# ---------------------------------------------------------------------------

class _DocAwareEmbedder:
    """Deterministic offline embedder for building an UploadedDoc in tests."""

    def _vec(self, t: str) -> list[float]:
        t = t.lower()
        return [float("risk" in t), float("revenue" in t)]

    def embed_documents(self, chunks: list[str]) -> list[list[float]]:
        return [self._vec(c) for c in chunks]

    def embed_query(self, q: str) -> list[float]:
        return self._vec(q)


def _put_fake_doc(sid: str, filename: str = "财报.txt") -> None:
    """Store a real UploadedDoc for the session via the production store."""
    from services import doc_store
    from services import document as docmod

    text = "Revenue grew strongly.\n\nRisk factors include competition."
    doc = docmod.build_uploaded_doc(text.encode("utf-8"), filename,
                                    embedder=_DocAwareEmbedder())
    doc_store.put_document(sid, doc)


class TestChatDocumentAwarenessInjection:
    """When a document is uploaded for a session, the /chat and /chat/stream
    handlers must inject a system-role awareness message (naming the file) into
    the turn passed to the agent; when no document exists, NOTHING is injected
    (the turn is identical to the pre-fix behaviour)."""

    def test_chat_injects_awareness_system_message_when_doc_present(self, app_module):
        from services import doc_store

        sid = "s-doc-aware"
        doc_store.clear()
        _put_fake_doc(sid, filename="Q3财报.txt")
        fake = _FakeAgent([AIMessage(content="ok")])
        try:
            with patch.object(app_module, "_get_agent", return_value=fake):
                with _client(app_module) as client:
                    resp = client.post(
                        "/chat",
                        json={"session_id": sid, "message": "帮我分析一下这个财报"},
                    )
        finally:
            doc_store.clear()

        assert resp.status_code == 200
        # Inspect the exact messages handed to the agent.
        assert len(fake.calls) == 1
        messages = fake.calls[0]["state"]["messages"]
        # A system message naming the file precedes the user message.
        assert messages[0]["role"] == "system"
        assert "[System note]" in messages[0]["content"]
        assert "Q3财报.txt" in messages[0]["content"]
        assert "analyze_document" in messages[0]["content"]
        assert messages[-1] == {"role": "user", "content": "帮我分析一下这个财报"}

    def test_chat_no_injection_when_no_doc(self, app_module):
        """No document → byte-for-byte identical turn (zero regression)."""
        from services import doc_store

        sid = "s-no-doc-aware"
        doc_store.clear()
        fake = _FakeAgent([AIMessage(content="ok")])
        with patch.object(app_module, "_get_agent", return_value=fake):
            with _client(app_module) as client:
                resp = client.post(
                    "/chat",
                    json={"session_id": sid, "message": "你好"},
                )

        assert resp.status_code == 200
        assert len(fake.calls) == 1
        messages = fake.calls[0]["state"]["messages"]
        # Exactly the pre-fix single user message, no system awareness message.
        assert messages == [{"role": "user", "content": "你好"}]

    def test_chat_stream_injects_awareness_system_message_when_doc_present(self, app_module):
        from fastapi.testclient import TestClient
        from services import doc_store

        sid = "s-doc-aware-stream"
        doc_store.clear()
        _put_fake_doc(sid, filename="年报.txt")
        fake = _FakeAgent([AIMessage(content="ok")])
        try:
            with patch.object(app_module, "_get_agent", return_value=fake):
                client = TestClient(app_module.app, raise_server_exceptions=False)
                with client.stream(
                    "POST", "/chat/stream",
                    json={"session_id": sid, "message": "这个财报讲了什么"},
                ) as r:
                    assert r.status_code == 200
                    _ = list(r.iter_lines())
        finally:
            doc_store.clear()

        assert len(fake.calls) == 1
        messages = fake.calls[0]["state"]["messages"]
        assert messages[0]["role"] == "system"
        assert "年报.txt" in messages[0]["content"]
        assert "analyze_document" in messages[0]["content"]
        assert messages[-1] == {"role": "user", "content": "这个财报讲了什么"}


# ---------------------------------------------------------------------------
# POST /chat with missing / invalid body → 422
# ---------------------------------------------------------------------------

class TestChatValidation:
    def test_missing_message_field_returns_422(self, app_module):
        with _client(app_module) as client:
            resp = client.post("/chat", json={"session_id": "s1"})  # no message
        assert resp.status_code == 422

    def test_missing_session_id_field_returns_422(self, app_module):
        with _client(app_module) as client:
            resp = client.post("/chat", json={"message": "hi"})  # no session_id
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, app_module):
        with _client(app_module) as client:
            resp = client.post("/chat", json={})
        assert resp.status_code == 422

    def test_wrong_type_message_returns_422(self, app_module):
        with _client(app_module) as client:
            resp = client.post(
                "/chat", json={"session_id": "s1", "message": {"not": "a string"}}
            )
        assert resp.status_code == 422

    def test_non_json_body_returns_422(self, app_module):
        with _client(app_module) as client:
            resp = client.post(
                "/chat",
                data="this is not json",
                headers={"content-type": "application/json"},
            )
        assert resp.status_code == 422

    def test_validation_error_never_invokes_agent(self, app_module):
        """A 422 is raised before the handler body, so _get_agent is untouched."""
        with patch.object(app_module, "_get_agent") as get_agent:
            with _client(app_module) as client:
                resp = client.post("/chat", json={"session_id": "s1"})
            assert resp.status_code == 422
            get_agent.assert_not_called()
