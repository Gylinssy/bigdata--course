from __future__ import annotations

from time import perf_counter

from .constraint_graph import FIELD_DISPLAY_NAMES as PROJECT_FIELD_LABELS
from .constraint_graph import REMEDIATION_FIELDS_BY_RULE
from .constraint_graph import ConstraintGraphView, load_constraint_graph
from .extractor import ProjectExtractor
from .models import (
    EvidenceItem,
    EvidenceSource,
    IdeaCoachOutput,
    IdeaCoachResponse,
    IdeaWorkspace,
    ProjectState,
    RuleResult,
    RuleStatus,
)
from .pressure_trace import build_pressure_trace
from .runtime_log import RuntimeLogger, new_run_id, preview_text
from .rule_engine import RuleEngine

TRACKED_FIELDS = (
    "problem",
    "customer_segment",
    "value_proposition",
    "channel",
    "revenue_model",
    "validation_evidence",
    "execution_plan",
    "competitive_advantage",
)

CORE_FIELDS = ("problem", "customer_segment", "value_proposition", "channel")

SOCRATIC_QUESTION_BY_RULE = {
    "H1": "如果你下周就必须拿到第一批真实用户，他们最可能是谁，又最常出现在哪个渠道或场景？",
    "H2": "如果这个项目今天不存在，谁会持续为这个问题付出时间、金钱或风险？你准备先用什么最小方式解决？",
    "H4": "如果评委要求你马上解释市场规模，你能不能把总市场、可服务市场和当前能拿下的市场分开说清？",
    "H5": "如果用户认可价值，真正掏钱的人会是谁？他为什么现在就愿意付费？",
    "H8": "如果没有外部融资，你现在这套单位经济还能撑多久？",
    "H9": "如果评委追问“你怎么证明这不是主观想象”，你现在拿得出哪条最小证据？",
    "H10": "如果只给你 4 周时间和当前团队资源，你最现实的首个可交付版本是什么？",
    "H11": "如果项目涉及敏感人群、数据或决策风险，哪些边界必须先说清才能继续推进？",
    "H12": "如果用户不选你而去用现有替代方案，最可能是因为什么？你到底在哪个维度更强？",
    "H13": "如果用户第一次用了你的产品，是什么机制会让他在 7 天或 30 天后继续回来？",
    "H14": "如果把增长目标拆到月度，你真的有足够的渠道和资源吃下这些新增吗？",
    "H15": "如果只能做一个最小试点，第一批对象是谁、怎么进入、多久判断成败？",
    "H16": "你说的目标用户，真的会在你当前选择的渠道里被有效触达并完成转化吗？",
    "H17": "如果下一个 7 天 MVP 只能验证一个假设，你会选哪一个，为什么？",
    "H18": "即便没有直接竞品，用户现在用什么替代方案解决问题？他们为什么要切换到你这里？",
    "H19": "你现在的收入设计，真的足以覆盖交付成本并形成闭环吗？",
    "H20": "按最保守收入假设，你的现金流 runway 还有多久，最先要优化哪项成本？",
    "H21": "你用到的数据、素材或模型，授权主体和使用边界真的讲得清楚吗？",
    "H22": "这个关键结论来自哪条可追溯证据？样本量、采集时间和偏差控制怎么说？",
    "H23": "当前团队和资源是否真能支撑你写下的里程碑？最小可行边界在哪里？",
}

IDEA_RULE_ORDER = {
    "H2": 1,
    "H1": 2,
    "H5": 3,
    "H9": 4,
    "H12": 5,
    "H10": 6,
    "H15": 7,
    "H17": 8,
    "H13": 9,
    "H14": 10,
    "H4": 11,
    "H19": 12,
    "H8": 13,
    "H20": 14,
    "H18": 15,
    "H21": 16,
    "H22": 17,
    "H23": 18,
    "H16": 19,
    "H11": 20,
}


class IdeaCoachAgent:
    def __init__(
        self,
        extractor: ProjectExtractor | None = None,
        rule_engine: RuleEngine | None = None,
        runtime_logger: RuntimeLogger | None = None,
        constraint_graph: ConstraintGraphView | None = None,
    ) -> None:
        self.extractor = extractor or ProjectExtractor(enable_llm=False)
        self.rule_engine = rule_engine or RuleEngine()
        self.runtime_logger = runtime_logger or RuntimeLogger()
        self.constraint_graph = constraint_graph or load_constraint_graph()

    def bootstrap(self, seed_idea: str = "") -> IdeaCoachResponse:
        run_id = new_run_id("idea-coach")
        started_at = perf_counter()
        workspace = IdeaWorkspace(seed_idea=seed_idea.strip())
        if seed_idea.strip():
            workspace.answers.update(self._extract_updates(seed_idea.strip(), []))
        self.runtime_logger.log(
            "idea_coach_agent",
            "bootstrap_started",
            run_id=run_id,
            seed_preview=preview_text(seed_idea),
        )
        response = self._compose_response(workspace)
        self.runtime_logger.log(
            "idea_coach_agent",
            "bootstrap_completed",
            run_id=run_id,
            focus_rule=response.structured_output.focus_rule_id,
            completion_ratio=response.structured_output.completion_ratio,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return response

    def step(self, workspace: IdeaWorkspace, user_input: str) -> IdeaCoachResponse:
        run_id = new_run_id("idea-coach")
        started_at = perf_counter()
        answer = user_input.strip()
        next_workspace = workspace.model_copy(deep=True)
        self.runtime_logger.log(
            "idea_coach_agent",
            "turn_started",
            run_id=run_id,
            latest_input_preview=preview_text(answer),
            last_focus_rule=workspace.last_focus_rule,
            pending_fields=workspace.pending_fields,
        )
        if answer:
            updates = self._extract_updates(answer, workspace.pending_fields)
            next_workspace.turn_count += 1
            next_workspace.answers.update(updates)
        response = self._compose_response(next_workspace)
        self.runtime_logger.log(
            "idea_coach_agent",
            "turn_completed",
            run_id=run_id,
            focus_rule=response.structured_output.focus_rule_id,
            updated_fields=sorted(response.workspace.answers.keys()),
            completion_ratio=response.structured_output.completion_ratio,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return response

    def _compose_response(self, workspace: IdeaWorkspace) -> IdeaCoachResponse:
        state = self._build_state(workspace)
        project_text = self.build_project_text(workspace, state)
        evidence = self._build_evidence(state)
        detected_rules = self.rule_engine.evaluate(state, project_text, evidence)
        focus_rule = self._select_focus_rule(detected_rules, state)
        trace = build_pressure_trace(
            detected_rules=detected_rules,
            rule_specs=self.rule_engine.rule_specs,
            case_evidence=[],
        )
        graph_context = self.constraint_graph.rule_context(focus_rule.rule_id) if focus_rule else {}
        completion_ratio = self._completion_ratio(state)
        stage_label = self._stage_label(completion_ratio)
        missing_core_fields = [field for field in CORE_FIELDS if not getattr(state, field)]
        ready_for_generation = self._ready_for_generation(state, workspace)
        ready_for_diagnosis = self._ready_for_diagnosis(state, workspace)
        overview = self._build_overview(state, detected_rules, missing_core_fields)

        if focus_rule is None:
            workspace.pending_fields = []
            workspace.last_focus_rule = None
            output = IdeaCoachOutput(
                stage_label=stage_label,
                overview=overview,
                focus_rule_id=None,
                focus_rule_message="",
                socratic_question="基础闭环已经基本成型。",
                answer_template="",
                next_action="可以先生成项目草案，再送入 A2-A4 诊断；若还想打磨，可继续追问增长、留存或单位经济。",
                generated_project_text=project_text,
                ready_for_generation=True,
                ready_for_diagnosis=True,
                completion_ratio=completion_ratio,
                missing_core_fields=missing_core_fields,
                detected_rules=detected_rules,
                hypergraph_focus=trace,
                draft_state=state,
            )
            return IdeaCoachResponse(
                reply=(
                    f"{overview}\n\n"
                "基础约束已经基本成型。你现在可以直接生成一版项目草案，并送入 A2-A4 诊断。"
                ),
                structured_output=output,
                workspace=workspace,
                model="idea-coach-agent",
                used_llm=False,
            )

        target_fields = self._target_fields_for_rule(focus_rule, state, graph_context)
        strategy_question = ""
        strategies = graph_context.get("strategies", [])
        if strategies:
            strategy_question = str(strategies[0].get("generated_question", ""))
        question = (
            SOCRATIC_QUESTION_BY_RULE.get(focus_rule.rule_id)
            or strategy_question
            or trace.get("generated_question")
            or focus_rule.probing_question
            or "先把最关键的一步说清楚。"
        )
        answer_template = self._build_answer_template(target_fields)
        workspace.pending_fields = target_fields
        workspace.last_focus_rule = focus_rule.rule_id
        edge_type = str(graph_context.get("edge_type") or trace.get("retrieved_heterogeneous_subgraph", [{}])[0].get("edge_type", "Hypergraph_Edge"))
        next_action = focus_rule.fix_task or "先把这一轮回答补到可诊断的最小程度。"
        reply_lines = [
            f"先不急着把 idea 写成完整 BP。{overview}",
            "",
            f"当前我先卡住 {focus_rule.rule_id} 这条超图约束（{edge_type}）：{focus_rule.message}",
            f"苏格拉底式追问：{question}",
        ]
        if answer_template:
            reply_lines.extend(["", "请尽量按这个格式回答：", answer_template])
        related_cases = self.constraint_graph.cases_for_rule(focus_rule.rule_id, limit=2)
        if related_cases:
            case_lines = [
                f"- {case.get('title', 'unknown')}（{case.get('outcome', 'unknown')} / {case.get('domain', 'unknown')}）"
                for case in related_cases
            ]
            reply_lines.extend(["", "可参考的图谱案例：", *case_lines])
        reply_lines.extend(["", f"这一轮的最小推进目标：{next_action}"])
        if ready_for_generation:
            reply_lines.extend(
                [
                    "",
                    "你现在已经有足够信息生成一版草案了；如果愿意，也可以直接把当前草案送入 A2-A4 诊断。",
                ]
            )
        reply = "\n".join(reply_lines)
        output = IdeaCoachOutput(
            stage_label=stage_label,
            overview=overview,
            focus_rule_id=focus_rule.rule_id,
            focus_rule_message=focus_rule.message,
            socratic_question=question,
            answer_template=answer_template,
            next_action=next_action,
            generated_project_text=project_text,
            ready_for_generation=ready_for_generation,
            ready_for_diagnosis=ready_for_diagnosis,
            completion_ratio=completion_ratio,
            missing_core_fields=missing_core_fields,
            detected_rules=detected_rules,
            hypergraph_focus={**trace, "graph_rule_context": graph_context, "graph_case_refs": related_cases},
            draft_state=state,
        )
        return IdeaCoachResponse(
            reply=reply,
            structured_output=output,
            workspace=workspace,
            model="idea-coach-agent",
            used_llm=False,
        )

    @staticmethod
    def build_project_text(workspace: IdeaWorkspace, state: ProjectState) -> str:
        lines: list[str] = []
        for field in ProjectState.model_fields:
            value = getattr(state, field)
            if value in (None, ""):
                continue
            label = PROJECT_FIELD_LABELS.get(field, field)
            lines.append(f"{label}：{IdeaCoachAgent._stringify(value)}")
        if workspace.seed_idea and workspace.seed_idea not in "\n".join(lines):
            lines.append(f"补充说明：{workspace.seed_idea}")
        if not lines and workspace.seed_idea:
            lines.append(workspace.seed_idea)
        return "\n".join(lines)

    def _extract_updates(self, text: str, target_fields: list[str]) -> dict[str, str]:
        extracted_state, _ = self.extractor.extract(text)
        updates = {
            field: self._stringify(value)
            for field, value in extracted_state.model_dump(exclude_none=True).items()
            if value not in (None, "")
        }
        if updates:
            return updates

        cleaned = text.strip()
        if not cleaned or not target_fields:
            return updates

        lines = [self._strip_possible_label(line) for line in cleaned.splitlines() if line.strip()]
        if len(target_fields) == 1:
            return {target_fields[0]: cleaned}
        if len(lines) >= len(target_fields):
            return {field: lines[index] for index, field in enumerate(target_fields)}
        if lines:
            return {target_fields[0]: lines[0]}
        return updates

    @staticmethod
    def _strip_possible_label(text: str) -> str:
        if "：" in text:
            return text.split("：", 1)[1].strip()
        if ":" in text:
            return text.split(":", 1)[1].strip()
        return text.strip()

    @staticmethod
    def _stringify(value: object) -> str:
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _build_state(workspace: IdeaWorkspace) -> ProjectState:
        payload = {field: value for field, value in workspace.answers.items() if value not in (None, "")}
        return ProjectState.model_validate(payload)

    @staticmethod
    def _build_evidence(state: ProjectState) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        for field, value in state.model_dump(exclude_none=True).items():
            evidence.append(
                EvidenceItem(
                    source=EvidenceSource.USER_INPUT,
                    quote=f"{PROJECT_FIELD_LABELS.get(field, field)}：{IdeaCoachAgent._stringify(value)}",
                    field=field,
                )
            )
        return evidence

    def _select_focus_rule(self, detected_rules: list[RuleResult], state: ProjectState) -> RuleResult | None:
        risk_rules = [rule for rule in detected_rules if rule.status != RuleStatus.PASS]
        if not risk_rules:
            return None
        high_risk_rules = [rule for rule in risk_rules if rule.status == RuleStatus.HIGH_RISK]
        if high_risk_rules:
            candidates = high_risk_rules
        else:
            missing_field_rules = [
                rule
                for rule in risk_rules
                if any(not getattr(state, field) for field in REMEDIATION_FIELDS_BY_RULE.get(rule.rule_id, []))
            ]
            candidates = missing_field_rules or risk_rules
        return sorted(
            candidates,
            key=lambda item: (
                IDEA_RULE_ORDER.get(item.rule_id, 999),
                -self.rule_engine.rank(item)[0],
                -self.rule_engine.rank(item)[1],
            ),
        )[0]

    @staticmethod
    def _target_fields_for_rule(
        rule: RuleResult,
        state: ProjectState,
        graph_context: dict[str, object] | None = None,
    ) -> list[str]:
        preferred = [str(field) for field in (graph_context or {}).get("remediation_fields", []) if str(field)]
        if not preferred:
            preferred = REMEDIATION_FIELDS_BY_RULE.get(rule.rule_id, [])
        missing = [field for field in preferred if not getattr(state, field)]
        if missing:
            return missing
        if preferred:
            return preferred
        return []

    @staticmethod
    def _build_answer_template(fields: list[str]) -> str:
        if not fields:
            return ""
        return "\n".join(f"- {PROJECT_FIELD_LABELS.get(field, field)}：" for field in fields)

    @staticmethod
    def _completion_ratio(state: ProjectState) -> float:
        filled = sum(1 for field in TRACKED_FIELDS if getattr(state, field))
        return round(filled / len(TRACKED_FIELDS), 2)

    @staticmethod
    def _stage_label(completion_ratio: float) -> str:
        if completion_ratio < 0.26:
            return "Idea 火花"
        if completion_ratio < 0.51:
            return "问题与用户定锚"
        if completion_ratio < 0.76:
            return "商业闭环收束"
        return "可生成草案"

    @staticmethod
    def _ready_for_generation(state: ProjectState, workspace: IdeaWorkspace) -> bool:
        filled_core = sum(1 for field in CORE_FIELDS if getattr(state, field))
        return filled_core >= 3 and workspace.turn_count >= 2

    @staticmethod
    def _ready_for_diagnosis(state: ProjectState, workspace: IdeaWorkspace) -> bool:
        has_foundation = all(getattr(state, field) for field in CORE_FIELDS)
        has_next_layer = bool(state.revenue_model or state.validation_evidence or state.execution_plan)
        return has_foundation and has_next_layer and workspace.turn_count >= 3

    @staticmethod
    def _build_overview(state: ProjectState, detected_rules: list[RuleResult], missing_core_fields: list[str]) -> str:
        filled_labels = [PROJECT_FIELD_LABELS[field] for field in TRACKED_FIELDS if getattr(state, field)]
        risk_rules = [rule.rule_id for rule in detected_rules if rule.status != RuleStatus.PASS][:4]
        parts: list[str] = []
        if filled_labels:
            parts.append(f"已收束字段：{'、'.join(filled_labels)}")
        else:
            parts.append("当前还处在 idea 澄清阶段，先把问题、用户、方案和渠道说清。")
        if missing_core_fields:
            parts.append(f"核心空白：{'、'.join(PROJECT_FIELD_LABELS[field] for field in missing_core_fields)}")
        if risk_rules:
            parts.append(f"当前高优先级规则：{'、'.join(risk_rules)}")
        return "；".join(parts)
