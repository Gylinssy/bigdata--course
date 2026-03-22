from __future__ import annotations

from typing import Iterable

from .models import EvidenceItem, EvidenceSource


def dedupe_evidence(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
    seen: set[tuple[str, str | None, int | None, str | None]] = set()
    result: list[EvidenceItem] = []
    for item in items:
        key = (item.quote, item.doc_id, item.page_no, item.field)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def format_evidence(item: EvidenceItem) -> str:
    if item.source == EvidenceSource.CASE_PDF:
        page = f" p.{item.page_no}" if item.page_no is not None else ""
        doc_id = item.doc_id or "unknown"
        return f'[case: {doc_id}{page}] "{item.quote}"'
    field = f"{item.field}: " if item.field else ""
    return f"{field}{item.quote}"
