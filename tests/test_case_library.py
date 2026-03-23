import json
from pathlib import Path

from core.case_library import (
    build_structured_case_chunks,
    export_structured_chunks,
    load_structured_cases,
    validate_case_record,
)


def test_validate_case_record_detects_missing_fields() -> None:
    errors = validate_case_record({"case_id": "X1"})
    assert errors
    assert any("missing field" in item for item in errors)


def test_export_structured_chunks(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    output_path = tmp_path / "chunks.jsonl"
    rows = [
        {
            "case_id": "ok-1",
            "title": "Case A",
            "domain": "edtech",
            "stage": "mvp",
            "outcome": "success",
            "summary": "A valid case",
            "failure_reasons": [],
            "lessons": ["lesson"],
            "key_metrics": {"ltv_cac": "3.1"},
            "source": "test",
        },
        {
            "case_id": "bad-1",
            "title": "Case B",
            "domain": "edtech",
            "outcome": "failed",
            "summary": "invalid because key_metrics missing",
            "failure_reasons": ["no metrics"],
            "lessons": ["add metrics"],
            "source": "test",
        },
    ]
    cases_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    count = export_structured_chunks(cases_path, output_path)
    assert count == 1
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "structured-ok-1" in content


def test_load_and_chunk_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "structured_cases.jsonl"
    payload = {
        "case_id": "C100",
        "title": "Roundtrip",
        "domain": "saas",
        "stage": "pilot",
        "outcome": "pivot",
        "summary": "Roundtrip validation",
        "failure_reasons": ["reason"],
        "lessons": ["lesson"],
        "key_metrics": {"mrr": "1200"},
        "source": "test",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    cases = load_structured_cases(path)
    chunks = build_structured_case_chunks(cases)
    assert len(cases) == 1
    assert len(chunks) == 1
    assert chunks[0]["doc_id"] == "structured_case::C100"
