from pathlib import Path
from zipfile import ZipFile

import fitz

from core.ocr.backends import PdfTextBackend
from core.ocr.ingest import ingest_directory


def make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text, fontsize=14)
    doc.save(path)
    doc.close()


def make_docx(path: Path, text: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>")


def make_pptx(path: Path, text: str) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/slides/slide1.xml", f"<p:sld><p:cSld><p:spTree><a:t>{text}</a:t></p:spTree></p:cSld></p:sld>")


def test_ingest_creates_pages_and_chunks(tmp_path: Path):
    input_dir = tmp_path / "cases"
    output_dir = tmp_path / "outputs"
    input_dir.mkdir()
    make_pdf(input_dir / "case1.pdf", "This case shows a school health startup validating compliance risks.")
    make_docx(input_dir / "case2.docx", "A data lake startup improved data cleaning quality with human-in-the-loop methods.")
    make_pptx(input_dir / "case3.pptx", "An agritech robot pilot reached a 97 percent weed kill rate.")

    stats = ingest_directory(input_dir, output_dir, backend=PdfTextBackend())

    pages_path = output_dir / "pages.jsonl"
    chunks_path = output_dir / "chunks.jsonl"
    assert stats.documents == 3
    assert pages_path.exists()
    assert chunks_path.exists()
    assert "case1" in pages_path.read_text(encoding="utf-8")
    assert "case2" in pages_path.read_text(encoding="utf-8")
    assert "case3" in pages_path.read_text(encoding="utf-8")
    assert "chunk_id" in chunks_path.read_text(encoding="utf-8")
