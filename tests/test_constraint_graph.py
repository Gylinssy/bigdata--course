import json
from pathlib import Path

from core.constraint_graph import build_constraint_graph_payload, export_constraint_graph_cypher


def test_constraint_graph_links_rules_strategies_fields_and_cases(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    rows = [
        {
            "case_id": "GX001",
            "title": "YouthCare 未成年人健康助手",
            "domain": "healthtech",
            "stage": "pilot",
            "outcome": "failed",
            "summary": "项目面向未成年人健康管理，但在试点前没有补足授权和合规说明，导致推进受阻。",
            "failure_reasons": ["未成年人数据授权不足", "合规边界模糊"],
            "lessons": ["先补合规清单再做试点", "敏感场景要先确认授权链"],
            "key_metrics": {"pilot_schools": "0", "authorization_docs": "0"},
            "source": "unit_test",
        }
    ]
    cases_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows), encoding="utf-8")

    graph = build_constraint_graph_payload(cases_path=cases_path)

    node_ids = {node["node_id"] for node in graph["nodes"]}
    relationships = graph["relationships"]

    assert "rule:H11" in node_ids
    assert "field:compliance_notes" in node_ids
    assert any(rel["type"] == "USES_STRATEGY" and rel["start"] == "rule:H11" for rel in relationships)
    assert any(rel["type"] == "REMEDIATES_WITH_FIELD" and rel["start"] == "rule:H11" and rel["end"] == "field:compliance_notes" for rel in relationships)
    assert any(rel["type"] == "REFERENCES_CASE" and rel["start"] == "rule:H11" and rel["end"] == "case:GX001" for rel in relationships)


def test_constraint_graph_can_export_neo4j_cypher(tmp_path: Path) -> None:
    graph = build_constraint_graph_payload()

    cypher_path = export_constraint_graph_cypher(graph, tmp_path / "constraint_graph.cypher")
    content = cypher_path.read_text(encoding="utf-8")

    assert "MERGE (n:`ConstraintRule`" in content
    assert "MERGE (s)-[r:`REQUIRES_FIELD`]->(e)" in content
