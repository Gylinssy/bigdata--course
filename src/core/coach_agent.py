from __future__ import annotations

import json
from typing import Iterable

from .hypergraph_validator import HypergraphConstraintValidator
from .llm_client import DeepSeekClient
from .models import (
    ClaimStatus,
    ConstraintValidationReport,
    DiagnosisRiskLevel,
    EvidenceItem,
    ProjectState,
    RuleResult,
    RuleStatus,
    StructuredClaim,
    StructuredDiagnosis,
)

PRIMARY_RULE_PRIORITY = {
    RuleStatus.HIGH_RISK: 4,
    RuleStatus.FAIL: 3,
    RuleStatus.WARNING: 2,
    RuleStatus.PASS: 1,
}
SEVERITY_PRIORITY = {
    "high": 3,
    "medium": 2,
    "low": 1,
}


class StructuredCoachAgent:
    def __init__(
        self,
        llm_client: DeepSeekClient | None = None,
        validator: HypergraphConstraintValidator | None = None,
        max_rewrite_attempts: int = 1,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.validator = validator or HypergraphConstraintValidator()
        self.max_rewrite_attempts = max_rewrite_attempts

    def generate(
        self,
        *,
        state: ProjectState,
        rules: list[RuleResult],
        extraction_evidence: list[EvidenceItem],
        case_evidence: list[EvidenceItem],
        project_text: str,
        fallback_task: str,
    ) -> tuple[StructuredDiagnosis, ConstraintValidationReport]:
        diagnosis = self._build_initial_output(
            state=state,
            rules=rules,
            extraction_evidence=extraction_evidence,
            case_evidence=case_evidence,
            fallback_task=fallback_task,
        )
        report = self.validator.validate(
            diagnosis,
            state=state,
            rules=rules,
            extraction_evidence=extraction_evidence,
            case_evidence=case_evidence,
            rewrite_attempted=False,
        )
        if report.passed:
            return diagnosis, report

        rewrite_attempted = False
        current = diagnosis
        if self.llm_client.available and self.max_rewrite_attempts > 0:
            rewrite_attempted = True
            for _ in range(self.max_rewrite_attempts):
                rewritten = self._rewrite_with_llm(
                    current=current,
                    report=report,
                    state=state,
                    rules=rules,
                    project_text=project_text,
                )
                if not rewritten:
                    break
                current = rewritten
                report = self.validator.validate(
                    current,
                    state=state,
                    rules=rules,
                    extraction_evidence=extraction_evidence,
                    case_evidence=case_evidence,
                    rewrite_attempted=True,
                )
                if report.passed:
                    return current, report

        repaired = self._build_initial_output(
            state=state,
            rules=rules,
            extraction_evidence=extraction_evidence,
            case_evidence=case_evidence,
            fallback_task=fallback_task,
        )
        repaired_report = self.validator.validate(
            repaired,
            state=state,
            rules=rules,
            extraction_evidence=extraction_evidence,
            case_evidence=case_evidence,
            rewrite_attempted=rewrite_attempted,
        )
        if repaired_report.passed:
            return repaired, repaired_report
        return current, report

    def _build_initial_output(
        self,
        *,
        state: ProjectState,
        rules: list[RuleResult],
        extraction_evidence: list[EvidenceItem],
        case_evidence: list[EvidenceItem],
        fallback_task: str,
    ) -> StructuredDiagnosis:
        primary_rule = self._select_primary_rule(rules)
        risk_level = self._risk_level_from_rules(rules)
        triggered_rules = [rule.rule_id for rule in rules if rule.status != RuleStatus.PASS]
        if not triggered_rules:
            triggered_rules = [primary_rule.rule_id]

        next_action = primary_rule.fix_task or fallback_task
        primary_field = self._select_primary_field(primary_rule, state)
        evidence_refs = [f"rule:{primary_rule.rule_id}"]
        if primary_field and self._state_has_value(state, primary_field):
            evidence_refs.append(f"input:{primary_field}")
        elif extraction_evidence:
            first_field = extraction_evidence[0].field
            if first_field:
                evidence_refs.append(f"input:{first_field}")
        if case_evidence and case_evidence[0].doc_id:
            evidence_refs.append(f"case:{case_evidence[0].doc_id}")

        claim_status = ClaimStatus.SUPPORTED
        diagnosis_summary = primary_rule.message
        if len(evidence_refs) == 1:
            claim_status = ClaimStatus.NEEDS_VALIDATION
            diagnosis_summary = f"{primary_rule.message}（待验证）"

        claims = [
            StructuredClaim(
                field=primary_field,
                statement=diagnosis_summary,
                evidence_refs=evidence_refs,
                status=claim_status,
            ),
            StructuredClaim(
                field="next_action",
                statement=f"建议先执行：{next_action}",
                evidence_refs=[f"rule:{primary_rule.rule_id}"],
                status=ClaimStatus.SUPPORTED,
            ),
        ]

        return StructuredDiagnosis(
            diagnosis_summary=diagnosis_summary,
            risk_level=risk_level,
            triggered_rules=triggered_rules,
            next_action=next_action,
            claims=claims,
        )

    def _rewrite_with_llm(
        self,
        *,
        current: StructuredDiagnosis,
        report: ConstraintValidationReport,
        state: ProjectState,
        rules: list[RuleResult],
        project_text: str,
    ) -> StructuredDiagnosis | None:
        if not report.violations:
            return None

        violation_lines = [f"{index}. {item.code}: {item.message}" for index, item in enumerate(report.violations, start=1)]
        schema = {
            "diagnosis_summary": "string",
            "risk_level": "normal|warning|high_risk",
            "triggered_rules": ["H1"],
            "next_action": "string",
            "claims": [
                {
                    "field": "validation_evidence|next_action|...",
                    "statement": "string",
                    "evidence_refs": ["input:validation_evidence", "rule:H9"],
                    "status": "supported|needs_validation",
                }
            ],
        }

        user_prompt = (
            "你是结构化诊断修复器。请只输出 JSON，不要 markdown。\n\n"
            "你刚才的输出违反了以下超图约束：\n"
            f"{chr(10).join(violation_lines)}\n\n"
            "请基于原始材料和规则结果重写。要求：\n"
            "1) 所有核心结论必须可追溯到 evidence_refs。\n"
            "2) evidence_refs 只能使用 input:<field> / rule:<rule_id> / case:<doc_id> / case_chunk:<chunk_id>。\n"
            "3) 若证据不足，claim.status 必须为 needs_validation，且 statement 里包含“待验证”。\n"
            "4) risk_level 必须与规则风险一致。\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"当前输出:\n{current.model_dump_json(indent=2)}\n\n"
            f"规则结果:\n{json.dumps([rule.model_dump(mode='json') for rule in rules], ensure_ascii=False, indent=2)}\n\n"
            f"项目状态:\n{state.model_dump_json(indent=2)}\n\n"
            f"原始材料:\n{project_text[:3000]}"
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt="输出必须是有效 JSON，严格遵循给定 schema。",
                user_prompt=user_prompt,
                temperature=0.0,
            )
            return StructuredDiagnosis.model_validate(data)
        except Exception:
            return None

    @staticmethod
    def _select_primary_rule(rules: Iterable[RuleResult]) -> RuleResult:
        return sorted(
            rules,
            key=lambda item: (PRIMARY_RULE_PRIORITY[item.status], SEVERITY_PRIORITY[item.severity.value]),
            reverse=True,
        )[0]

    @staticmethod
    def _risk_level_from_rules(rules: Iterable[RuleResult]) -> DiagnosisRiskLevel:
        statuses = {rule.status for rule in rules}
        if RuleStatus.HIGH_RISK in statuses:
            return DiagnosisRiskLevel.HIGH_RISK
        if RuleStatus.FAIL in statuses or RuleStatus.WARNING in statuses:
            return DiagnosisRiskLevel.WARNING
        return DiagnosisRiskLevel.NORMAL

    @staticmethod
    def _select_primary_field(primary_rule: RuleResult, state: ProjectState) -> str:
        if primary_rule.evidence:
            for item in primary_rule.evidence:
                if item.field:
                    return item.field

        fallback_map = {
            "H1": "customer_segment",
            "H2": "problem",
            "H4": "tam",
            "H5": "payer",
            "H8": "ltv",
            "H9": "validation_evidence",
            "H10": "execution_plan",
            "H11": "compliance_notes",
            "H12": "competitive_advantage",
            "H13": "retention_strategy",
            "H14": "growth_target",
            "H15": "pilot_plan",
        }
        field = fallback_map.get(primary_rule.rule_id, "rule_assessment")
        if field == "rule_assessment":
            return field
        return field if StructuredCoachAgent._state_has_value(state, field) else "rule_assessment"

    @staticmethod
    def _state_has_value(state: ProjectState, field: str) -> bool:
        value = getattr(state, field, None)
        return value not in (None, "", [], {})
