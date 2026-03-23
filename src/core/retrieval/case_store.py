from __future__ import annotations

import json
import os
from pathlib import Path

from ..models import EvidenceItem, EvidenceSource
from .vector_store import SimpleVectorStore


class CaseStore:
    def __init__(
        self,
        chunks_path: Path | str = Path("outputs/cases/chunks.jsonl"),
        structured_chunks_path: Path | str = Path("outputs/cases/structured_chunks.jsonl"),
        index_dir: Path | str | None = None,
    ) -> None:
        self.chunks_path = Path(chunks_path)
        self.structured_chunks_path = Path(structured_chunks_path)
        resolved_index_dir = index_dir or os.getenv("CASE_INDEX_DIR", "outputs/cases/index")
        self.vector_store = SimpleVectorStore(resolved_index_dir)

    def has_cases(self) -> bool:
        return self.chunks_path.exists() or self.structured_chunks_path.exists()

    def retrieve_cases(self, query: str, top_k: int = 3) -> list[EvidenceItem]:
        results = self.vector_store.search(query, top_k=top_k)
        if not results and self.chunks_path.exists():
            self._rebuild_index()
            results = self.vector_store.search(query, top_k=top_k)

        evidence = []
        for result in results:
            metadata = result["metadata"]
            evidence.append(
                EvidenceItem(
                    source=EvidenceSource.CASE_PDF,
                    quote=result["text"][:240],
                    doc_id=metadata.get("doc_id"),
                    page_no=metadata.get("page_no"),
                    chunk_id=metadata.get("chunk_id"),
                )
            )
        return evidence

    def _rebuild_index(self) -> None:
        records = self._read_jsonl(self.chunks_path) + self._read_jsonl(self.structured_chunks_path)
        if not records:
            return
        self.vector_store.build(records)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict]:
        if not path.exists():
            return []
        records: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return records
