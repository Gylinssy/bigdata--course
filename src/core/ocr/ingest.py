from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from ..case_library import export_structured_chunks
from ..retrieval.vector_store import SimpleVectorStore
from .backends import BaseOCRBackend, OCRPageInput, choose_backend


@dataclass
class IngestStats:
    documents: int
    pages: int
    chunks: int
    backend: str


SUPPORTED_DOC_SUFFIXES = {".pdf", ".docx", ".pptx"}
XML_TEXT_RE = re.compile(r">([^<>]+)<")


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


def render_docx_pages(docx_path: Path) -> list[tuple[int, str]]:
    with zipfile.ZipFile(docx_path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    text = " ".join(part.strip() for part in XML_TEXT_RE.findall(xml) if part.strip())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    slices = chunk_text(text, chunk_size=1800, overlap=120)
    return [(page_no, value) for page_no, (value, _, _) in enumerate(slices, start=1)]


def render_pptx_pages(pptx_path: Path) -> list[tuple[int, str]]:
    slide_records: list[tuple[int, str]] = []
    with zipfile.ZipFile(pptx_path) as archive:
        slide_names = sorted(name for name in archive.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        for index, slide_name in enumerate(slide_names, start=1):
            xml = archive.read(slide_name).decode("utf-8", errors="ignore")
            text = " ".join(part.strip() for part in XML_TEXT_RE.findall(xml) if part.strip())
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                slide_records.append((index, text))
    return slide_records


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


def ingest_text_document(doc_path: Path, doc_id: str | None = None) -> tuple[list[dict], list[dict]]:
    doc_id = doc_id or doc_path.stem
    page_records: list[dict] = []
    chunk_records: list[dict] = []

    if doc_path.suffix.lower() == ".docx":
        pages = render_docx_pages(doc_path)
        backend_name = "docx_xml"
    elif doc_path.suffix.lower() == ".pptx":
        pages = render_pptx_pages(doc_path)
        backend_name = "pptx_xml"
    else:
        pages = []
        backend_name = "unknown"

    for page_no, text in pages:
        page_records.append(
            {
                "doc_id": doc_id,
                "page_no": page_no,
                "text": text,
                "ocr_backend": backend_name,
                "image_hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
                "doc_type": doc_path.suffix.lower().lstrip("."),
                "source_path": str(doc_path),
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
                    "doc_type": doc_path.suffix.lower().lstrip("."),
                    "source_path": str(doc_path),
                }
            )

    return page_records, chunk_records


def _discover_documents(input_dirs: list[Path]) -> list[Path]:
    discovered: list[Path] = []
    seen_signatures: set[tuple[str, int]] = set()
    for input_dir in input_dirs:
        if not input_dir.exists():
            continue
        iterator = input_dir.rglob("*") if input_dir.is_dir() else [input_dir]
        for path in iterator:
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_DOC_SUFFIXES:
                continue
            signature = (path.name.lower(), int(path.stat().st_size))
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            discovered.append(path)
    return sorted(discovered, key=lambda item: item.name.lower())


def ingest_sources(
    input_dirs: list[Path | str],
    output_dir: Path | str,
    backend_name: str = "auto",
    manifest_path: Path | None = None,
    index_dir: Path | None = None,
    backend: BaseOCRBackend | None = None,
) -> IngestStats:
    resolved_inputs = [Path(path) for path in input_dirs]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(manifest_path or (resolved_inputs[0] / "manifest.csv"))
    selected_backend = backend or choose_backend(backend_name)

    all_pages: list[dict] = []
    all_chunks: list[dict] = []
    document_paths = _discover_documents(resolved_inputs)
    for doc_path in document_paths:
        doc_id = doc_path.stem
        if doc_id in manifest:
            doc_id = manifest[doc_id].get("doc_id") or doc_id
        if doc_path.suffix.lower() == ".pdf":
            pages, chunks = ingest_pdf(doc_path, selected_backend, doc_id=doc_id)
        else:
            pages, chunks = ingest_text_document(doc_path, doc_id=doc_id)
        all_pages.extend(pages)
        all_chunks.extend(chunks)

    _write_jsonl(output_dir / "pages.jsonl", all_pages)
    _write_jsonl(output_dir / "chunks.jsonl", all_chunks)

    structured_chunks_path = output_dir / "structured_chunks.jsonl"
    structured_cases_path = Path("data/case_library/structured_cases.jsonl")
    structured_count = export_structured_chunks(structured_cases_path, structured_chunks_path)
    structured_chunks = _read_jsonl(structured_chunks_path) if structured_count > 0 else []

    index_records = all_chunks + structured_chunks
    resolved_index_dir = Path(index_dir or os.getenv("CASE_INDEX_DIR", output_dir / "index"))
    SimpleVectorStore(resolved_index_dir).build(index_records)

    return IngestStats(
        documents=len(document_paths),
        pages=len(all_pages),
        chunks=len(index_records),
        backend=selected_backend.name,
    )


def ingest_directory(
    input_dir: Path | str,
    output_dir: Path | str,
    backend_name: str = "auto",
    manifest_path: Path | None = None,
    index_dir: Path | None = None,
    backend: BaseOCRBackend | None = None,
) -> IngestStats:
    return ingest_sources(
        [input_dir],
        output_dir,
        backend_name=backend_name,
        manifest_path=manifest_path,
        index_dir=index_dir,
        backend=backend,
    )


def _write_jsonl(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines), encoding="utf-8")


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
