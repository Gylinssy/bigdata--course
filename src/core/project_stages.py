from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .models import RuleResult, RuleStatus

STAGE_SEQUENCE: tuple[str, ...] = ("idea", "mvp", "pilot")

STAGE_METADATA: dict[str, dict[str, str]] = {
    "idea": {
        "display_name": "阶段1 · 问题定义",
        "short_label": "问题定义",
        "description": "聚焦用户、问题、市场口径与渠道假设。",
    },
    "mvp": {
        "display_name": "阶段2 · MVP验证",
        "short_label": "MVP验证",
        "description": "聚焦证据、商业闭环、单位经济与可验证方案。",
    },
    "pilot": {
        "display_name": "阶段3 · 试点落地",
        "short_label": "试点落地",
        "description": "聚焦试点、执行、合规与扩张准备。",
    },
}

STAGE_ALIASES: dict[str, str] = {
    "idea": "idea",
    "concept": "idea",
    "problem_validation": "idea",
    "market_modeling": "idea",
    "competition_design": "idea",
    "channel_design": "idea",
    "mvp": "mvp",
    "prototype": "mvp",
    "validation": "mvp",
    "business_model": "mvp",
    "unit_economics": "mvp",
    "evidence_validation": "mvp",
    "mvp_validation": "mvp",
    "pilot": "pilot",
    "execution_design": "pilot",
    "risk_boundary": "pilot",
    "pilot_design": "pilot",
    "retention_design": "pilot",
    "growth_design": "pilot",
}

RULE_STAGE_BUCKETS: dict[str, str] = {
    "H1": "idea",
    "H2": "idea",
    "H4": "idea",
    "H5": "mvp",
    "H8": "mvp",
    "H9": "mvp",
    "H10": "pilot",
    "H11": "pilot",
    "H12": "idea",
    "H13": "pilot",
    "H14": "pilot",
    "H15": "pilot",
    "H16": "idea",
    "H17": "mvp",
    "H18": "idea",
    "H19": "mvp",
    "H20": "mvp",
    "H21": "pilot",
    "H22": "mvp",
    "H23": "pilot",
}


def normalize_stage_key(value: str | None, *, default: str = "idea") -> str:
    key = str(value or "").strip().lower()
    if key in STAGE_METADATA:
        return key
    if key in STAGE_ALIASES:
        return STAGE_ALIASES[key]
    return default


def stage_display_name(stage_key: str) -> str:
    return STAGE_METADATA.get(normalize_stage_key(stage_key), STAGE_METADATA["idea"])["display_name"]


def stage_short_label(stage_key: str) -> str:
    return STAGE_METADATA.get(normalize_stage_key(stage_key), STAGE_METADATA["idea"])["short_label"]


def stage_description(stage_key: str) -> str:
    return STAGE_METADATA.get(normalize_stage_key(stage_key), STAGE_METADATA["idea"])["description"]


def stage_scope(stage_key: str | None, *, cumulative: bool = True) -> list[str]:
    if not stage_key:
        return list(STAGE_SEQUENCE)
    normalized = normalize_stage_key(stage_key)
    if not cumulative:
        return [normalized]
    index = STAGE_SEQUENCE.index(normalized)
    return list(STAGE_SEQUENCE[: index + 1])


def bucket_case_stage(raw_stage: str | None) -> str:
    return normalize_stage_key(raw_stage, default="idea")


def bucket_rule_stage(rule_id: str, raw_stage_hint: str | None = None) -> str:
    if rule_id in RULE_STAGE_BUCKETS:
        return RULE_STAGE_BUCKETS[rule_id]
    return normalize_stage_key(raw_stage_hint, default="idea")


def infer_project_stage_from_rules(rules: Iterable[RuleResult | dict[str, Any]]) -> str:
    stage_has_risk = {stage_key: False for stage_key in STAGE_SEQUENCE}
    any_rule = False
    for rule in rules:
        any_rule = True
        rule_id = _rule_value(rule, "rule_id")
        status = _rule_status(rule)
        if status == RuleStatus.PASS.value:
            continue
        stage_has_risk[bucket_rule_stage(rule_id)] = True

    if not any_rule:
        return "idea"

    for stage_key in STAGE_SEQUENCE:
        if stage_has_risk[stage_key]:
            return stage_key
    return STAGE_SEQUENCE[-1]


def summarize_rule_stage_counts(rules: Iterable[RuleResult | dict[str, Any]]) -> dict[str, dict[str, int]]:
    stage_counters: dict[str, Counter[str]] = {stage_key: Counter() for stage_key in STAGE_SEQUENCE}
    for rule in rules:
        stage_key = bucket_rule_stage(_rule_value(rule, "rule_id"))
        status = _rule_status(rule)
        stage_counters[stage_key][status] += 1

    return {
        stage_key: {
            "pass": counter.get(RuleStatus.PASS.value, 0),
            "warning": counter.get(RuleStatus.WARNING.value, 0),
            "fail": counter.get(RuleStatus.FAIL.value, 0),
            "high_risk": counter.get(RuleStatus.HIGH_RISK.value, 0),
        }
        for stage_key, counter in stage_counters.items()
    }


def _rule_status(rule: RuleResult | dict[str, Any]) -> str:
    if isinstance(rule, RuleResult):
        return rule.status.value
    return str(rule.get("status", RuleStatus.PASS.value))


def _rule_value(rule: RuleResult | dict[str, Any], key: str) -> str:
    if isinstance(rule, RuleResult):
        return str(getattr(rule, key, ""))
    return str(rule.get(key, ""))
