from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import EvidenceItem, ProjectState, RuleResult, RuleStatus, Severity


RULE_PRIORITY = {
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
}

STATUS_PRIORITY = {
    RuleStatus.FAIL: 4,
    RuleStatus.HIGH_RISK: 3,
    RuleStatus.WARNING: 2,
    RuleStatus.PASS: 1,
}

TOKEN_RE = re.compile(r"[A-Za-z]{3,}|[\u4e00-\u9fff]{2,}")
STOPWORDS = {
    "项目", "用户", "客户", "方案", "产品", "平台", "系统", "服务", "帮助", "提供", "通过", "实现",
    "一个", "我们", "他们", "能够", "用于", "进行", "以及", "相关", "核心", "目标",
}

VALIDATION_KEYWORDS = [
    "访谈", "问卷", "试点", "测试", "内测", "验证", "留存", "转化", "复购", "点击", "预约", "报名", "样本", "反馈",
]

EXECUTION_KEYWORDS = [
    "里程碑", "版本", "排期", "负责人", "开发", "上线", "试运行", "时间表", "周", "月", "第一阶段", "第二阶段", "试点",
]

BENEFICIARY_KEYWORDS = ["学生", "家长", "老师", "患者", "医生", "老人", "儿童", "用户", "消费者"]
PAYER_KEYWORDS = ["学校", "医院", "企业", "机构", "政府", "家长", "平台", "商家", "B端", "教育局"]
DIFFERENTIATION_KEYWORDS = [
    "差异化", "独特", "优势", "壁垒", "护城河", "更快", "更准", "更低成本", "竞品", "替代方案",
]
RETENTION_KEYWORDS = [
    "留存", "复购", "续费", "订阅", "月活", "周活", "使用频次", "召回", "复访",
]
PILOT_KEYWORDS = [
    "试点", "首批", "样板", "合作方", "试运行", "上线", "验证周期", "验收指标", "退出条件",
]
NUMBER_RE = re.compile(r"(-?\d+(?:,\d{3})*(?:\.\d+)?)")


class RuleEngine:
    def __init__(self, rules_dir: Path | str = Path("data/hyper_rules")) -> None:
        self.rules_dir = Path(rules_dir)
        self.rule_specs = self._load_rules()

    def evaluate(self, state: ProjectState, project_text: str, evidence: list[EvidenceItem]) -> list[RuleResult]:
        evidence_map = {item.field: item for item in evidence if item.field}
        return [
            self._check_h1(state, evidence_map),
            self._check_h2(state, evidence_map),
            self._check_h4(state, evidence_map),
            self._check_h5(state, project_text, evidence_map),
            self._check_h8(state, evidence_map),
            self._check_h9(state, project_text, evidence_map),
            self._check_h10(state, project_text, evidence_map),
            self._check_h11(state, project_text, evidence_map),
            self._check_h12(state, project_text, evidence_map),
            self._check_h13(state, project_text, evidence_map),
            self._check_h14(state, project_text, evidence_map),
            self._check_h15(state, project_text, evidence_map),
        ]

    def rank(self, rule: RuleResult) -> tuple[int, int]:
        return (RULE_PRIORITY[rule.severity], STATUS_PRIORITY[rule.status])

    def _load_rules(self) -> dict[str, dict]:
        specs: dict[str, dict] = {}
        for path in sorted(self.rules_dir.glob("*.yaml")):
            specs[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8"))
        return specs

    def _rule_result(
        self,
        rule_id: str,
        *,
        status: RuleStatus,
        message: str,
        evidence: list[EvidenceItem],
    ) -> RuleResult:
        spec = self.rule_specs[rule_id]
        return RuleResult(
            rule_id=rule_id,
            status=status,
            severity=Severity(spec["severity"]),
            message=message,
            probing_question=spec.get("probing_question"),
            fix_task=spec.get("fix_task"),
            evidence=evidence,
        )

    def _check_h1(self, state: ProjectState, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "customer_segment", "value_proposition", "channel")
        missing = [field for field in ("customer_segment", "value_proposition", "channel") if not getattr(state, field)]
        if missing:
            return self._rule_result(
                "H1",
                status=RuleStatus.FAIL,
                message=f"客户-价值-渠道链路不完整，缺少: {', '.join(missing)}。",
                evidence=evidence,
            )

        customer = (state.customer_segment or "").lower()
        channel = (state.channel or "").lower()
        risky_pairs = [
            (r"(医院|学校|政府|企业|b2b)", r"(抖音|小红书|快手|朋友圈)"),
            (r"(家长|老师|中学|未成年)", r"(博彩|酒吧|夜店)"),
        ]
        for customer_pattern, channel_pattern in risky_pairs:
            if re.search(customer_pattern, customer) and re.search(channel_pattern, channel):
                return self._rule_result(
                    "H1",
                    status=RuleStatus.WARNING,
                    message="目标客户与当前渠道匹配度偏低，可能导致获客效率受损。",
                    evidence=evidence,
                )

        return self._rule_result(
            "H1",
            status=RuleStatus.PASS,
            message="客户、价值主张与渠道链路基本完整。",
            evidence=evidence,
        )

    def _check_h2(self, state: ProjectState, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "problem", "value_proposition")
        if not state.problem or not state.value_proposition:
            return self._rule_result(
                "H2",
                status=RuleStatus.FAIL,
                message="缺少问题定义或价值主张，无法判断问题-方案是否匹配。",
                evidence=evidence,
            )

        problem_tokens = self._meaningful_tokens(state.problem)
        value_tokens = self._meaningful_tokens(state.value_proposition)
        overlap = problem_tokens & value_tokens
        if overlap:
            return self._rule_result(
                "H2",
                status=RuleStatus.PASS,
                message=f"问题与方案存在直接呼应，重合关键词: {', '.join(sorted(overlap)[:4])}。",
                evidence=evidence,
            )

        return self._rule_result(
            "H2",
            status=RuleStatus.WARNING,
            message="问题定义与方案描述几乎没有关键词重合，需警惕方案没有直接回应痛点。",
            evidence=evidence,
        )

    def _check_h4(self, state: ProjectState, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "tam", "sam", "som")
        if state.tam is None or state.sam is None or state.som is None:
            return self._rule_result("H4", status=RuleStatus.FAIL, message="缺少 TAM/SAM/SOM 关键数据。", evidence=evidence)
        if state.tam >= state.sam >= state.som:
            return self._rule_result("H4", status=RuleStatus.PASS, message="TAM/SAM/SOM 逻辑成立。", evidence=evidence)
        return self._rule_result(
            "H4",
            status=RuleStatus.FAIL,
            message=f"当前市场规模顺序异常：TAM={state.tam}, SAM={state.sam}, SOM={state.som}。",
            evidence=evidence,
        )

    def _check_h5(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "customer_segment", "revenue_model", "payer")
        if not state.customer_segment or not state.revenue_model:
            return self._rule_result(
                "H5",
                status=RuleStatus.FAIL,
                message="缺少客户对象或收入模式，无法判断付费逻辑。",
                evidence=evidence,
            )

        customer_text = state.customer_segment
        revenue_text = " ".join(filter(None, [state.revenue_model, state.payer, project_text]))
        has_beneficiary = any(keyword in customer_text for keyword in BENEFICIARY_KEYWORDS)
        has_payer_signal = any(keyword in revenue_text for keyword in PAYER_KEYWORDS)
        if has_beneficiary and has_payer_signal and not state.payer:
            return self._rule_result(
                "H5",
                status=RuleStatus.WARNING,
                message="看起来存在使用者与付费者分离，但没有明确说明谁来付费和谁做决策。",
                evidence=evidence,
            )
        return self._rule_result(
            "H5",
            status=RuleStatus.PASS,
            message="当前付费逻辑至少有基本说明，未发现明显的角色错位。",
            evidence=evidence,
        )

    def _check_h8(self, state: ProjectState, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "ltv", "cac")
        if state.ltv is None or state.cac is None:
            return self._rule_result("H8", status=RuleStatus.FAIL, message="缺少 LTV/CAC 数据，无法判断单位经济。", evidence=evidence)
        if state.cac == 0:
            return self._rule_result("H8", status=RuleStatus.WARNING, message="CAC 为 0，数据口径异常，需要重算。", evidence=evidence)
        ratio = state.ltv / state.cac
        if ratio >= 3:
            return self._rule_result("H8", status=RuleStatus.PASS, message=f"单位经济成立，LTV/CAC={ratio:.2f}。", evidence=evidence)
        return self._rule_result("H8", status=RuleStatus.FAIL, message=f"单位经济不足，LTV/CAC={ratio:.2f}，低于 3。", evidence=evidence)

    def _check_h9(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "validation_evidence", "traction", "problem")
        validation_text = " ".join(filter(None, [state.validation_evidence, state.traction, project_text]))
        signal_count = sum(1 for keyword in VALIDATION_KEYWORDS if keyword in validation_text)
        if signal_count == 0:
            return self._rule_result(
                "H9",
                status=RuleStatus.FAIL,
                message="没有看到访谈、问卷、试点或转化数据，需求判断缺少验证证据。",
                evidence=evidence,
            )
        if signal_count == 1:
            return self._rule_result(
                "H9",
                status=RuleStatus.WARNING,
                message="已有少量验证信号，但证据仍偏弱，建议补更明确的用户验证数据。",
                evidence=evidence,
            )
        return self._rule_result(
            "H9",
            status=RuleStatus.PASS,
            message="需求验证已有初步证据支持。",
            evidence=evidence,
        )

    def _check_h10(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "execution_plan", "traction", "cost_structure")
        execution_text = " ".join(filter(None, [state.execution_plan, state.traction, state.cost_structure, project_text]))
        signal_count = sum(1 for keyword in EXECUTION_KEYWORDS if keyword in execution_text)
        if not state.execution_plan and not state.traction:
            return self._rule_result(
                "H10",
                status=RuleStatus.FAIL,
                message="没有执行计划或阶段进展描述，方案落地路径不清晰。",
                evidence=evidence,
            )
        if signal_count < 2:
            return self._rule_result(
                "H10",
                status=RuleStatus.WARNING,
                message="执行计划信息偏弱，尚未清楚说明时间节点、版本范围或负责人。",
                evidence=evidence,
            )
        return self._rule_result(
            "H10",
            status=RuleStatus.PASS,
            message="执行路径已有基本说明，具备初步落地计划。",
            evidence=evidence,
        )

    def _check_h11(
        self,
        state: ProjectState,
        project_text: str,
        evidence_map: dict[str, EvidenceItem],
    ) -> RuleResult:
        text = " ".join(filter(None, [project_text, state.problem, state.customer_segment, state.value_proposition])).lower()
        sensitive_hits = re.findall(r"(医疗|金融|学生|未成年|隐私|健康|心理|诊断|支付|征信)", text)
        evidence = self._collect_evidence(evidence_map, "problem", "customer_segment", "compliance_notes")
        if sensitive_hits and not state.compliance_notes:
            return self._rule_result(
                "H11",
                status=RuleStatus.HIGH_RISK,
                message=f"命中敏感领域关键词 {sorted(set(sensitive_hits))}，但未看到合规说明。",
                evidence=evidence,
            )
        return self._rule_result(
            "H11",
            status=RuleStatus.PASS,
            message="未发现明显的敏感领域合规缺口，或已提供合规说明。",
            evidence=evidence,
        )

    def _check_h12(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "competitive_advantage", "value_proposition")
        text = " ".join(filter(None, [state.competitive_advantage, state.value_proposition, project_text]))
        signal_count = sum(1 for keyword in DIFFERENTIATION_KEYWORDS if keyword in text)
        if not state.competitive_advantage and signal_count < 2:
            return self._rule_result(
                "H12",
                status=RuleStatus.FAIL,
                message="没有看到清晰的竞品对比或差异化说明，竞争优势不明确。",
                evidence=evidence,
            )
        if signal_count < 3:
            return self._rule_result(
                "H12",
                status=RuleStatus.WARNING,
                message="存在差异化描述，但竞争壁垒证据偏弱。",
                evidence=evidence,
            )
        return self._rule_result(
            "H12",
            status=RuleStatus.PASS,
            message="已给出初步差异化与竞争优势说明。",
            evidence=evidence,
        )

    def _check_h13(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "retention_strategy", "revenue_model", "traction")
        text = " ".join(filter(None, [state.retention_strategy, state.revenue_model, state.traction, project_text]))
        signal_count = sum(1 for keyword in RETENTION_KEYWORDS if keyword in text)
        if signal_count == 0:
            return self._rule_result(
                "H13",
                status=RuleStatus.FAIL,
                message="没有看到留存或复购机制描述，增长可能依赖一次性获客。",
                evidence=evidence,
            )
        if signal_count == 1:
            return self._rule_result(
                "H13",
                status=RuleStatus.WARNING,
                message="留存机制描述较弱，建议补明确的留存目标与触发机制。",
                evidence=evidence,
            )
        return self._rule_result(
            "H13",
            status=RuleStatus.PASS,
            message="留存/复购机制有初步设计。",
            evidence=evidence,
        )

    def _check_h14(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "growth_target", "som", "channel")
        if not state.growth_target:
            return self._rule_result(
                "H14",
                status=RuleStatus.FAIL,
                message="未提供阶段增长目标，无法校验增长假设是否可行。",
                evidence=evidence,
            )

        target = self._extract_first_number(state.growth_target)
        if target is None:
            return self._rule_result(
                "H14",
                status=RuleStatus.WARNING,
                message="增长目标存在文字描述，但缺少可计算的目标数值。",
                evidence=evidence,
            )

        if state.som is not None and target > state.som:
            return self._rule_result(
                "H14",
                status=RuleStatus.FAIL,
                message=f"增长目标({target:g})超过SOM({state.som:g})，增长假设不成立。",
                evidence=evidence,
            )

        text = " ".join(filter(None, [state.growth_target, project_text]))
        if not any(keyword in text for keyword in ("季度", "月", "年", "阶段")):
            return self._rule_result(
                "H14",
                status=RuleStatus.WARNING,
                message="增长目标缺少时间维度，尚不能形成可执行追踪。",
                evidence=evidence,
            )

        return self._rule_result(
            "H14",
            status=RuleStatus.PASS,
            message="增长目标与时间维度基本清晰，未发现明显规模冲突。",
            evidence=evidence,
        )

    def _check_h15(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "pilot_plan", "execution_plan", "traction")
        text = " ".join(filter(None, [state.pilot_plan, state.execution_plan, state.traction, project_text]))
        signal_count = sum(1 for keyword in PILOT_KEYWORDS if keyword in text)
        if not state.pilot_plan and signal_count < 2:
            return self._rule_result(
                "H15",
                status=RuleStatus.FAIL,
                message="试点路径不明确，缺少首批对象、进入路径或验收节奏。",
                evidence=evidence,
            )
        if signal_count < 3:
            return self._rule_result(
                "H15",
                status=RuleStatus.WARNING,
                message="试点计划有初步方向，但缺少关键执行细节。",
                evidence=evidence,
            )
        return self._rule_result(
            "H15",
            status=RuleStatus.PASS,
            message="试点路径已有可执行描述。",
            evidence=evidence,
        )

    @staticmethod
    def _collect_evidence(evidence_map: dict[str, EvidenceItem], *fields: str) -> list[EvidenceItem]:
        return [evidence_map[field] for field in fields if field in evidence_map]

    @staticmethod
    def _meaningful_tokens(text: str) -> set[str]:
        tokens = {token.lower() for token in TOKEN_RE.findall(text)}
        return {token for token in tokens if token not in STOPWORDS and len(token) >= 2}

    @staticmethod
    def _extract_first_number(text: str) -> float | None:
        match = NUMBER_RE.search(text)
        if not match:
            return None
        return float(match.group(1).replace(",", ""))
