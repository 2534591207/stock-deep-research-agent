from __future__ import annotations

import base64
import re

import fitz

from .models import UploadedDocument


KEYWORDS = ["收入", "营收", "利润", "现金流", "风险", "指引", "revenue", "profit", "cash flow", "risk", "guidance"]


def analyze_documents(documents: list[UploadedDocument]) -> list[dict]:
    results = []
    for document in documents:
        try:
            raw = base64.b64decode(document.content_base64)
            text = extract_text(document.name, raw)
            snippets = find_relevant_snippets(text)
            results.append(
                {
                    "name": document.name,
                    "status": "completed",
                    "character_count": len(text),
                    "summary": snippets or ["已解析文件，但未找到预设财务关键词。"],
                }
            )
        except Exception as exc:
            results.append({"name": document.name, "status": "failed", "error": str(exc)})
    return results


def extract_text(name: str, raw: bytes) -> str:
    if name.lower().endswith(".pdf"):
        pdf = fitz.open(stream=raw, filetype="pdf")
        return "\n".join(page.get_text() for page in pdf)
    return raw.decode("utf-8", errors="replace")


def find_relevant_snippets(text: str, limit: int = 8) -> list[str]:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    selected = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in KEYWORDS):
            selected.append(re.sub(r"\s+", " ", line)[:300])
        if len(selected) >= limit:
            break
    return selected
