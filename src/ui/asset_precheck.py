from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.case_library import count_valid_structured_cases, load_structured_cases, validate_case_record
from core.knowledge_graph import load_kg_nodes
from core.pressure_trace import load_strategy_pool


MIN_SCALE_REQUIREMENTS = (
    ("Rubric 维度数量", "rubric_count", 10),
    ("赛事模板数量", "competition_template_count", 4),
    ("KG 节点数量", "kg_entity_count", 100),
    ("结构化案例数量", "structured_case_count", 50),
    ("超边数量", "hyperedge_count", 20),
    ("规则诊断池数量", "rule_count", 20),
    ("追问策略池数量", "strategy_count", 15),
)


def _count_rubrics(rubric_path: Path | str = Path("data/rubric.yaml")) -> int:
    target = Path(rubric_path)
    if not target.exists():
        return 0
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    rows = payload.get("rubrics", [])
    return len(rows) if isinstance(rows, list) else 0


def _count_case_pdfs(case_dir: Path | str = Path("data/cases")) -> int:
    target = Path(case_dir)
    if not target.exists():
        return 0
    return len(list(target.glob("*.pdf")))


def build_asset_scale_report(
    *,
    rule_specs: dict[str, dict[str, Any]],
    competition_templates: dict[str, dict[str, Any]],
    rubric_path: Path | str = Path("data/rubric.yaml"),
    kg_nodes_path: Path | str = Path("data/kg_nodes.json"),
    structured_cases_path: Path | str = Path("data/case_library/structured_cases.jsonl"),
    strategy_pool_path: Path | str = Path("data/interrogation_strategies.yaml"),
    case_pdf_dir: Path | str = Path("data/cases"),
) -> dict[str, Any]:
    strategy_pool = load_strategy_pool(strategy_pool_path)
    structured_cases = load_structured_cases(structured_cases_path)
    invalid_cases = [case.get("case_id", "<unknown>") for case in structured_cases if validate_case_record(case)]

    actuals = {
        "rubric_count": _count_rubrics(rubric_path),
        "competition_template_count": len(competition_templates),
        "kg_entity_count": len(load_kg_nodes(kg_nodes_path)),
        "structured_case_count": count_valid_structured_cases(structured_cases_path),
        "hyperedge_count": len(rule_specs),
        "rule_count": len(rule_specs),
        "strategy_count": len(strategy_pool),
    }

    rows: list[dict[str, Any]] = []
    for label, key, minimum in MIN_SCALE_REQUIREMENTS:
        actual = int(actuals.get(key, 0))
        passed = actual >= minimum
        rows.append(
            {
                "指标": label,
                "当前值": actual,
                "要求下限": minimum,
                "是否达标": "PASS" if passed else "FAIL",
                "缺口": max(0, minimum - actual),
            }
        )

    pass_count = len([row for row in rows if row["是否达标"] == "PASS"])
    return {
        "rows": rows,
        "pass_count": pass_count,
        "total_count": len(rows),
        "case_pdf_count": _count_case_pdfs(case_pdf_dir),
        "invalid_case_ids": invalid_cases,
    }
