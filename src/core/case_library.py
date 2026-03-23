from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_CASE_FIELDS = (
    "case_id",
    "title",
    "domain",
    "summary",
    "outcome",
    "failure_reasons",
    "lessons",
    "key_metrics",
)


def load_structured_cases(path: Path | str = Path("data/case_library/structured_cases.jsonl")) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []

    cases: list[dict[str, Any]] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            cases.append(payload)
    return cases


def validate_case_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_CASE_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
            continue
        value = record[field]
        if value is None:
            errors.append(f"empty field: {field}")
            continue
        if isinstance(value, str) and not value.strip():
            errors.append(f"empty field: {field}")
            continue
        if field == "lessons" and isinstance(value, list) and not value:
            errors.append("lessons must contain at least one item")
            continue
        if field == "key_metrics" and isinstance(value, dict) and not value:
            errors.append("key_metrics must contain at least one metric")

    if "failure_reasons" in record and not isinstance(record.get("failure_reasons"), list):
        errors.append("failure_reasons must be a list")
    if "lessons" in record and not isinstance(record.get("lessons"), list):
        errors.append("lessons must be a list")
    if "key_metrics" in record and not isinstance(record.get("key_metrics"), dict):
        errors.append("key_metrics must be an object")
    if "outcome" in record and str(record.get("outcome", "")).lower() not in {"success", "failed", "pivot"}:
        errors.append("outcome must be one of: success|failed|pivot")
    return errors


def count_valid_structured_cases(path: Path | str = Path("data/case_library/structured_cases.jsonl")) -> int:
    total = 0
    for record in load_structured_cases(path):
        if not validate_case_record(record):
            total += 1
    return total


def build_case_retrieval_text(record: dict[str, Any]) -> str:
    metrics = record.get("key_metrics", {})
    metrics_text = ", ".join(f"{key}={value}" for key, value in metrics.items()) if isinstance(metrics, dict) else ""
    failures = "; ".join(item for item in record.get("failure_reasons", []) if isinstance(item, str))
    lessons = "; ".join(item for item in record.get("lessons", []) if isinstance(item, str))
    return (
        f"title: {record.get('title', '')}\n"
        f"domain: {record.get('domain', '')}\n"
        f"stage: {record.get('stage', '')}\n"
        f"outcome: {record.get('outcome', '')}\n"
        f"summary: {record.get('summary', '')}\n"
        f"failure_reasons: {failures}\n"
        f"lessons: {lessons}\n"
        f"key_metrics: {metrics_text}\n"
        f"source: {record.get('source', '')}"
    ).strip()


def build_structured_case_chunks(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for record in cases:
        errors = validate_case_record(record)
        if errors:
            continue
        case_id = str(record["case_id"]).strip()
        text = build_case_retrieval_text(record)
        chunks.append(
            {
                "chunk_id": f"structured-{case_id}",
                "doc_id": f"structured_case::{case_id}",
                "page_no": 1,
                "text": text,
                "start_char": 0,
                "end_char": len(text),
            }
        )
    return chunks


def export_structured_chunks(
    cases_path: Path | str = Path("data/case_library/structured_cases.jsonl"),
    output_path: Path | str = Path("outputs/cases/structured_chunks.jsonl"),
) -> int:
    cases = load_structured_cases(cases_path)
    chunks = build_structured_case_chunks(cases)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(chunk, ensure_ascii=False) for chunk in chunks]
    target.write_text("\n".join(lines), encoding="utf-8")
    return len(chunks)
