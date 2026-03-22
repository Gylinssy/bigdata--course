from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import fitz

from ..retrieval.vector_store import SimpleVectorStore
from .backends import BaseOCRBackend, OCRPageInput, choose_backend


@dataclass
class IngestStats:
    documents: int
    pages: int
    chunks: int
    backend: str


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[tuple[str, int, int]]:
    clean = " ".join(text.split())
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append((clean[start:end], start, end))
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def read_manifest(manifest_path: Path) -> dict[str, dict]:
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row["doc_id"]: row for row in csv.DictReader(handle) if row.get("doc_id")}


def render_pdf_pages(pdf_path: Path) -> list[tuple[int, bytes, str]]:
    doc = fitz.open(pdf_path)
    rendered = []
    for page_index, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)
        rendered.append((page_index + 1, pix.tobytes("png"), page.get_text("text")))
    doc.close()
    return rendered


def ingest_pdf(
    pdf_path: Path,
    backend: BaseOCRBackend,
    doc_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    doc_id = doc_id or pdf_path.stem
    page_records: list[dict] = []
    chunk_records: list[dict] = []

    for page_no, image_bytes, page_text_hint in render_pdf_pages(pdf_path):
        text = backend.extract_text(OCRPageInput(image_bytes=image_bytes, page_text_hint=page_text_hint))
        page_records.append(
            {
                "doc_id": doc_id,
                "page_no": page_no,
                "text": text,
                "ocr_backend": backend.name,
                "image_hash": hashlib.md5(image_bytes).hexdigest(),
            }
        )
        for idx, (chunk_value, start_char, end_char) in enumerate(chunk_text(text), start=1):
            chunk_records.append(
                {
                    "chunk_id": f"{doc_id}-p{page_no}-c{idx}",
                    "doc_id": doc_id,
                    "page_no": page_no,
                    "text": chunk_value,
                    "start_char": start_char,
                    "end_char": end_char,
                }
            )

    return page_records, chunk_records


def ingest_directory(
    input_dir: Path | str,
    output_dir: Path | str,
    backend_name: str = "auto",
    manifest_path: Path | None = None,
    index_dir: Path | None = None,
    backend: BaseOCRBackend | None = None,
) -> IngestStats:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(manifest_path or (input_dir / "manifest.csv"))
    selected_backend = backend or choose_backend(backend_name)

    all_pages: list[dict] = []
    all_chunks: list[dict] = []
    pdf_paths = sorted(input_dir.glob("*.pdf"))
    for pdf_path in pdf_paths:
        doc_id = pdf_path.stem
        if doc_id in manifest:
            doc_id = manifest[doc_id].get("doc_id") or doc_id
        pages, chunks = ingest_pdf(pdf_path, selected_backend, doc_id=doc_id)
        all_pages.extend(pages)
        all_chunks.extend(chunks)

    _write_jsonl(output_dir / "pages.jsonl", all_pages)
    _write_jsonl(output_dir / "chunks.jsonl", all_chunks)
    resolved_index_dir = Path(index_dir or os.getenv("CASE_INDEX_DIR", output_dir / "index"))
    SimpleVectorStore(resolved_index_dir).build(all_chunks)

    return IngestStats(
        documents=len(pdf_paths),
        pages=len(all_pages),
        chunks=len(all_chunks),
        backend=selected_backend.name,
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines), encoding="utf-8")
