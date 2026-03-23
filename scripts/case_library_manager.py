from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.case_library import (  # noqa: E402
    build_structured_case_chunks,
    export_structured_chunks,
    load_structured_cases,
    validate_case_record,
)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def cmd_template(args: argparse.Namespace) -> int:
    output = Path(args.output)
    rows: list[dict[str, Any]] = []
    for idx in range(1, args.count + 1):
        rows.append(
            {
                "case_id": f"TEMPLATE_{idx:03d}",
                "title": "TODO",
                "domain": "TODO",
                "stage": "idea",
                "outcome": "pivot",
                "summary": "TODO: concise case summary in 3-6 sentences",
                "failure_reasons": ["TODO_reason_1", "TODO_reason_2"],
                "lessons": ["TODO_lesson_1", "TODO_lesson_2"],
                "key_metrics": {"TODO_metric": "TODO_value"},
                "source": "TODO_source",
            }
        )
    _write_jsonl(output, rows)
    print(f"template created: {output} ({len(rows)} rows)")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.input)
    rows = _load_jsonl(path)
    valid = 0
    invalid = 0
    for row in rows:
        errors = validate_case_record(row)
        if errors:
            invalid += 1
            if args.verbose:
                case_id = row.get("case_id", "<unknown>")
                print(f"[invalid] {case_id}: {'; '.join(errors)}")
            continue
        valid += 1
    print(f"input={path}")
    print(f"total={len(rows)} valid={valid} invalid={invalid}")
    return 0 if invalid == 0 else 1


def cmd_append(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    target_path = Path(args.target)

    source_rows = _load_jsonl(source_path)
    target_rows = _load_jsonl(target_path)
    existing_ids = {str(row.get("case_id")).strip() for row in target_rows if row.get("case_id")}

    accepted: list[dict[str, Any]] = []
    rejected = 0
    for row in source_rows:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id or case_id in existing_ids:
            rejected += 1
            continue
        if validate_case_record(row):
            rejected += 1
            continue
        accepted.append(row)
        existing_ids.add(case_id)

    merged = target_rows + accepted
    _write_jsonl(target_path, merged)
    print(f"target={target_path}")
    print(f"merged_total={len(merged)} appended={len(accepted)} rejected={rejected}")
    return 0


def cmd_export_chunks(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_path = Path(args.output)
    count = export_structured_chunks(input_path, output_path)
    print(f"structured chunk file: {output_path}")
    print(f"chunk_count={count}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    rows = load_structured_cases(Path(args.input))
    valid_rows = [row for row in rows if not validate_case_record(row)]
    outcomes = Counter(str(row.get("outcome", "unknown")) for row in valid_rows)
    domains = Counter(str(row.get("domain", "unknown")) for row in valid_rows)
    chunk_count = len(build_structured_case_chunks(valid_rows))

    print(f"input={args.input}")
    print(f"total_rows={len(rows)}")
    print(f"valid_rows={len(valid_rows)}")
    print(f"chunk_count={chunk_count}")
    print(f"top_outcomes={dict(outcomes.most_common(5))}")
    print(f"top_domains={dict(domains.most_common(8))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Structured case library helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("template", help="Generate template JSONL rows.")
    template_parser.add_argument("--output", default="data/case_library/new_cases_template.jsonl")
    template_parser.add_argument("--count", type=int, default=10)
    template_parser.set_defaults(func=cmd_template)

    validate_parser = subparsers.add_parser("validate", help="Validate structured case JSONL.")
    validate_parser.add_argument("--input", default="data/case_library/structured_cases.jsonl")
    validate_parser.add_argument("--verbose", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    append_parser = subparsers.add_parser("append", help="Append new valid cases into target JSONL.")
    append_parser.add_argument("--input", required=True)
    append_parser.add_argument("--target", default="data/case_library/structured_cases.jsonl")
    append_parser.set_defaults(func=cmd_append)

    export_parser = subparsers.add_parser("export-chunks", help="Export structured cases into vector chunks.")
    export_parser.add_argument("--input", default="data/case_library/structured_cases.jsonl")
    export_parser.add_argument("--output", default="outputs/cases/structured_chunks.jsonl")
    export_parser.set_defaults(func=cmd_export_chunks)

    stats_parser = subparsers.add_parser("stats", help="Print case library stats.")
    stats_parser.add_argument("--input", default="data/case_library/structured_cases.jsonl")
    stats_parser.set_defaults(func=cmd_stats)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
