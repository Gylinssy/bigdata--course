from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.ocr.ingest import ingest_directory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR PDFs into page/chunk JSONL and build a local index.")
    parser.add_argument("--input-dir", default="data/cases", help="Directory with PDF files.")
    parser.add_argument("--output-dir", default="outputs/cases", help="Directory for OCR artifacts.")
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "deepseek_ocr", "tesseract", "pdf_text"],
        help="OCR backend preference.",
    )
    args = parser.parse_args()

    stats = ingest_directory(ROOT / args.input_dir, ROOT / args.output_dir, backend_name=args.backend)
    print(
        f"Ingested {stats.documents} docs, {stats.pages} pages, {stats.chunks} chunks "
        f"with backend={stats.backend}."
    )


if __name__ == "__main__":
    main()
