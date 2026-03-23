from core.models import EvidenceItem, EvidenceSource, ProjectState
from core.pressure_trace import build_pressure_trace, pressure_trace_to_text
from core.rule_engine import RuleEngine


def test_build_pressure_trace_contains_required_observability_fields() -> None:
    engine = RuleEngine()
    state = ProjectState(
        customer_segment="全国农民",
        channel="抖音投流",
        competitive_advantage="我们没有对手",
        revenue_model="每单1元",
        cost_structure="无人机与电池成本",
    )
    evidence = [
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="客户：全国农民", field="customer_segment"),
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="渠道：抖音投流", field="channel"),
    ]
    rules = engine.evaluate(state, "我们没有对手，每单1元。", evidence)
    trace = build_pressure_trace(
        detected_rules=rules,
        rule_specs=engine.rule_specs,
        case_evidence=[],
    )

    assert trace["agent_name"] == "project_coach"
    assert "fallacy_label" in trace
    assert "retrieved_heterogeneous_subgraph" in trace
    assert "selected_strategy" in trace
    assert "generated_question" in trace
    assert isinstance(trace["rule_triggered"], list)

    text = pressure_trace_to_text(trace)
    assert "selected_strategy" in text
