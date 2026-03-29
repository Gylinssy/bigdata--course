from ui.visuals import _build_hypergraph_view_model


def test_build_hypergraph_view_model_exposes_hyperedges_and_fields():
    rule_specs = {
        "H1": {
            "required_fields": ["customer_segment", "value_proposition", "channel"],
            "severity": "medium",
        },
        "H2": {
            "required_fields": ["problem", "value_proposition"],
            "severity": "high",
        },
        "H3": {
            "required_fields": ["problem"],
            "severity": "low",
        },
    }

    view_model = _build_hypergraph_view_model(rule_specs)

    assert view_model["field_count"] == 4
    assert view_model["hyperedge_count"] == 3
    assert view_model["max_arity"] == 3
    assert view_model["avg_arity"] == 2.0
    assert set(view_model["fields"]) == {"customer_segment", "value_proposition", "channel", "problem"}
    assert set(view_model["left_fields"]) | set(view_model["right_fields"]) == set(view_model["fields"])
    assert set(view_model["left_fields"]) & set(view_model["right_fields"]) == set()

    first_edge = view_model["hyperedges"][0]
    assert first_edge["rule_id"] == "H2"
    assert first_edge["severity"] == "high"
    assert first_edge["edge_kind"] == "双字段超边"

    h1_edge = next(item for item in view_model["hyperedges"] if item["rule_id"] == "H1")
    assert h1_edge["members"] == ["channel", "customer_segment", "value_proposition"]
    assert h1_edge["edge_kind"] == "多字段超边"

