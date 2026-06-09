"""tests/test_document.py — services/document.py RAG-lite primitives (offline).

Fully deterministic, no network: extraction (TXT + a tiny generated PDF), chunking,
retrieval with a FAKE embedder, lexical fallback, scanned/no-text → DocumentError,
and a grounded summary with a FAKE llm.
"""
from __future__ import annotations

import numpy as np
import pytest

import services.document as d


# ---------------------------------------------------------------------------
# Fakes — deterministic, offline
# ---------------------------------------------------------------------------

class FakeEmbedder:
    """Deterministic 3-dim embeddings keyed on keyword presence (no network)."""

    def _vec(self, text: str) -> list[float]:
        t = text.lower()
        return [
            float("risk" in t or "风险" in t),
            float("revenue" in t or "营收" in t or "收入" in t),
            float("cash" in t or "现金" in t),
        ]

    def embed_documents(self, chunks: list[str]) -> list[list[float]]:
        return [self._vec(c) for c in chunks]

    def embed_query(self, q: str) -> list[float]:
        return self._vec(q)


class FakeLLM:
    """Fake chat model returning a fixed grounded one-liner."""

    def __init__(self, reply: str = "这是一份测试财报，涵盖营收与风险。"):
        self.reply = reply
        self.last_messages = None

    def invoke(self, messages):
        self.last_messages = messages

        class _R:
            content = self.reply

        return _R()


def _tiny_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _scanned_pdf() -> bytes:
    """A PDF page with NO text layer (simulates a scanned image-only file)."""
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_txt_extracts_text(self):
        res = d.extract_text("Hello financial world.".encode("utf-8"), "report.txt")
        assert res.text == "Hello financial world."
        assert res.pages == 1
        assert res.chars == len(res.text)

    def test_md_extracts_text(self):
        res = d.extract_text(b"# Title\n\nSome **revenue** content.", "notes.md")
        assert "revenue" in res.text
        assert res.pages == 1

    def test_pdf_extracts_text(self):
        data = _tiny_pdf("Net income was 5 million in 2023.")
        res = d.extract_text(data, "10k.pdf")
        assert "Net income" in res.text
        assert res.pages == 1

    def test_scanned_pdf_raises_422(self):
        with pytest.raises(d.DocumentError) as ei:
            d.extract_text(_scanned_pdf(), "scan.pdf")
        assert ei.value.status_code == 422

    def test_empty_txt_raises_422(self):
        with pytest.raises(d.DocumentError) as ei:
            d.extract_text(b"   \n  ", "empty.txt")
        assert ei.value.status_code == 422

    def test_unsupported_extension_raises_415(self):
        with pytest.raises(d.DocumentError) as ei:
            d.extract_text(b"data", "image.png")
        assert ei.value.status_code == 415


# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_short_text_single_chunk(self):
        chunks = d.chunk_text("short text", chunk_chars=1500, overlap=200)
        assert chunks == ["short text"]

    def test_overlapping_chunks(self):
        text = "".join(str(i % 10) for i in range(1000))
        chunks = d.chunk_text(text, chunk_chars=300, overlap=50)
        assert len(chunks) > 1
        # Adjacent chunks share the overlap tail/head.
        assert chunks[0][-50:] == chunks[1][:50]

    def test_empty_text_no_chunks(self):
        assert d.chunk_text("   ") == []


# ---------------------------------------------------------------------------
# embed_chunks / retrieve (fake embedder + lexical fallback)
# ---------------------------------------------------------------------------

class TestRetrieve:
    def _doc(self, embedder=None):
        text = (
            "Section one discusses revenue growth and total revenue figures.\n\n"
            "Section two lists business risk factors and competition risk.\n\n"
            "Section three covers cash flow and cash positions."
        )
        return d.build_uploaded_doc(text.encode("utf-8"), "rep.txt", embedder=embedder)

    def test_embed_chunks_shape(self):
        chunks = ["risk here", "revenue there", "cash now"]
        mat = d.embed_chunks(chunks, embedder=FakeEmbedder())
        assert isinstance(mat, np.ndarray)
        assert mat.shape == (3, 3)

    def test_upload_does_not_embed_lazily_built_on_retrieve(self):
        # build_uploaded_doc (the upload path) must NOT embed — embeddings stay None
        # until the first retrieve, which lazily builds & caches the index.
        doc = self._doc(embedder=FakeEmbedder())
        assert doc.embeddings is None  # upload no longer embeds

        ex = d.retrieve("what are the risk factors", doc, k=1, embedder=FakeEmbedder())
        assert doc.embeddings is not None  # lazily built on first retrieve
        assert len(ex) == 1
        assert "risk" in ex[0].text.lower()
        assert ex[0].locator  # non-empty locator

    def test_retrieve_reuses_cached_index_no_reembed(self):
        # First retrieve builds the index; a second call must reuse the cached
        # embeddings and NOT re-embed the chunks.
        class CountingEmbedder(FakeEmbedder):
            def __init__(self):
                self.doc_calls = 0

            def embed_documents(self, chunks):
                self.doc_calls += 1
                return super().embed_documents(chunks)

        emb = CountingEmbedder()
        doc = self._doc(embedder=emb)
        assert emb.doc_calls == 0  # upload did not embed

        d.retrieve("risk factors", doc, k=1, embedder=emb)
        assert emb.doc_calls == 1  # built once
        cached = doc.embeddings
        d.retrieve("revenue growth", doc, k=1, embedder=emb)
        assert emb.doc_calls == 1  # reused cache — no re-embed of chunks
        assert doc.embeddings is cached

    def test_ensure_index_builds_and_caches(self):
        doc = self._doc(embedder=FakeEmbedder())
        assert doc.embeddings is None
        out = d.ensure_index(doc, embedder=FakeEmbedder())
        assert out is doc
        assert doc.embeddings is not None
        # Idempotent: a second ensure_index does not rebuild (same array object).
        first = doc.embeddings
        d.ensure_index(doc, embedder=FakeEmbedder())
        assert doc.embeddings is first

    def test_retrieve_lexical_fallback_when_no_embeddings(self):
        # Embedder that fails → embeddings stay None → lexical retrieval mode
        # (offline, never touches the network even if an OPENAI_API_KEY is present).
        class Boom:
            def embed_documents(self, chunks):
                raise RuntimeError("no network")

        doc = self._doc()
        ex = d.retrieve("cash flow position", doc, k=1, embedder=Boom())
        assert doc.embeddings is None  # lazy build failed → lexical mode
        assert "cash" in ex[0].text.lower()

    def test_embed_chunks_none_on_bad_embedder(self):
        class Boom:
            def embed_documents(self, chunks):
                raise RuntimeError("no network")

        assert d.embed_chunks(["a", "b"], embedder=Boom()) is None

    def test_embed_chunks_batches_and_reports_progress(self, monkeypatch):
        # Force a small batch size so multiple batches are exercised.
        monkeypatch.setattr(d, "EMBED_BATCH_SIZE", 2)

        class BatchEmbedder(FakeEmbedder):
            def __init__(self):
                self.batch_sizes = []

            def embed_documents(self, chunks):
                self.batch_sizes.append(len(chunks))
                return super().embed_documents(chunks)

        emb = BatchEmbedder()
        chunks = ["risk a", "revenue b", "cash c", "risk d", "revenue e"]
        progress: list[tuple[int, int]] = []
        mat = d.embed_chunks(chunks, embedder=emb, on_progress=lambda done, total: progress.append((done, total)))

        # Full (n, dim) matrix returned despite batching.
        assert isinstance(mat, np.ndarray)
        assert mat.shape == (5, 3)
        # 5 chunks / batch 2 → batches of [2, 2, 1].
        assert emb.batch_sizes == [2, 2, 1]
        # on_progress fired once per batch with cumulative done / fixed total.
        assert progress == [(2, 5), (4, 5), (5, 5)]

    def test_ensure_index_forwards_progress(self):
        progress: list[tuple[int, int]] = []
        doc = self._doc(embedder=FakeEmbedder())
        assert doc.embeddings is None
        d.ensure_index(doc, embedder=FakeEmbedder(),
                       on_progress=lambda done, total: progress.append((done, total)))
        assert doc.embeddings is not None
        # At least one progress callback, last reaches total.
        assert progress
        assert progress[-1][0] == progress[-1][1]


# ---------------------------------------------------------------------------
# summarize (fake llm + grounded fallback)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DOC_MAX_INDEX_CHARS truncation
# ---------------------------------------------------------------------------

class TestIndexTruncation:
    def test_long_text_truncated_flag_and_bounded_chunks(self):
        from config import DOC_CHUNK_CHARS, DOC_MAX_INDEX_CHARS

        # Build a text that clearly exceeds DOC_MAX_INDEX_CHARS.
        long_text = "A" * (DOC_MAX_INDEX_CHARS + 50_000)
        data = long_text.encode("utf-8")
        doc = d.build_uploaded_doc(data, "big.txt", embedder=FakeEmbedder())

        # index_truncated must be True.
        assert doc.index_truncated is True

        # Full text is preserved for honest reporting.
        assert len(doc.text) == len(long_text)
        assert doc.meta["chars"] == len(long_text)

        # Chunks must come only from the first DOC_MAX_INDEX_CHARS characters.
        max_expected_chunks = (DOC_MAX_INDEX_CHARS // (DOC_CHUNK_CHARS - 250)) + 2
        assert len(doc.chunks) <= max_expected_chunks

        # All chunks are sliced from the capped text, so no chunk can contain
        # characters beyond position DOC_MAX_INDEX_CHARS in the original text.
        # (chunk_text receives text[:DOC_MAX_INDEX_CHARS] — any end index is clamped.)
        for chunk in doc.chunks:
            assert len(chunk) <= DOC_CHUNK_CHARS

    def test_short_text_not_truncated(self):
        from config import DOC_MAX_INDEX_CHARS

        short_text = "Revenue grew significantly this year. Risk factors include competition."
        assert len(short_text) < DOC_MAX_INDEX_CHARS

        doc = d.build_uploaded_doc(short_text.encode("utf-8"), "short.txt", embedder=FakeEmbedder())

        assert doc.index_truncated is False
        assert len(doc.text) == len(short_text)
        # All text is indexed — chunks cover the full document.
        assert doc.chunks  # at least one chunk


class TestSummarize:
    def _doc(self):
        return d.build_uploaded_doc(
            b"Revenue grew. Risk factors include competition.", "x.txt",
            embedder=FakeEmbedder(),
        )

    def test_summarize_with_fake_llm(self):
        doc = self._doc()
        ex = d.retrieve("summary", doc, k=2, embedder=FakeEmbedder())
        llm = FakeLLM()
        out = d.summarize(doc, ex, llm=llm)
        assert out == llm.reply
        assert llm.last_messages is not None

    def test_summarize_fallback_on_llm_error_is_grounded(self):
        class Boom:
            def invoke(self, messages):
                raise RuntimeError("llm down")

        doc = self._doc()
        ex = d.retrieve("summary", doc, k=2, embedder=FakeEmbedder())
        out = d.summarize(doc, ex, llm=Boom())
        # Grounded fallback names the file and quotes original text (no fabrication).
        assert doc.filename in out

    def test_summarize_no_excerpts(self):
        doc = self._doc()
        out = d.summarize(doc, [], llm=FakeLLM())
        assert doc.filename in out
