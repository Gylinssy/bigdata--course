import json
from pathlib import Path

import yaml

from ui.asset_precheck import build_asset_scale_report


def test_build_asset_scale_report_works_with_custom_paths(tmp_path: Path) -> None:
    rubric_path = tmp_path / "rubric.yaml"
    rubric_path.write_text(
        yaml.safe_dump({"rubrics": [{"rubric_id": "R1"}, {"rubric_id": "R2"}]}, allow_unicode=True),
        encoding="utf-8",
    )

    kg_path = tmp_path / "kg_nodes.json"
    kg_path.write_text(json.dumps([{"node_id": "k1"}, {"node_id": "k2"}, {"node_id": "k3"}], ensure_ascii=False), encoding="utf-8")

    structured_cases_path = tmp_path / "structured_cases.jsonl"
    rows = [
        {
            "case_id": "A1",
            "title": "ok",
            "domain": "edtech",
            "summary": "ok",
            "outcome": "success",
            "failure_reasons": [],
            "lessons": ["x"],
            "key_metrics": {"k": "v"},
        },
        {"case_id": "bad"},
    ]
    structured_cases_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows), encoding="utf-8")

    strategy_path = tmp_path / "strategies.yaml"
    strategy_path.write_text(
        yaml.safe_dump({"strategies": [{"strategy_id": "S1", "name": "test"}]}, allow_unicode=True),
        encoding="utf-8",
    )

    report = build_asset_scale_report(
        rule_specs={"H1": {"required_fields": ["a"]}, "H2": {"required_fields": ["b"]}},
        competition_templates={"template-a": {}},
        rubric_path=rubric_path,
        kg_nodes_path=kg_path,
        structured_cases_path=structured_cases_path,
        strategy_pool_path=strategy_path,
        case_pdf_dir=tmp_path,
    )

    assert report["total_count"] == 7
    assert report["case_pdf_count"] == 0
    assert "bad" in report["invalid_case_ids"]
    first_row = report["rows"][0]
    assert "指标" in first_row
    assert "当前值" in first_row
