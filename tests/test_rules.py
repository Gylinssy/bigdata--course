from core.models import EvidenceItem, EvidenceSource, ProjectState, RuleStatus
from core.rule_engine import RuleEngine


def test_h2_warns_when_problem_and_solution_do_not_align():
    engine = RuleEngine()
    evidence = [
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="问题：校园心理健康服务不足", field="problem"),
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="价值主张：提供跨境电商选品工具", field="value_proposition"),
    ]
    state = ProjectState(problem="校园心理健康服务不足", value_proposition="提供跨境电商选品工具")
    result = next(rule for rule in engine.evaluate(state, state.problem or "", evidence) if rule.rule_id == "H2")
    assert result.status == RuleStatus.WARNING


def test_h4_requires_tam_sam_som_order():
    engine = RuleEngine()
    state = ProjectState(tam=100, sam=200, som=10)
    result = next(rule for rule in engine.evaluate(state, "", []) if rule.rule_id == "H4")
    assert result.status == RuleStatus.FAIL


def test_h4_accepts_numeric_strings_with_units():
    engine = RuleEngine()
    state = ProjectState.model_construct(tam="10万亿", sam="5万亿", som="1万亿")
    result = next(rule for rule in engine.evaluate(state, "", []) if rule.rule_id == "H4")
    assert result.status == RuleStatus.PASS


def test_h5_warns_when_payer_is_not_explained():
    engine = RuleEngine()
    evidence = [
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="客户：学生和家长", field="customer_segment"),
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="收入模式：按学校采购收费", field="revenue_model"),
    ]
    state = ProjectState(customer_segment="学生和家长", revenue_model="按学校采购收费")
    result = next(rule for rule in engine.evaluate(state, state.revenue_model or "", evidence) if rule.rule_id == "H5")
    assert result.status == RuleStatus.WARNING


def test_h8_requires_healthy_ltv_cac_ratio():
    engine = RuleEngine()
    evidence = [
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="LTV 100", field="ltv"),
        EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="CAC 50", field="cac"),
    ]
    state = ProjectState(ltv=100, cac=50)
    result = next(rule for rule in engine.evaluate(state, "", evidence) if rule.rule_id == "H8")
    assert result.status == RuleStatus.FAIL


def test_h8_handles_non_numeric_strings_without_crashing():
    engine = RuleEngine()
    state = ProjectState.model_construct(ltv="极高", cac="几乎为0")
    result = next(rule for rule in engine.evaluate(state, "", []) if rule.rule_id == "H8")
    assert result.status == RuleStatus.FAIL


def test_h9_fails_without_validation_signals():
    engine = RuleEngine()
    state = ProjectState(problem="大学生需要更好的求职辅导")
    result = next(rule for rule in engine.evaluate(state, state.problem or "", []) if rule.rule_id == "H9")
    assert result.status == RuleStatus.FAIL


def test_h10_fails_without_execution_plan_or_progress():
    engine = RuleEngine()
    state = ProjectState(value_proposition="提供 AI 助教工具")
    result = next(rule for rule in engine.evaluate(state, state.value_proposition or "", []) if rule.rule_id == "H10")
    assert result.status == RuleStatus.FAIL


def test_h11_marks_sensitive_project_without_compliance_notes():
    engine = RuleEngine()
    state = ProjectState(problem="为未成年人做心理诊断", customer_segment="中学学生")
    result = next(rule for rule in engine.evaluate(state, state.problem or "", []) if rule.rule_id == "H11")
    assert result.status == RuleStatus.HIGH_RISK


def test_h12_fails_without_differentiation_evidence():
    engine = RuleEngine()
    state = ProjectState(value_proposition="我们提供在线学习平台")
    result = next(rule for rule in engine.evaluate(state, state.value_proposition or "", []) if rule.rule_id == "H12")
    assert result.status == RuleStatus.FAIL


def test_h13_fails_without_retention_mechanism():
    engine = RuleEngine()
    state = ProjectState(revenue_model="按次收费")
    result = next(rule for rule in engine.evaluate(state, state.revenue_model or "", []) if rule.rule_id == "H13")
    assert result.status == RuleStatus.FAIL


def test_h14_fails_without_growth_target():
    engine = RuleEngine()
    state = ProjectState(som=10000)
    result = next(rule for rule in engine.evaluate(state, "", []) if rule.rule_id == "H14")
    assert result.status == RuleStatus.FAIL


def test_h15_fails_without_pilot_plan():
    engine = RuleEngine()
    state = ProjectState(value_proposition="为中学提供心理测评工具")
    result = next(rule for rule in engine.evaluate(state, state.value_proposition or "", []) if rule.rule_id == "H15")
    assert result.status == RuleStatus.FAIL
