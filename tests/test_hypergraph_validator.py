from core.hypergraph_validator import HypergraphConstraintValidator
from core.models import (
    ClaimStatus,
    DiagnosisRiskLevel,
    EvidenceItem,
    EvidenceSource,
    ProjectState,
    RuleResult,
    RuleStatus,
    Severity,
    StructuredClaim,
    StructuredDiagnosis,
)


def test_validator_passes_for_consistent_structured_output():
    validator = HypergraphConstraintValidator()
    state = ProjectState(validation_evidence="已完成12份用户访谈")
    rules = [
        RuleResult(
            rule_id="H9",
            status=RuleStatus.WARNING,
            severity=Severity.MEDIUM,
            message="已有少量验证信号，但证据仍偏弱。",
            fix_task="补充访谈样本并给出转化数据。",
        )
    ]
    diagnosis = StructuredDiagnosis(
        diagnosis_summary="已有少量验证信号，但证据仍偏弱。",
        risk_level=DiagnosisRiskLevel.WARNING,
        triggered_rules=["H9"],
        next_action="补充访谈样本并给出转化数据。",
        claims=[
            StructuredClaim(
                field="validation_evidence",
                statement="已有少量验证信号，但证据仍偏弱。",
                evidence_refs=["input:validation_evidence", "rule:H9"],
                status=ClaimStatus.SUPPORTED,
            ),
            StructuredClaim(
                field="next_action",
                statement="建议先执行：补充访谈样本并给出转化数据。",
                evidence_refs=["rule:H9"],
                status=ClaimStatus.SUPPORTED,
            ),
        ],
    )
    extraction = [
        EvidenceItem(
            source=EvidenceSource.EXTRACTED_FIELD,
            quote="验证证据：已完成12份用户访谈",
            field="validation_evidence",
        )
    ]

    report = validator.validate(
        diagnosis,
        state=state,
        rules=rules,
        extraction_evidence=extraction,
        case_evidence=[],
    )

    assert report.passed is True
    assert not report.violations


def test_validator_flags_h8_contradiction_when_rule_failed():
    validator = HypergraphConstraintValidator()
    state = ProjectState(ltv=100, cac=50)
    rules = [
        RuleResult(
            rule_id="H8",
            status=RuleStatus.FAIL,
            severity=Severity.MEDIUM,
            message="单位经济不足，LTV/CAC=2.00，低于3。",
            fix_task="重算单位经济并明确提升路径。",
        )
    ]
    diagnosis = StructuredDiagnosis(
        diagnosis_summary="单位经济健康，可继续扩大投放。",
        risk_level=DiagnosisRiskLevel.WARNING,
        triggered_rules=["H8"],
        next_action="重算单位经济并明确提升路径。",
        claims=[
            StructuredClaim(
                field="ltv",
                statement="单位经济健康。",
                evidence_refs=["input:ltv", "rule:H8"],
                status=ClaimStatus.SUPPORTED,
            ),
            StructuredClaim(
                field="next_action",
                statement="建议先执行：重算单位经济并明确提升路径。",
                evidence_refs=["rule:H8"],
                status=ClaimStatus.SUPPORTED,
            ),
        ],
    )

    report = validator.validate(
        diagnosis,
        state=state,
        rules=rules,
        extraction_evidence=[],
        case_evidence=[],
    )

    assert report.passed is False
    assert any(item.code == "rule.h8_contradiction" for item in report.violations)


def test_validator_flags_unknown_evidence_reference():
    validator = HypergraphConstraintValidator()
    state = ProjectState(problem="校园心理健康支持不足")
    rules = [
        RuleResult(
            rule_id="H2",
            status=RuleStatus.WARNING,
            severity=Severity.MEDIUM,
            message="问题与方案描述重合度偏低。",
            fix_task="补问题-方案映射表。",
        )
    ]
    diagnosis = StructuredDiagnosis(
        diagnosis_summary="问题-方案映射仍需加强。",
        risk_level=DiagnosisRiskLevel.WARNING,
        triggered_rules=["H2"],
        next_action="补问题-方案映射表。",
        claims=[
            StructuredClaim(
                field="problem",
                statement="问题-方案映射仍需加强。",
                evidence_refs=["input:problem", "rule:H2", "input:not_exists"],
                status=ClaimStatus.SUPPORTED,
            ),
            StructuredClaim(
                field="next_action",
                statement="建议先执行：补问题-方案映射表。",
                evidence_refs=["rule:H2"],
                status=ClaimStatus.SUPPORTED,
            ),
        ],
    )

    report = validator.validate(
        diagnosis,
        state=state,
        rules=rules,
        extraction_evidence=[],
        case_evidence=[],
    )

    assert report.passed is False
    assert any(item.code == "claim.unknown_evidence_refs" for item in report.violations)
