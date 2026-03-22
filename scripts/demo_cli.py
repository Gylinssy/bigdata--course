from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.env_utils import load_env_file  # noqa: E402
from core.models import ProjectCoachRequest  # noqa: E402
from core.pipeline import ProjectCoachPipeline  # noqa: E402

load_env_file()


def load_first_example(path: Path) -> dict:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            return json.loads(line)
    raise ValueError(f"No example found in {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the project coaching MVP on one example input.")
    parser.add_argument("--input", default="data/examples/project_inputs.jsonl", help="Path to a JSONL input file.")
    args = parser.parse_args()

    example = load_first_example(ROOT / args.input)
    pipeline = ProjectCoachPipeline()
    output = pipeline.run(ProjectCoachRequest(**example))
    print(output.markdown_report)


if __name__ == "__main__":
    main()
