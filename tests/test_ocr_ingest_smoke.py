from pathlib import Path

import fitz

from core.ocr.backends import PdfTextBackend
from core.ocr.ingest import ingest_directory


def make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()


def test_ingest_creates_pages_and_chunks(tmp_path: Path):
    input_dir = tmp_path / "cases"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    make_pdf(input_dir / "case1.pdf", "This case shows a school health startup validating compliance risks.")

    stats = ingest_directory(input_dir, output_dir, backend=PdfTextBackend())

    pages_path = output_dir / "pages.jsonl"
    chunks_path = output_dir / "chunks.jsonl"
    assert stats.documents == 1
    assert pages_path.exists()
    assert chunks_path.exists()
    assert "case1" in pages_path.read_text(encoding="utf-8")
    assert "chunk_id" in chunks_path.read_text(encoding="utf-8")
