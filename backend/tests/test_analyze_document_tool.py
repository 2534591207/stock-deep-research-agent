"""tests/test_analyze_document_tool.py — tools.analyze_document (offline).

Injects a fake doc into the document store + a fake embedder/llm, sets the
session contextvar, and asserts: ok → summary + excerpts; no doc → no_document;
and the `__doc__` doc stage events are emitted via a captured progress sink.
"""
from __future__ import annotations

import pytest

import tools
from services import doc_store
from services import document as d
from services.progress import report_progress


class _FakeEmbedder:
    def _vec(self, t):
        t = t.lower()
        return [float("risk" in t), float("revenue" in t), float("cash" in t)]

    def embed_documents(self, chunks):
        return [self._vec(c) for c in chunks]

    def embed_query(self, q):
        return self._vec(q)


class _FakeLLM:
    def invoke(self, messages):
        class _R:
            content = "这是一份财报，涉及营收与风险因素。"

        return _R()


def _make_doc() -> d.UploadedDoc:
    text = (
        "Revenue increased this year and total revenue was strong.\n\n"
        "Risk factors include intense competition and regulatory risk.\n\n"
        "Cash flow from operations was positive."
    )
    return d.build_uploaded_doc(text.encode("utf-8"), "fin.txt", embedder=_FakeEmbedder())


@pytest.fixture()
def wired():
    tools.set_doc_embedder(_FakeEmbedder())
    tools.set_doc_llm(_FakeLLM())
    doc_store.clear()
    try:
        yield
    finally:
        tools.set_doc_embedder(None)
        tools.set_doc_llm(None)
        doc_store.clear()


def _invoke_with_session(question: str, session_id: str | None):
    """Invoke the tool with the session contextvar set + a captured progress sink."""
    events: list[dict] = []
    sink_token = report_progress.set(lambda ev: events.append(ev))
    sid_token = doc_store.current_session_id.set(session_id)
    try:
        result = tools.analyze_document.invoke({"question": question})
    finally:
        doc_store.current_session_id.reset(sid_token)
        report_progress.reset(sink_token)
    return result, events


class TestAnalyzeDocumentTool:
    def test_ok_returns_summary_and_excerpts(self, wired):
        doc_store.put_document("sess-1", _make_doc())
        result, _ = _invoke_with_session("what are the risk factors", "sess-1")
        assert result["status"] == "ok"
        assert result["summary"]
        assert result["excerpts"]
        for ex in result["excerpts"]:
            assert "text" in ex and "locator" in ex
        # Grounded: the top excerpt for a risk question mentions risk.
        assert any("risk" in ex["text"].lower() for ex in result["excerpts"])

    def test_no_document_when_none_uploaded(self, wired):
        result, _ = _invoke_with_session("分析这个财报", "no-doc-session")
        assert result == {"status": "no_document"}

    def test_no_document_when_no_session(self, wired):
        result, _ = _invoke_with_session("分析这个财报", None)
        assert result == {"status": "no_document"}

    def test_emits_doc_stage_events(self, wired):
        doc_store.put_document("sess-2", _make_doc())
        _, events = _invoke_with_session("营收情况如何", "sess-2")
        stages = [(e["symbol"], e["stage"], e["status"]) for e in events
                  if e.get("type") == "stage"]
        # All four doc stages emitted start+done under the __doc__ track, in order.
        expected_order = ["doc_load", "doc_parse", "doc_locate", "doc_summarize"]
        starts = [stage for sym, stage, status in stages
                  if sym == "__doc__" and status == "start"]
        dones = [stage for sym, stage, status in stages
                 if sym == "__doc__" and status == "done"]
        assert starts == expected_order
        assert dones == expected_order

    def test_no_document_still_emits_doc_load(self, wired):
        _, events = _invoke_with_session("file?", "missing")
        doc_load = [(e["stage"], e["status"]) for e in events
                    if e.get("symbol") == "__doc__" and e.get("stage") == "doc_load"]
        assert doc_load == [("doc_load", "start"), ("doc_load", "done")]

    def test_lazy_index_built_once_and_cached_across_calls(self):
        # Upload stores the doc without embeddings; the first analyze_document call
        # builds the index lazily (embedder called once for chunks), and a second
        # call reuses the cached index (no re-embed of chunks).
        class _CountingEmbedder(_FakeEmbedder):
            def __init__(self):
                self.doc_calls = 0

            def embed_documents(self, chunks):
                self.doc_calls += 1
                return super().embed_documents(chunks)

        emb = _CountingEmbedder()
        tools.set_doc_embedder(emb)
        tools.set_doc_llm(_FakeLLM())
        doc_store.clear()
        try:
            doc = _make_doc()
            assert doc.embeddings is None  # upload did not embed
            doc_store.put_document("sess-lazy", doc)

            _invoke_with_session("what are the risk factors", "sess-lazy")
            assert emb.doc_calls == 1  # built once on first question
            stored = doc_store.get_document("sess-lazy")
            assert stored.embeddings is not None  # cached on the stored object
            cached = stored.embeddings

            _invoke_with_session("营收情况如何", "sess-lazy")
            assert emb.doc_calls == 1  # reused cache — no re-embed of chunks
            assert doc_store.get_document("sess-lazy").embeddings is cached
        finally:
            tools.set_doc_embedder(None)
            tools.set_doc_llm(None)
            doc_store.clear()


class TestExistingToolsUnchanged:
    """analyze_stocks / generate_report must not read the session contextvar."""

    def test_analyze_stocks_signature_unchanged(self):
        # Two required args, no session_id leaked in.
        assert set(tools.analyze_stocks.args) == {"companies", "period"}

    def test_generate_report_signature_unchanged(self):
        assert set(tools.generate_report.args) == {"companies", "period"}
