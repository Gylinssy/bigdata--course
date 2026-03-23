from __future__ import annotations

from typing import Iterable

from .models import (
    ClaimStatus,
    ConstraintValidationReport,
    ConstraintViolation,
    DiagnosisRiskLevel,
    EvidenceItem,
    ProjectState,
    RuleResult,
    RuleStatus,
    StructuredDiagnosis,
)


INFERENCE_MARKERS = ("推测", "待验证", "需验证", "假设")
ALLOWED_META_FIELDS = {"rule_assessment", "risk_assessment", "next_action"}
H11_CONTRADICTION_PHRASES = ("风险已基本消除", "合规风险可忽略", "无需合规准备", "可直接大规模试点")
H8_CONTRADICTION_PHRASES = ("单位经济健康", "单位经济成立", "ltv/cac健康", "盈利模型健康")


class HypergraphConstraintValidator:
    def validate(
        self,
        diagnosis: StructuredDiagnosis,
        *,
        state: ProjectState,
        rules: list[RuleResult],
        extraction_evidence: list[EvidenceItem],
        case_evidence: list[EvidenceItem],
        rewrite_attempted: bool = False,
    ) -> ConstraintValidationReport:
        violations: list[ConstraintViolation] = []
        rule_map = {rule.rule_id: rule for rule in rules}
        expected_risk_level = self._expected_risk_level(rules)
        valid_refs = self._build_valid_refs(state, rules, extraction_evidence, case_evidence)

        self._check_required_fields(diagnosis, violations)
        self._check_triggered_rules(diagnosis, rules, rule_map, violations)
        self._check_risk_level(diagnosis, expected_risk_level, violations)
        self._check_claims(diagnosis, state, valid_refs, violations)
        self._check_rule_contradictions(diagnosis, rule_map, violations)

        return ConstraintValidationReport(
            passed=not violations,
            violations=violations,
            rewrite_attempted=rewrite_attempted,
        )

    def _check_required_fields(
        self,
        diagnosis: StructuredDiagnosis,
        violations: list[ConstraintViolation],
    ) -> None:
        if not diagnosis.diagnosis_summary.strip():
            violations.append(self._violation("field.missing_summary", "diagnosis_summary 不能为空。"))
        if not diagnosis.triggered_rules:
            violations.append(self._violation("field.missing_triggered_rules", "triggered_rules 不能为空。"))
        if not diagnosis.next_action.strip():
            violations.append(self._violation("field.missing_next_action", "next_action 不能为空。"))
        if not diagnosis.claims:
            violations.append(self._violation("field.missing_claims", "claims 至少需要 1 条。"))

    def _check_triggered_rules(
        self,
        diagnosis: StructuredDiagnosis,
        rules: list[RuleResult],
        rule_map: dict[str, RuleResult],
        violations: list[ConstraintViolation],
    ) -> None:
        unknown_rules = [rule_id for rule_id in diagnosis.triggered_rules if rule_id not in rule_map]
        if unknown_rules:
            violations.append(
                self._violation(
                    "rule.unknown_triggered_rule",
                    f"triggered_rules 包含未知规则: {', '.join(sorted(set(unknown_rules)))}。",
                )
            )

        non_pass_rules = {rule.rule_id for rule in rules if rule.status != RuleStatus.PASS}
        if non_pass_rules and not (set(diagnosis.triggered_rules) & non_pass_rules):
            violations.append(
                self._violation(
                    "rule.missing_non_pass",
                    "当前存在非 pass 规则，但 triggered_rules 没有覆盖任何风险规则。",
                )
            )

    def _check_risk_level(
        self,
        diagnosis: StructuredDiagnosis,
        expected_risk_level: DiagnosisRiskLevel,
        violations: list[ConstraintViolation],
    ) -> None:
        if diagnosis.risk_level != expected_risk_level:
            violations.append(
                self._violation(
                    "risk.inconsistent_level",
                    f"risk_level={diagnosis.risk_level.value} 与规则结果不一致，应为 {expected_risk_level.value}。",
                )
            )

    def _check_claims(
        self,
        diagnosis: StructuredDiagnosis,
        state: ProjectState,
        valid_refs: set[str],
        violations: list[ConstraintViolation],
    ) -> None:
        state_fields_with_value = {
            field
            for field, value in state.model_dump().items()
            if value not in (None, "", [], {})
        }
        has_next_action_claim = False

        for index, claim in enumerate(diagnosis.claims, start=1):
            claim_label = f"claims[{index}]"
            if not claim.field.strip():
                violations.append(self._violation("claim.missing_field", f"{claim_label} 缺少 field。"))
            if not claim.statement.strip():
                violations.append(self._violation("claim.missing_statement", f"{claim_label} 缺少 statement。"))

            if claim.field == "next_action":
                has_next_action_claim = True

            unknown_refs = [ref for ref in claim.evidence_refs if ref not in valid_refs]
            if unknown_refs:
                violations.append(
                    self._violation(
                        "claim.unknown_evidence_refs",
                        f"{claim_label} evidence_refs 无法映射: {', '.join(sorted(set(unknown_refs)))}。",
                    )
                )

            if claim.status == ClaimStatus.SUPPORTED and not claim.evidence_refs:
                violations.append(
                    self._violation(
                        "claim.supported_without_evidence",
                        f"{claim_label} 标记为 supported，但缺少 evidence_refs。",
                    )
                )

            if claim.status == ClaimStatus.NEEDS_VALIDATION:
                if not self._contains_inference_marker(claim.statement):
                    violations.append(
                        self._violation(
                            "claim.inference_missing_marker",
                            f"{claim_label} 标记为 needs_validation，但 statement 未注明“推测/待验证”。",
                        )
                    )
            elif unknown_refs:
                violations.append(
                    self._violation(
                        "claim.unsupported_inference",
                        f"{claim_label} 出现未知证据引用，但未标记为 needs_validation。",
                    )
                )

            if (
                claim.field not in state_fields_with_value
                and claim.field not in ALLOWED_META_FIELDS
                and claim.status != ClaimStatus.NEEDS_VALIDATION
            ):
                violations.append(
                    self._violation(
                        "claim.field_without_support",
                        f"{claim_label} field={claim.field} 在输入材料中没有对应字段支撑。",
                    )
                )

            if (
                claim.status == ClaimStatus.SUPPORTED
                and claim.field in state_fields_with_value
                and f"input:{claim.field}" not in claim.evidence_refs
            ):
                violations.append(
                    self._violation(
                        "claim.missing_input_support",
                        f"{claim_label} 是核心字段结论，但 evidence_refs 缺少 input:{claim.field}。",
                    )
                )

        if not has_next_action_claim:
            violations.append(
                self._violation(
                    "next_action.missing_claim",
                    "next_action 需要在 claims 中有对应论证（field=next_action）。",
                )
            )

    def _check_rule_contradictions(
        self,
        diagnosis: StructuredDiagnosis,
        rule_map: dict[str, RuleResult],
        violations: list[ConstraintViolation],
    ) -> None:
        text_parts = [diagnosis.diagnosis_summary, diagnosis.next_action]
        text_parts.extend(claim.statement for claim in diagnosis.claims)
        normalized_text = " ".join(part.lower() for part in text_parts if part)

        h11 = rule_map.get("H11")
        if h11 and h11.status == RuleStatus.HIGH_RISK:
            for phrase in H11_CONTRADICTION_PHRASES:
                if phrase.lower() in normalized_text:
                    violations.append(
                        self._violation(
                            "rule.h11_contradiction",
                            f"H11=high_risk，但输出包含矛盾表述: {phrase}。",
                        )
                    )
                    break

        h8 = rule_map.get("H8")
        if h8 and h8.status == RuleStatus.FAIL:
            for phrase in H8_CONTRADICTION_PHRASES:
                if phrase.lower() in normalized_text:
                    violations.append(
                        self._violation(
                            "rule.h8_contradiction",
                            f"H8=fail，但输出包含矛盾表述: {phrase}。",
                        )
                    )
                    break

    def _build_valid_refs(
        self,
        state: ProjectState,
        rules: list[RuleResult],
        extraction_evidence: list[EvidenceItem],
        case_evidence: list[EvidenceItem],
    ) -> set[str]:
        refs: set[str] = set()
        for field, value in state.model_dump().items():
            if value not in (None, "", [], {}):
                refs.add(f"input:{field}")

        for rule in rules:
            refs.add(f"rule:{rule.rule_id}")

        for item in extraction_evidence:
            if item.field:
                refs.add(f"input:{item.field}")

        for item in case_evidence:
            if item.doc_id:
                refs.add(f"case:{item.doc_id}")
            if item.chunk_id:
                refs.add(f"case_chunk:{item.chunk_id}")

        return refs

    @staticmethod
    def _expected_risk_level(rules: Iterable[RuleResult]) -> DiagnosisRiskLevel:
        statuses = {rule.status for rule in rules}
        if RuleStatus.HIGH_RISK in statuses:
            return DiagnosisRiskLevel.HIGH_RISK
        if RuleStatus.FAIL in statuses or RuleStatus.WARNING in statuses:
            return DiagnosisRiskLevel.WARNING
        return DiagnosisRiskLevel.NORMAL

    @staticmethod
    def _contains_inference_marker(statement: str) -> bool:
        return any(marker in statement for marker in INFERENCE_MARKERS)

    @staticmethod
    def _violation(code: str, message: str) -> ConstraintViolation:
        return ConstraintViolation(code=code, message=message)
