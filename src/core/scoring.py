from __future__ import annotations

from typing import Any

from .models import RuleResult, RubricScore, ScoreDimension, UnifiedScoreOutput
from .project_stages import infer_project_stage_from_rules, stage_display_name


def build_unified_score_output(
    rubric_scores: list[RubricScore | dict[str, Any]],
    *,
    rules: list[RuleResult | dict[str, Any]] | None = None,
    rubric_meta_map: dict[str, dict[str, Any]] | None = None,
    weights: dict[str, float] | None = None,
    template_name: str = "统一评分",
) -> UnifiedScoreOutput:
    normalized_scores = [_as_rubric_score(item) for item in rubric_scores]
    weights = weights or {}
    rubric_meta_map = rubric_meta_map or {}

    dimensions: list[ScoreDimension] = []
    total_score = 0.0
    weight_total = 0.0
    evidence_covered = 0

    for item in normalized_scores:
        weight = float(weights.get(item.rubric_id, 1.0 if not weights else 0.0))
        weighted_score = item.score * weight
        missing_evidence, fix_24h, fix_72h = _build_remediation(item, rubric_meta_map.get(item.rubric_id, {}))
        evidence_count = len(item.evidence)
        if evidence_count > 0:
            evidence_covered += 1
        total_score += float(item.score)
        weight_total += weight
        dimensions.append(
            ScoreDimension(
                rubric_id=item.rubric_id,
                name=item.name,
                score=float(item.score),
                weight=round(weight, 4),
                weighted_score=round(weighted_score, 4),
                score_band=_score_band(float(item.score)),
                rationale=item.rationale,
                evidence_count=evidence_count,
                missing_evidence=missing_evidence,
                fix_24h=fix_24h,
                fix_72h=fix_72h,
            )
        )

    average_score = round(total_score / len(dimensions), 2) if dimensions else 0.0
    if weight_total > 0:
        weighted_final_score = round(sum(item.weighted_score for item in dimensions) / weight_total, 2)
    else:
        weighted_final_score = average_score

    dimensions.sort(key=lambda item: (item.score, item.name))
    weakest = [item.name for item in dimensions[:3]]
    strongest = [item.name for item in sorted(dimensions, key=lambda item: (-item.score, item.name))[:3]]

    stage_key = infer_project_stage_from_rules(rules or [])
    stage_label = stage_display_name(stage_key)
    summary = _build_summary(
        stage_label=stage_label,
        weighted_final_score=weighted_final_score,
        score_band=_score_band(weighted_final_score),
        weakest_dimensions=weakest,
    )
    risk_rule_count = len([rule for rule in rules or [] if _rule_status(rule) != "pass"])
    high_risk_rule_count = len([rule for rule in rules or [] if _rule_status(rule) == "high_risk"])

    return UnifiedScoreOutput(
        template_name=template_name,
        average_score=average_score,
        weighted_final_score=weighted_final_score,
        score_band=_score_band(weighted_final_score),
        stage_key=stage_key,
        stage_label=stage_label,
        evidence_coverage_ratio=round(evidence_covered / len(dimensions), 2) if dimensions else 0.0,
        strongest_dimensions=strongest,
        weakest_dimensions=weakest,
        low_score_dimension_count=len([item for item in dimensions if item.score <= 2.0]),
        risk_rule_count=risk_rule_count,
        high_risk_rule_count=high_risk_rule_count,
        dimensions=dimensions,
        summary=summary,
    )


def build_item_reports(score_output: UnifiedScoreOutput) -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "estimated_score": f"{int(item.score) if float(item.score).is_integer() else item.score}/5",
            "missing_evidence": "；".join(item.missing_evidence) if item.missing_evidence else "当前维度证据基本齐全。",
            "fix_24h": item.fix_24h,
            "fix_72h": item.fix_72h,
        }
        for item in score_output.dimensions
    ]


def _build_remediation(item: RubricScore, rubric_meta: dict[str, Any]) -> tuple[list[str], str, str]:
    required_fields = rubric_meta.get("required_evidence", []) if isinstance(rubric_meta.get("required_evidence"), list) else []
    common_mistakes = rubric_meta.get("common_mistakes", []) if isinstance(rubric_meta.get("common_mistakes"), list) else []
    evidence_fields = {evidence.field for evidence in item.evidence if evidence.field}
    missing = [str(field) for field in required_fields if field not in evidence_fields]

    if item.score <= 2 and not missing:
        missing = [str(common_mistakes[0])] if common_mistakes else ["证据链未覆盖该维度的关键字段"]

    if not missing:
        return (
            [],
            "补充 1 条最新验证数据并复核该维度评分依据。",
            "完成一次小范围迭代验证并更新证据链。",
        )

    return (
        missing,
        f"补齐最关键缺口：{missing[0]}，并提交对应证据。",
        "按缺口完成扩展验证：补样本、补对照、补复盘，并更新评分。",
    )


def _build_summary(
    *,
    stage_label: str,
    weighted_final_score: float,
    score_band: str,
    weakest_dimensions: list[str],
) -> str:
    weakness_text = "、".join(weakest_dimensions[:2]) if weakest_dimensions else "暂无明显短板"
    return f"{stage_label}，综合评分 {weighted_final_score}/5，当前等级 {score_band}，优先修复：{weakness_text}。"


def _score_band(score: float) -> str:
    if score >= 4.2:
        return "strong"
    if score >= 3.4:
        return "stable"
    if score >= 2.5:
        return "warning"
    return "critical"


def _rule_status(rule: RuleResult | dict[str, Any]) -> str:
    if isinstance(rule, RuleResult):
        return rule.status.value
    return str(rule.get("status", "pass"))


def _as_rubric_score(item: RubricScore | dict[str, Any]) -> RubricScore:
    if isinstance(item, RubricScore):
        return item
    return RubricScore.model_validate(item)
