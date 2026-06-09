"""services/document.py — RAG-lite document understanding (NEW, purely additive).

Single uploaded financial-report file → extract text → overlapping chunks →
in-memory embeddings (numpy cosine top-k) → grounded summary. No vector DB.

Pipeline primitives (all pure / injectable for offline tests):
  - extract_text(data, filename)      PDF via PyMuPDF (fitz); TXT/MD direct decode.
                                       No extractable text (scanned) → DocumentError.
  - chunk_text(text)                   overlapping ~DOC_CHUNK_CHARS chunks.
  - embed_chunks(chunks, embedder)     default OpenAIEmbeddings; injectable fake.
                                       Embeddings unavailable/error → returns None
                                       (caller falls back to lexical retrieval).
  - retrieve(question, doc, k, ...)    cosine top-k over numpy, or lexical fallback.
  - summarize(doc, excerpts, llm)      brief grounded overview; injectable llm.

Honesty: never fabricates content. When embeddings are unavailable it degrades to
a transparent keyword/lexical retrieval mode rather than inventing similarity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from config import (
    DOC_CHUNK_CHARS,
    DOC_CHUNK_OVERLAP,
    DOC_MAX_INDEX_CHARS,
    DOC_TOP_K,
    EMBED_BATCH_SIZE,
    EMBEDDING_MODEL,
)


class DocumentError(Exception):
    """Domain error for unprocessable uploads (e.g. scanned PDF with no text).

    Carries an optional ``status_code`` hint so the /upload endpoint can map the
    failure to the right HTTP code (422 for no-extractable-text).
    """

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class DocText:
    """Result of text extraction."""

    text: str
    pages: int
    chars: int


@dataclass
class Excerpt:
    """One retrieved chunk with its locator (chunk index / approx page)."""

    text: str
    locator: str


@dataclass
class UploadedDoc:
    """In-memory representation of ONE uploaded document (one per session)."""

    filename: str
    text: str
    chunks: list[str]
    embeddings: Optional[np.ndarray] = None  # None → lexical retrieval mode
    meta: dict = field(default_factory=dict)
    index_truncated: bool = False  # True when only the first DOC_MAX_INDEX_CHARS were indexed


# ---------------------------------------------------------------------------
# 1. extract_text
# ---------------------------------------------------------------------------

def extract_text(data: bytes, filename: str) -> DocText:
    """Extract plain text from an uploaded file's bytes.

    PDF → PyMuPDF (``import fitz``); TXT/MD → direct UTF-8 decode (latin-1 fallback).
    Raises ``DocumentError`` when no extractable text is found (e.g. a scanned PDF
    image with no text layer) — OCR is intentionally NOT supported this phase.
    """
    ext = _ext(filename)

    if ext == ".pdf":
        text, pages = _extract_pdf(data)
    elif ext in (".txt", ".md"):
        text = _decode(data)
        pages = 1
    else:
        raise DocumentError(
            f"不支持的文件类型：{ext or filename}", status_code=415
        )

    cleaned = text.strip()
    if not cleaned:
        raise DocumentError(
            "未能从文件中提取到任何文本（可能是扫描件/纯图片 PDF）。"
            "本期不支持 OCR，请上传含文本层的 PDF 或 TXT/MD 文件。",
            status_code=422,
        )

    return DocText(text=cleaned, pages=pages, chars=len(cleaned))


def _extract_pdf(data: bytes) -> tuple[str, int]:
    import fitz  # PyMuPDF

    parts: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — corrupt/unreadable PDF
        raise DocumentError(f"无法解析 PDF 文件：{exc}", status_code=422) from exc
    try:
        pages = doc.page_count
        for page in doc:
            parts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n".join(parts), pages


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _ext(filename: str) -> str:
    name = (filename or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


# ---------------------------------------------------------------------------
# 2. chunk_text
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    chunk_chars: int = DOC_CHUNK_CHARS,
    overlap: int = DOC_CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping fixed-size character chunks.

    Returns ~``chunk_chars``-sized windows that overlap by ``overlap`` chars so a
    fact that straddles a boundary still appears whole in at least one chunk.
    """
    text = text.strip()
    if not text:
        return []
    if chunk_chars <= 0:
        return [text]
    overlap = max(0, min(overlap, chunk_chars - 1))
    step = chunk_chars - overlap

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_chars, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start += step
    return chunks


# ---------------------------------------------------------------------------
# 3. embed_chunks
# ---------------------------------------------------------------------------

def embed_chunks(
    chunks: list[str],
    embedder: Optional[Any] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Optional[np.ndarray]:
    """Embed chunks into a (n_chunks, dim) float32 matrix, in BATCHES.

    ``embedder`` is injectable: any object exposing ``embed_documents(list[str])``
    (the LangChain Embeddings interface). When None, the default is
    ``langchain_openai.OpenAIEmbeddings(model=EMBEDDING_MODEL)``.

    Chunks are embedded in batches of ``EMBED_BATCH_SIZE`` (one ``embed_documents``
    call per batch). This avoids one giant slow request and lets the caller observe
    real progress: ``on_progress(done, total)`` is invoked after EACH batch
    completes, where ``done`` is the cumulative number of chunks embedded and
    ``total`` is ``len(chunks)``.

    Returns None when embeddings are unavailable (no embedder constructible, or any
    embedding call raises) so the caller degrades to lexical retrieval — never
    fabricates vectors.
    """
    if not chunks:
        return None

    emb = embedder
    if emb is None:
        try:
            from langchain_openai import OpenAIEmbeddings  # lazy import

            from config import settings

            emb = OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                api_key=settings.openai_api_key,
            )
        except Exception:  # noqa: BLE001 — no key / import failure → lexical mode
            return None

    total = len(chunks)
    batch_size = max(1, EMBED_BATCH_SIZE)
    parts: list[np.ndarray] = []
    try:
        for start in range(0, total, batch_size):
            batch = chunks[start:start + batch_size]
            vectors = emb.embed_documents(list(batch))
            arr = np.asarray(vectors, dtype=np.float32)
            if arr.ndim != 2 or arr.shape[0] != len(batch):
                return None
            parts.append(arr)
            if on_progress is not None:
                done = min(start + len(batch), total)
                try:
                    on_progress(done, total)
                except Exception:  # noqa: BLE001 — progress must never break embedding
                    pass
    except Exception:  # noqa: BLE001 — network/quota error → lexical fallback
        return None

    matrix = np.concatenate(parts, axis=0)
    if matrix.shape[0] != total:
        return None
    return matrix


def embed_query(question: str, embedder: Optional[Any] = None) -> Optional[np.ndarray]:
    """Embed a single query string into a 1-D float32 vector, or None on failure."""
    emb = embedder
    if emb is None:
        try:
            from langchain_openai import OpenAIEmbeddings  # lazy import

            from config import settings

            emb = OpenAIEmbeddings(
                model=EMBEDDING_MODEL,
                api_key=settings.openai_api_key,
            )
        except Exception:  # noqa: BLE001
            return None
    try:
        vec = emb.embed_query(question)
        return np.asarray(vec, dtype=np.float32)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 4. ensure_index / retrieve
# ---------------------------------------------------------------------------

def ensure_index(
    doc: UploadedDoc,
    embedder: Optional[Any] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> UploadedDoc:
    """Build & cache the document's embedding index (idempotent).

    The heavy embedding now happens at UPLOAD time (called from the streaming
    /upload handler with an ``on_progress`` callback so the UI can show real batch
    progress). It also remains a SAFETY NET: if a question arrives before the index
    finished (or it was never built), this rebuilds it on demand.

    If ``doc.embeddings`` is already set, this is a no-op (the common, fast case
    after upload). Otherwise it embeds all chunks (via ``embedder``, in batches,
    forwarding ``on_progress(done, total)``) and CACHES the result back onto the
    stored doc so subsequent queries in the same session are instant. If embeddings
    are unavailable (no key / error), ``doc.embeddings`` stays None and the caller
    degrades to lexical retrieval — never fabricates vectors.

    Returns the same ``doc`` for convenience.
    """
    if doc.embeddings is None and doc.chunks:
        doc.embeddings = embed_chunks(doc.chunks, embedder, on_progress=on_progress)
    return doc


def retrieve(
    question: str,
    doc: UploadedDoc,
    k: int = DOC_TOP_K,
    embedder: Optional[Any] = None,
) -> list[Excerpt]:
    """Return the top-k most relevant chunks for ``question`` as Excerpts.

    Lazily builds & caches the embedding index on the first call (see
    ``ensure_index``), then ranks via cosine similarity over the embeddings when
    available; otherwise a transparent lexical (keyword-overlap) fallback.
    ``locator`` encodes the chunk index and an approximate page number derived from
    chunk position.
    """
    chunks = doc.chunks
    if not chunks:
        return []
    k = max(1, min(k, len(chunks)))

    # Lazy: build the embedding index on first retrieval and cache it on the doc.
    ensure_index(doc, embedder)

    if doc.embeddings is not None:
        qv = embed_query(question, embedder)
        if qv is not None and qv.shape[0] == doc.embeddings.shape[1]:
            order = _cosine_topk(qv, doc.embeddings, k)
            return [_excerpt(doc, i) for i in order]

    # Lexical fallback (degrade honestly).
    order = _lexical_topk(question, chunks, k)
    return [_excerpt(doc, i) for i in order]


def _cosine_topk(qv: np.ndarray, mat: np.ndarray, k: int) -> list[int]:
    qn = qv / (np.linalg.norm(qv) + 1e-12)
    mn = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12)
    sims = mn @ qn
    idx = np.argsort(-sims)[:k]
    return [int(i) for i in idx]


def _lexical_topk(question: str, chunks: list[str], k: int) -> list[int]:
    q_tokens = _tokens(question)
    scored: list[tuple[float, int]] = []
    for i, ch in enumerate(chunks):
        c_tokens = _tokens(ch)
        if not q_tokens or not c_tokens:
            score = 0.0
        else:
            overlap = sum(1 for t in q_tokens if t in c_tokens)
            score = overlap / (len(q_tokens) ** 0.5)
        scored.append((score, i))
    # Stable: by score desc, then original order asc.
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [i for _, i in scored[:k]]


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _excerpt(doc: UploadedDoc, chunk_index: int) -> Excerpt:
    total_chunks = max(1, len(doc.chunks))
    pages = max(1, int(doc.meta.get("pages", 1)))
    # Approximate page from chunk position (chunks are sequential).
    approx_page = min(pages, 1 + (chunk_index * pages) // total_chunks)
    locator = f"chunk {chunk_index + 1}/{total_chunks} · 约第 {approx_page} 页"
    return Excerpt(text=doc.chunks[chunk_index], locator=locator)


# ---------------------------------------------------------------------------
# 5. summarize
# ---------------------------------------------------------------------------

_SUMMARY_SYSTEM = (
    "你是一名严谨的财报阅读助手。只根据给定的文档片段，"
    "用 2-4 句中文简述这份文档是什么、核心内容是什么。"
    "严格基于原文，不得编造或推断未出现的数字与结论；"
    "无法判断的就说明信息有限。"
)


def summarize(
    doc: UploadedDoc,
    excerpts: list[Excerpt],
    llm: Optional[Any] = None,
) -> str:
    """Produce a brief grounded overview of the document from its excerpts.

    ``llm`` is injectable: any object exposing ``invoke(messages) -> message`` (the
    LangChain chat-model interface). When None, the default is the same ChatOpenAI
    configuration the agent uses. Grounded only — never fabricates. On any LLM
    error it degrades to a transparent excerpt-derived fallback (no invention).
    """
    context = "\n\n".join(f"[{e.locator}]\n{e.text}" for e in excerpts[:DOC_TOP_K])
    if not context.strip():
        return f"已读取文件「{doc.filename}」，但未检索到与问题相关的内容。"

    model = llm
    if model is None:
        try:
            from langchain_openai import ChatOpenAI  # lazy import

            from config import settings

            model = ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                api_key=settings.openai_api_key,
            )
        except Exception:  # noqa: BLE001
            return _fallback_summary(doc, excerpts)

    try:
        messages = [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"文件名：{doc.filename}\n\n以下是文档中的相关片段：\n\n{context}\n\n"
                    "请简述这份文档是什么、核心内容是什么。"
                ),
            },
        ]
        resp = model.invoke(messages)
        content = getattr(resp, "content", resp)
        text = content if isinstance(content, str) else str(content)
        text = text.strip()
        return text or _fallback_summary(doc, excerpts)
    except Exception:  # noqa: BLE001 — LLM unavailable → grounded fallback
        return _fallback_summary(doc, excerpts)


def _fallback_summary(doc: UploadedDoc, excerpts: list[Excerpt]) -> str:
    first = excerpts[0].text.strip() if excerpts else doc.text[:300]
    snippet = first[:300].replace("\n", " ")
    return (
        f"已读取文件「{doc.filename}」（约 {doc.meta.get('chars', len(doc.text))} 字）。"
        f"以下为文档相关原文摘录：{snippet}…"
    )


# ---------------------------------------------------------------------------
# Convenience: build an UploadedDoc end-to-end (used by /upload)
# ---------------------------------------------------------------------------

def build_uploaded_doc(
    data: bytes,
    filename: str,
    embedder: Optional[Any] = None,  # noqa: ARG001 — kept for signature compat
) -> UploadedDoc:
    """Extract → chunk → assemble an UploadedDoc (NO embedding here).

    Does ONLY extract text + chunk; it does NOT embed (``embeddings`` starts as
    None). The /upload handler builds the embedding index immediately afterwards
    via ``ensure_index`` (at UPLOAD time, with batch progress); ``ensure_index`` /
    ``retrieve`` also serve as a safety net that rebuilds the index on demand if a
    question somehow arrives before it finished. Raises DocumentError on
    unprocessable input.

    ``embedder`` is accepted but unused here (embedding is done by ``ensure_index``);
    kept so existing callers/tests need no signature change.
    """
    extracted = extract_text(data, filename)

    # Cap the indexed portion to DOC_MAX_INDEX_CHARS to limit embedding latency on
    # large docs (e.g. 143-page 10-K).  The full extracted text is always preserved
    # on the doc for honest reporting; only the chunked/embedded slice is bounded.
    index_truncated = len(extracted.text) > DOC_MAX_INDEX_CHARS
    index_text = extracted.text[:DOC_MAX_INDEX_CHARS] if index_truncated else extracted.text

    chunks = chunk_text(index_text)
    return UploadedDoc(
        filename=filename,
        text=extracted.text,          # full text kept for honest reporting
        chunks=chunks,                # chunked from capped slice only
        embeddings=None,              # lazily built on first question — see ensure_index
        meta={"pages": extracted.pages, "chars": extracted.chars},
        index_truncated=index_truncated,
    )
