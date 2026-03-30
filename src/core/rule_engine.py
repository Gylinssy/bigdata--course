from __future__ import annotations

import re
from pathlib import Path

import yaml

from .models import EvidenceItem, ProjectState, RuleResult, RuleStatus, Severity
from .numeric_utils import coerce_number


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
COMPETITOR_KEYWORDS = [
    "竞品", "替代", "顺丰", "邮政", "闲鱼", "转转", "notion", "obsidian", "幕布", "巨头", "竞争",
]
SUBJECTIVE_KEYWORDS = [
    "主观推测", "估计", "猜测", "感觉", "应该", "大概", "差不多", "可能会", "基本会",
]
SOCIAL_CHANNEL_KEYWORDS = ["抖音", "小红书", "快手", "instagram", "tiktok", "b站", "微博"]
ENTERPRISE_CUSTOMER_KEYWORDS = ["学校", "医院", "政府", "企业", "机构", "b端", "院系", "教务"]
HARDWARE_LOGISTICS_KEYWORDS = ["无人机", "物流", "配送", "电池", "硬件", "工厂", "仓储", "运输", "开模"]
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
            self._check_h16(state, project_text, evidence_map),
            self._check_h17(state, project_text, evidence_map),
            self._check_h18(state, project_text, evidence_map),
            self._check_h19(state, project_text, evidence_map),
            self._check_h20(state, project_text, evidence_map),
            self._check_h21(state, project_text, evidence_map),
            self._check_h22(state, project_text, evidence_map),
            self._check_h23(state, project_text, evidence_map),
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
        tam = coerce_number(state.tam)
        sam = coerce_number(state.sam)
        som = coerce_number(state.som)
        if tam is None or sam is None or som is None:
            return self._rule_result("H4", status=RuleStatus.FAIL, message="缺少或无法解析 TAM/SAM/SOM 数值。", evidence=evidence)
        if tam >= sam >= som:
            return self._rule_result("H4", status=RuleStatus.PASS, message="TAM/SAM/SOM 逻辑成立。", evidence=evidence)
        return self._rule_result(
            "H4",
            status=RuleStatus.FAIL,
            message=f"当前市场规模顺序异常：TAM={tam}, SAM={sam}, SOM={som}。",
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
        ltv = coerce_number(state.ltv)
        cac = coerce_number(state.cac)
        if ltv is None or cac is None:
            return self._rule_result(
                "H8",
                status=RuleStatus.FAIL,
                message="LTV/CAC 缺失或不是有效数值，无法判断单位经济。",
                evidence=evidence,
            )
        if cac == 0:
            return self._rule_result("H8", status=RuleStatus.WARNING, message="CAC 为 0，数据口径异常，需要重算。", evidence=evidence)
        ratio = ltv / cac
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

        som = coerce_number(state.som)
        if som is not None and target > som:
            return self._rule_result(
                "H14",
                status=RuleStatus.FAIL,
                message=f"增长目标({target:g})超过SOM({som:g})，增长假设不成立。",
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

    def _check_h16(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "customer_segment", "channel", "validation_evidence")
        if not state.customer_segment or not state.channel:
            return self._rule_result(
                "H16",
                status=RuleStatus.WARNING,
                message="客户画像或渠道信息不足，暂无法验证渠道匹配度。",
                evidence=evidence,
            )

        customer_text = " ".join(filter(None, [state.customer_segment, project_text])).lower()
        channel_text = (state.channel or "").lower()
        if "农民" in customer_text and self._contains_keywords(channel_text, SOCIAL_CHANNEL_KEYWORDS):
            return self._rule_result(
                "H16",
                status=RuleStatus.FAIL,
                message="目标客户为农民，但主渠道依赖短视频平台，渠道匹配风险较高。",
                evidence=evidence,
            )
        if self._contains_keywords(customer_text, ENTERPRISE_CUSTOMER_KEYWORDS) and self._contains_keywords(channel_text, SOCIAL_CHANNEL_KEYWORDS):
            return self._rule_result(
                "H16",
                status=RuleStatus.WARNING,
                message="面向机构/B端客户却主要依赖社媒投流，建议补充直连渠道证据。",
                evidence=evidence,
            )
        return self._rule_result(
            "H16",
            status=RuleStatus.PASS,
            message="客户与渠道关系未发现明显冲突。",
            evidence=evidence,
        )

    def _check_h17(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "problem", "value_proposition", "validation_evidence")
        if not state.problem or not state.value_proposition:
            return self._rule_result(
                "H17",
                status=RuleStatus.WARNING,
                message="问题描述或方案描述不完整，无法形成稳定映射。",
                evidence=evidence,
            )

        problem_tokens = self._meaningful_tokens(state.problem)
        value_tokens = self._meaningful_tokens(state.value_proposition)
        overlap = len(problem_tokens & value_tokens)
        improvement_markers = ["降低", "提升", "缩短", "减少", "提高", "解决"]
        value_text = " ".join(filter(None, [state.value_proposition, project_text]))
        if overlap == 0 and not self._contains_keywords(value_text, improvement_markers):
            return self._rule_result(
                "H17",
                status=RuleStatus.FAIL,
                message="方案未给出可验证改进方向，问题-方案映射较弱。",
                evidence=evidence,
            )
        if overlap <= 1:
            return self._rule_result(
                "H17",
                status=RuleStatus.WARNING,
                message="问题-方案映射仍偏弱，建议补可量化改善指标。",
                evidence=evidence,
            )
        return self._rule_result(
            "H17",
            status=RuleStatus.PASS,
            message="问题与方案映射具备一定一致性。",
            evidence=evidence,
        )

    def _check_h18(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "competitive_advantage", "customer_segment")
        text = " ".join(filter(None, [state.competitive_advantage, project_text])).lower()
        hard_risk_markers = ["没有对手", "唯一的解决方案", "根本没有竞争对手", "我们是第一家"]
        if self._contains_keywords(text, hard_risk_markers):
            return self._rule_result(
                "H18",
                status=RuleStatus.FAIL,
                message="出现“无对手”式竞争假设，缺少替代方案与迁移成本分析。",
                evidence=evidence,
            )
        if not state.competitive_advantage and not self._contains_keywords(text, COMPETITOR_KEYWORDS):
            return self._rule_result(
                "H18",
                status=RuleStatus.WARNING,
                message="竞争与替代方案描述不足，建议补竞品与防御策略。",
                evidence=evidence,
            )
        return self._rule_result(
            "H18",
            status=RuleStatus.PASS,
            message="竞争与替代方案说明基本可用。",
            evidence=evidence,
        )

    def _check_h19(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "revenue_model", "cost_structure", "payer")
        if not state.revenue_model:
            return self._rule_result(
                "H19",
                status=RuleStatus.FAIL,
                message="收入模型缺失，无法评估商业闭环。",
                evidence=evidence,
            )

        text = " ".join(filter(None, [state.revenue_model, project_text])).lower()
        if "免费" in text and not self._contains_keywords(text, ["会员", "订阅", "广告", "抽成", "服务费"]):
            return self._rule_result(
                "H19",
                status=RuleStatus.WARNING,
                message="当前以免费策略为主但缺少后续变现路径说明。",
                evidence=evidence,
            )
        if re.search(r"(每单|单价).{0,8}(1元|一元)", text) and self._contains_keywords(text, HARDWARE_LOGISTICS_KEYWORDS):
            return self._rule_result(
                "H19",
                status=RuleStatus.FAIL,
                message="低价收费与重资产场景冲突，收入模型难以覆盖成本。",
                evidence=evidence,
            )
        return self._rule_result(
            "H19",
            status=RuleStatus.PASS,
            message="收入模型未发现明显闭环冲突。",
            evidence=evidence,
        )

    def _check_h20(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "ltv", "cac", "cost_structure", "revenue_model")
        text = " ".join(filter(None, [state.cost_structure, state.revenue_model, project_text])).lower()
        if self._contains_keywords(text, HARDWARE_LOGISTICS_KEYWORDS) and re.search(r"(每单|单价).{0,8}(1元|一元|2元|两元)", text):
            return self._rule_result(
                "H20",
                status=RuleStatus.FAIL,
                message="重资产成本场景下定价过低，存在成本覆盖不足风险。",
                evidence=evidence,
            )
        ltv = coerce_number(state.ltv)
        cac = coerce_number(state.cac)
        if ltv is not None and cac is not None and cac > 0:
            ratio = ltv / cac
            if ratio < 1.5:
                return self._rule_result(
                    "H20",
                    status=RuleStatus.FAIL,
                    message=f"单位经济冗余不足，LTV/CAC={ratio:.2f}，现金流风险较高。",
                    evidence=evidence,
                )
        if not state.cost_structure:
            return self._rule_result(
                "H20",
                status=RuleStatus.WARNING,
                message="未明确成本结构，难以判断成本覆盖能力。",
                evidence=evidence,
            )
        return self._rule_result(
            "H20",
            status=RuleStatus.PASS,
            message="成本覆盖能力未发现明显异常。",
            evidence=evidence,
        )

    def _check_h21(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "compliance_notes", "value_proposition")
        text = " ".join(filter(None, [project_text, state.compliance_notes])).lower()
        ip_risk_markers = ["未授权", "省去设计费", "直接批量生产", "扫描仪建出模型", "收集了", "版权"]
        if self._contains_keywords(text, ip_risk_markers) and not state.compliance_notes:
            return self._rule_result(
                "H21",
                status=RuleStatus.HIGH_RISK,
                message="检测到版权/授权高风险表述，但缺少合规说明。",
                evidence=evidence,
            )
        if self._contains_keywords(text, ip_risk_markers):
            return self._rule_result(
                "H21",
                status=RuleStatus.WARNING,
                message="存在版权/授权敏感表述，建议补充正式授权证明。",
                evidence=evidence,
            )
        return self._rule_result(
            "H21",
            status=RuleStatus.PASS,
            message="未发现明显版权授权风险信号。",
            evidence=evidence,
        )

    def _check_h22(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "validation_evidence", "traction")
        text = " ".join(filter(None, [state.validation_evidence, state.traction, project_text])).lower()
        has_validation_signal = self._contains_keywords(text, VALIDATION_KEYWORDS)
        has_subjective_signal = self._contains_keywords(text, SUBJECTIVE_KEYWORDS)
        if "主观推测" in text and not has_validation_signal:
            return self._rule_result(
                "H22",
                status=RuleStatus.FAIL,
                message="关键需求结论基于主观推测，缺少样本验证。",
                evidence=evidence,
            )
        if has_subjective_signal and not has_validation_signal:
            return self._rule_result(
                "H22",
                status=RuleStatus.WARNING,
                message="证据来源偏主观，建议补样本、问卷或转化数据。",
                evidence=evidence,
            )
        return self._rule_result(
            "H22",
            status=RuleStatus.PASS,
            message="证据来源质量未见明显问题。",
            evidence=evidence,
        )

    def _check_h23(self, state: ProjectState, project_text: str, evidence_map: dict[str, EvidenceItem]) -> RuleResult:
        evidence = self._collect_evidence(evidence_map, "execution_plan", "pilot_plan", "traction")
        text = " ".join(filter(None, [state.execution_plan, state.pilot_plan, state.traction, project_text])).lower()
        hard_markers = [
            "3个月覆盖全国",
            "三个月覆盖全国",
            "第2个月越南建厂",
            "第 2 个月越南建厂",
            "一个月卖出2万",
            "上线第一个月卖出2万",
            "下个月去越南直接买地",
        ]
        if self._contains_keywords(text, hard_markers):
            return self._rule_result(
                "H23",
                status=RuleStatus.FAIL,
                message="里程碑扩张速度与资源条件不匹配，计划可行性较低。",
                evidence=evidence,
            )
        if re.search(r"2名|两名", text) and self._contains_keywords(text, ["覆盖全国", "建厂", "海外"]):
            return self._rule_result(
                "H23",
                status=RuleStatus.WARNING,
                message="团队规模与扩张目标可能不匹配，建议缩小试点范围。",
                evidence=evidence,
            )
        return self._rule_result(
            "H23",
            status=RuleStatus.PASS,
            message="里程碑规模与资源描述未发现明显冲突。",
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

    @staticmethod
    def _contains_keywords(text: str, keywords: list[str]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)
