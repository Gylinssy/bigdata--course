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
        index_dir: Path | str | None = None,
    ) -> None:
        self.chunks_path = Path(chunks_path)
        resolved_index_dir = index_dir or os.getenv("CASE_INDEX_DIR", "outputs/cases/index")
        self.vector_store = SimpleVectorStore(resolved_index_dir)

    def has_cases(self) -> bool:
        return self.chunks_path.exists()

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
        records = []
        for line in self.chunks_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        self.vector_store.build(records)
