import json
from pathlib import Path

from core.knowledge_graph import build_knowledge_graph, export_knowledge_graph_cypher, retrieve_kg_nodes


def test_case_library_builds_knowledge_graph_with_case_domain_and_field_links(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    ontology_path = tmp_path / "ontology.yaml"

    cases_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "CASE001",
                        "title": "未成年人心理守护",
                        "domain": "edtech",
                        "stage": "pilot",
                        "outcome": "failed",
                        "summary": "项目服务未成年人，前期通过校园渠道推广，但因为授权说明不足导致试点中断。",
                        "failure_reasons": ["授权链不完整", "渠道验证不足"],
                        "lessons": ["先补授权与合规说明", "渠道验证要先做小范围试点"],
                        "key_metrics": {"pilot_schools": "2", "retention": "31%"},
                        "source": "unit_test",
                    },
                    ensure_ascii=False,
                )
            ]
        ),
        encoding="utf-8",
    )
    ontology_path.write_text(
        "project_fields:\n  - channel\n  - compliance_notes\nsensitive_domains:\n  - 未成年人\n",
        encoding="utf-8",
    )

    graph = build_knowledge_graph(cases_path=cases_path, ontology_path=ontology_path)

    node_ids = {node["node_id"] for node in graph["nodes"]}
    relationship_rows = {(row["start"], row["type"], row["end"]) for row in graph["relationships"]}

    assert graph["node_count"] == len(graph["nodes"])
    assert "case:CASE001" in node_ids
    assert "domain:edtech" in node_ids
    assert "outcome:failed" in node_ids
    assert "stage:pilot" in node_ids
    assert "field:channel" in node_ids
    assert "sensitive:未成年人" in node_ids
    assert ("case:CASE001", "HAS_DOMAIN", "domain:edtech") in relationship_rows
    assert ("case:CASE001", "HAS_OUTCOME", "outcome:failed") in relationship_rows
    assert ("case:CASE001", "HAS_STAGE", "stage:pilot") in relationship_rows
    assert ("case:CASE001", "SENSITIVE_TO", "sensitive:未成年人") in relationship_rows
    assert ("case:CASE001", "COVERS_FIELD", "field:channel") in relationship_rows


def test_knowledge_graph_exports_neo4j_cypher(tmp_path: Path) -> None:
    graph = build_knowledge_graph()

    cypher_path = export_knowledge_graph_cypher(graph, tmp_path / "knowledge_graph.cypher")
    content = cypher_path.read_text(encoding="utf-8")

    assert "MERGE (n:KGNode:`Case`" in content
    assert "MERGE (s)-[r:`HAS_DOMAIN`" in content


def test_retrieve_kg_nodes_prefers_matching_case_and_lesson_nodes(tmp_path: Path) -> None:
    cases_path = tmp_path / "cases.jsonl"
    ontology_path = tmp_path / "ontology.yaml"
    cases_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "CASE002",
                        "title": "DroneFarm 乡村配送",
                        "domain": "agritech",
                        "stage": "idea",
                        "outcome": "pivot",
                        "summary": "项目最初想做乡村无人机配送，但在渠道和支付意愿上证据不足。",
                        "failure_reasons": ["渠道错位"],
                        "lessons": ["先做农户访谈再估算支付意愿"],
                        "key_metrics": {"interviews": "3"},
                        "source": "unit_test",
                    },
                    ensure_ascii=False,
                )
            ]
        ),
        encoding="utf-8",
    )
    ontology_path.write_text("project_fields:\n  - channel\nsensitive_domains: []\n", encoding="utf-8")

    graph = build_knowledge_graph(cases_path=cases_path, ontology_path=ontology_path)
    retrieved = retrieve_kg_nodes("怎么验证农户渠道和支付意愿", graph["nodes"], top_k=4)

    labels = {item["label"] for item in retrieved}
    assert "Case" in labels
    assert "CaseLesson" in labels or "ProjectField" in labels
