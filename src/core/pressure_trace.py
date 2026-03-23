from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import EvidenceItem, RuleResult, RuleStatus


STATUS_PRIORITY = {
    RuleStatus.HIGH_RISK: 4,
    RuleStatus.FAIL: 3,
    RuleStatus.WARNING: 2,
    RuleStatus.PASS: 1,
}

FALLACY_BY_RULE = {
    "H4": "大数幻觉谬误",
    "H8": "单位经济幻觉",
    "H9": "证据缺失谬误",
    "H12": "竞争认知缺失",
    "H16": "渠道错配谬误",
    "H18": "无竞争对手谬误",
    "H19": "盈利闭环断裂",
    "H20": "现金流生存谬误",
    "H21": "合规授权盲区",
    "H22": "主观推测替代证据",
    "H23": "里程碑可行性幻觉",
}

EDGE_TYPE_BY_RULE = {
    "H1": "Value_Loop_Edge",
    "H2": "Value_Loop_Edge",
    "H4": "Market_Sizing_Edge",
    "H5": "Revenue_Logic_Edge",
    "H8": "Unit_Economics_Edge",
    "H9": "Evidence_Validation_Edge",
    "H10": "Execution_Path_Edge",
    "H11": "Risk_Pattern_Edge",
    "H12": "Competition_Defense_Edge",
    "H13": "Retention_Growth_Edge",
    "H14": "Growth_Constraint_Edge",
    "H15": "Pilot_Readiness_Edge",
    "H16": "Channel_Fit_Edge",
    "H17": "Problem_Solution_Edge",
    "H18": "Competition_Defense_Edge",
    "H19": "Revenue_Logic_Edge",
    "H20": "Unit_Economics_Edge",
    "H21": "Risk_Pattern_Edge",
    "H22": "Evidence_Validation_Edge",
    "H23": "Execution_Path_Edge",
}

STRATEGY_BY_RULE = {
    "H4": "S01_market_scope_calibration",
    "H16": "S02_channel_precision_probe",
    "H8": "S03_unit_econ_survival",
    "H18": "S04_hidden_competitor_probe",
    "H12": "S05_switching_cost_probe",
    "H22": "S06_evidence_traceback",
    "H15": "S07_pilot_scope_narrowing",
    "H23": "S08_resource_feasibility_check",
    "H11": "S09_compliance_boundary_check",
    "H21": "S10_ip_authorization_chain",
    "H14": "S11_growth_reality_check",
    "H13": "S12_retention_cohort_probe",
    "H19": "S13_pricing_wtp_probe",
    "H20": "S14_runway_stress_check",
    "H17": "S15_mvp_validation_cycle",
}


def load_strategy_pool(
    path: Path | str = Path("data/interrogation_strategies.yaml"),
) -> dict[str, dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    rows = payload.get("strategies", [])
    result: dict[str, dict[str, Any]] = {}
    if not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict):
            continue
        strategy_id = row.get("strategy_id")
        if not strategy_id:
            continue
        result[str(strategy_id)] = row
    return result


def build_pressure_trace(
    *,
    detected_rules: list[RuleResult],
    rule_specs: dict[str, dict[str, Any]],
    case_evidence: list[EvidenceItem],
    strategy_pool: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pool = strategy_pool or load_strategy_pool()
    risk_rules = [rule for rule in detected_rules if rule.status != RuleStatus.PASS]
    risk_rules.sort(key=lambda item: STATUS_PRIORITY[item.status], reverse=True)
    top_rule = risk_rules[0] if risk_rules else None

    strategy_id = STRATEGY_BY_RULE.get(top_rule.rule_id if top_rule else "", "S06_evidence_traceback")
    strategy = pool.get(strategy_id, {})
    generated_question = ""
    if top_rule and top_rule.probing_question:
        generated_question = top_rule.probing_question
    elif isinstance(strategy.get("generated_question"), str):
        generated_question = strategy["generated_question"]
    else:
        generated_question = "请补充一个可验证证据，说明你的核心假设为何成立。"

    subgraph = []
    for rule in risk_rules[:3]:
        spec = rule_specs.get(rule.rule_id, {})
        subgraph.append(
            {
                "rule_id": rule.rule_id,
                "edge_type": EDGE_TYPE_BY_RULE.get(rule.rule_id, "Risk_Pattern_Edge"),
                "required_fields": spec.get("required_fields", []),
            }
        )

    context_nodes: list[str] = []
    for item in subgraph:
        for field in item.get("required_fields", []):
            if field not in context_nodes:
                context_nodes.append(field)

    doc_ids = sorted({item.doc_id for item in case_evidence if item.doc_id})
    trace = {
        "agent_name": "project_coach",
        "fallacy_label": FALLACY_BY_RULE.get(top_rule.rule_id if top_rule else "", "未触发显著谬误"),
        "rule_triggered": [rule.rule_id for rule in risk_rules],
        "retrieved_heterogeneous_subgraph": subgraph,
        "retrieved_context_nodes": context_nodes,
        "retrieved_case_docs": doc_ids,
        "selected_strategy": strategy_id,
        "selected_strategy_name": strategy.get("name", strategy_id),
        "generated_question": generated_question,
    }
    return trace


def pressure_trace_to_text(trace: dict[str, Any]) -> str:
    return json.dumps(trace, ensure_ascii=False, indent=2)
