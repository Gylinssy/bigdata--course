from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.ocr.ingest import ingest_sources  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest multiple case source directories into a single case index.")
    parser.add_argument("--input-dir", action="append", dest="input_dirs", default=[], help="Case source directory. Can be used multiple times.")
    parser.add_argument("--output-dir", default="outputs/cases")
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "deepseek_ocr", "tesseract", "pdf_text"],
        help="OCR backend for PDFs.",
    )
    args = parser.parse_args()

    input_dirs = args.input_dirs or ["data/cases"]
    stats = ingest_sources([ROOT / path if not Path(path).is_absolute() else Path(path) for path in input_dirs], ROOT / args.output_dir, backend_name=args.backend)
    print(f"input_dirs={input_dirs}")
    print(f"documents={stats.documents}")
    print(f"pages={stats.pages}")
    print(f"chunks={stats.chunks}")
    print(f"backend={stats.backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
