"""tests/test_upload.py — POST /upload streaming NDJSON (offline, deterministic).

Upload now STREAMS its progress as NDJSON and builds the embedding index AT
UPLOAD time (no longer lazily on the first question). Validation still returns a
real HTTP status BEFORE any streaming: 415 unsupported type, 413 too large.
Scanned/no-text PDFs surface as an in-stream {"type":"error"} line.

A fake embedder is injected so upload never touches the network. EMBED_BATCH_SIZE
batching means the index phase emits done/total progress events.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class _FakeEmbedder:
    def __init__(self):
        self.doc_calls = 0

    def embed_documents(self, chunks):
        self.doc_calls += 1
        return [[float(len(c)), 1.0] for c in chunks]

    def embed_query(self, q):
        return [float(len(q)), 1.0]


def _scanned_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _stream_lines(client, *, data, files):
    """POST /upload and parse each NDJSON line. Returns (status_code, [dict])."""
    with client.stream("POST", "/upload", data=data, files=files) as r:
        if r.status_code != 200:
            # Pre-stream HTTP error (415/413): no NDJSON body to parse.
            r.read()
            return r.status_code, []
        lines = [json.loads(line) for line in r.iter_lines() if line]
    return 200, lines


@pytest.fixture()
def upload_embedder():
    return _FakeEmbedder()


@pytest.fixture()
def app_module(upload_embedder):
    with patch("app.require_keys", return_value=None):
        import app as app_module
        from services import doc_store

        app_module.set_upload_embedder(upload_embedder)
        doc_store.clear()
        try:
            yield app_module
        finally:
            app_module.set_upload_embedder(None)
            doc_store.clear()


@pytest.fixture()
def client(app_module):
    return TestClient(app_module.app, raise_server_exceptions=False)


class TestUpload:
    def test_txt_success_streams_phases_then_ready(self, client, app_module):
        from services import doc_store

        status, lines = _stream_lines(
            client,
            data={"session_id": "s1"},
            files={"file": ("report.txt", b"Revenue grew. Risk factors apply.", "text/plain")},
        )
        assert status == 200

        # Phase order: an extract phase appears, then >=1 index phase, then ready.
        types = [l.get("type") for l in lines]
        assert "phase" in types
        extract = [l for l in lines if l.get("type") == "phase" and l["phase"] == "extract"]
        assert extract and extract[0]["label"]
        index = [l for l in lines if l.get("type") == "phase" and l["phase"] == "index"]
        assert index, "expected at least one index-progress phase"
        for ev in index:
            assert isinstance(ev["done"], int) and isinstance(ev["total"], int)
            assert 0 < ev["done"] <= ev["total"]
        # Last index event reaches total.
        assert index[-1]["done"] == index[-1]["total"]

        # Final line is exactly one ready with the contract fields.
        ready = lines[-1]
        assert ready["type"] == "ready"
        assert ready["filename"] == "report.txt"
        assert ready["pages"] == 1
        assert ready["chars"] > 0
        assert ready["index_truncated"] is False

        # Stored in the document store (separate from the report store).
        assert doc_store.get_document("s1") is not None
        assert not app_module._report_store  # report store untouched

    def test_index_built_at_upload(self, client, app_module, upload_embedder):
        """The embedding index is built at UPLOAD (not lazily on first question)."""
        from services import doc_store

        status, lines = _stream_lines(
            client,
            data={"session_id": "s-fast"},
            files={"file": ("report.txt", b"Revenue grew. Risk factors apply.", "text/plain")},
        )
        assert status == 200
        assert lines[-1]["type"] == "ready"
        # Embedding ran during upload.
        assert upload_embedder.doc_calls >= 1
        stored = doc_store.get_document("s-fast")
        assert stored is not None
        assert stored.chunks  # text extracted + chunked
        assert stored.embeddings is not None  # index built AT upload → questions instant

    def test_reupload_replaces(self, client):
        from services import doc_store

        _stream_lines(
            client,
            data={"session_id": "s2"},
            files={"file": ("a.txt", b"first document content", "text/plain")},
        )
        _stream_lines(
            client,
            data={"session_id": "s2"},
            files={"file": ("b.md", b"second document content here", "text/plain")},
        )
        doc = doc_store.get_document("s2")
        assert doc.filename == "b.md"

    def test_unsupported_type_415(self, client):
        status, lines = _stream_lines(
            client,
            data={"session_id": "s3"},
            files={"file": ("pic.png", b"\x89PNG\r\n", "image/png")},
        )
        # Pre-stream HTTP error (before any NDJSON).
        assert status == 415
        assert lines == []

    def test_too_large_413(self, client, app_module):
        big = b"a" * (app_module.MAX_UPLOAD_MB * 1024 * 1024 + 1)
        status, lines = _stream_lines(
            client,
            data={"session_id": "s4"},
            files={"file": ("big.txt", big, "text/plain")},
        )
        assert status == 413
        assert lines == []

    def test_scanned_pdf_no_text_error_line(self, client):
        status, lines = _stream_lines(
            client,
            data={"session_id": "s5"},
            files={"file": ("scan.pdf", _scanned_pdf(), "application/pdf")},
        )
        # Stream opens 200, then the final line is an error (no extractable text).
        assert status == 200
        assert lines[-1]["type"] == "error"
        assert lines[-1]["message"]
        # No ready line was emitted.
        assert not any(l.get("type") == "ready" for l in lines)
