"""services/doc_store.py — In-memory uploaded-document store + session context.

NEW, purely additive. Holds ONE uploaded document per session (replace on
re-upload) and a contextvar carrying the current request's session_id so the
``analyze_document`` tool can find the session's doc without changing the
signatures of the existing tools.

This lives in its own module (not app.py) so BOTH app.py (the /upload + /chat
handlers) and tools.py (the analyze_document tool) can import it without a
circular import (app → agent → tools). It is completely separate from app.py's
report store; the two never interact.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from services.document import UploadedDoc

# session_id → ONE UploadedDoc (replace on re-upload).
_document_store: dict[str, UploadedDoc] = {}

# The current turn's session_id, set by the /chat and /chat/stream handlers
# BEFORE invoking the agent so analyze_document can resolve the session's doc.
# Default None → tool reports no_document (existing tools never read this).
current_session_id: ContextVar[Optional[str]] = ContextVar(
    "current_session_id", default=None
)


def put_document(session_id: str, doc: UploadedDoc) -> None:
    """Store (or replace) the session's single uploaded document."""
    _document_store[session_id] = doc


def get_document(session_id: str) -> Optional[UploadedDoc]:
    """Return the session's uploaded document, or None if none uploaded."""
    return _document_store.get(session_id)


def get_current_document() -> Optional[UploadedDoc]:
    """Return the document for the current contextvar session, or None."""
    sid = current_session_id.get()
    if sid is None:
        return None
    return _document_store.get(sid)


def clear() -> None:
    """Clear the entire document store (test helper)."""
    _document_store.clear()
