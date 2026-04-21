import json
from pathlib import Path

from core.constraint_graph import build_constraint_graph_payload, build_stage_constraint_subgraph
from core.knowledge_graph import build_knowledge_graph, build_stage_knowledge_subgraph
from core.scoring import build_unified_score_output
from ui.visuals import _build_hypergraph_view_model, _build_kg_view_model


def test_unified_score_output_infers_stage_and_repairs_missing_evidence():
    summary = build_unified_score_output(
        [
            {
                "rubric_id": "R1",
                "name": "Problem Clarity",
                "score": 4,
                "rationale": "clear",
                "evidence": [{"source": "user_input", "quote": "problem text", "field": "problem"}],
            },
            {
                "rubric_id": "R9",
                "name": "Evidence Quality",
                "score": 2,
                "rationale": "weak",
                "evidence": [],
            },
        ],
        rules=[
            {"rule_id": "H9", "status": "warning"},
            {"rule_id": "H10", "status": "pass"},
        ],
        rubric_meta_map={
            "R1": {"required_evidence": ["problem", "customer_segment"]},
            "R9": {"required_evidence": ["validation_evidence", "traction"]},
        },
        weights={"R1": 0.4, "R9": 0.6},
        template_name="test",
    )

    assert summary.stage_key == "mvp"
    assert summary.weighted_final_score == 2.8
    assert summary.low_score_dimension_count == 1
    evidence_dimension = next(item for item in summary.dimensions if item.rubric_id == "R9")
    assert evidence_dimension.missing_evidence == ["validation_evidence", "traction"]


def test_hypergraph_view_model_can_filter_by_stage():
    rule_specs = {
        "H1": {
            "required_fields": ["customer_segment", "value_proposition", "channel"],
            "severity": "medium",
        },
        "H9": {
            "required_fields": ["validation_evidence", "traction"],
            "severity": "high",
        },
        "H10": {
            "required_fields": ["execution_plan", "pilot_plan"],
            "severity": "low",
        },
    }

    idea_view = _build_hypergraph_view_model(rule_specs, stage_key="idea", cumulative=False)
    pilot_view = _build_hypergraph_view_model(rule_specs, stage_key="pilot", cumulative=False)

    assert {item["rule_id"] for item in idea_view["hyperedges"]} == {"H1"}
    assert {item["rule_id"] for item in pilot_view["hyperedges"]} == {"H10"}


def test_stage_knowledge_subgraph_filters_cases_and_preserves_node_types(tmp_path: Path):
    cases_path = tmp_path / "cases.jsonl"
    ontology_path = tmp_path / "ontology.yaml"
    rows = [
        {
            "case_id": "CASE001",
            "title": "Idea stage case",
            "domain": "edtech",
            "stage": "idea",
            "outcome": "pivot",
            "summary": "channel validation evidence",
            "failure_reasons": ["channel mismatch"],
            "lessons": ["validate early"],
            "key_metrics": {"interviews": "3"},
            "tags": ["validation"],
            "source": "unit_test",
        },
        {
            "case_id": "CASE002",
            "title": "Pilot stage case",
            "domain": "healthtech",
            "stage": "pilot",
            "outcome": "failed",
            "summary": "compliance pilot evidence",
            "failure_reasons": ["compliance gap"],
            "lessons": ["prepare consent"],
            "key_metrics": {"schools": "0"},
            "tags": ["compliance"],
            "source": "unit_test",
        },
    ]
    cases_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in rows), encoding="utf-8")
    ontology_path.write_text("project_fields:\n  - channel\n  - compliance_notes\nsensitive_domains:\n  - 未成年人\n", encoding="utf-8")

    graph = build_knowledge_graph(cases_path=cases_path, ontology_path=ontology_path)
    idea_subgraph = build_stage_knowledge_subgraph(graph, stage_key="idea", cumulative=False)
    idea_view = _build_kg_view_model(graph, max_cases=5, stage_key="idea", cumulative=False)

    case_ids = {node["node_id"] for node in idea_subgraph["nodes"] if node["label"] == "Case"}
    assert case_ids == {"case:CASE001"}
    assert idea_subgraph["case_count"] == 1
    assert any(row["label"] == "ProjectField" for row in idea_view["node_type_rows"])
    assert idea_view["node_completeness_ratio"] > 0


def test_stage_constraint_subgraph_filters_rules_by_stage():
    graph = build_constraint_graph_payload()

    idea_subgraph = build_stage_constraint_subgraph(graph, stage_key="idea", cumulative=False)
    pilot_subgraph = build_stage_constraint_subgraph(graph, stage_key="pilot", cumulative=False)

    idea_rule_ids = {node["properties"]["rule_id"] for node in idea_subgraph["nodes"] if node["label"] == "ConstraintRule"}
    pilot_rule_ids = {node["properties"]["rule_id"] for node in pilot_subgraph["nodes"] if node["label"] == "ConstraintRule"}

    assert "H1" in idea_rule_ids
    assert "H10" not in idea_rule_ids
    assert "H10" in pilot_rule_ids
