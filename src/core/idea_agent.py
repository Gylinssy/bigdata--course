from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from .constraint_graph import FIELD_DISPLAY_NAMES as PROJECT_FIELD_LABELS
from .constraint_graph import REMEDIATION_FIELDS_BY_RULE
from .constraint_graph import ConstraintGraphView, load_constraint_graph
from .extractor import ProjectExtractor
from .llm_client import DeepSeekClient
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
    "H1": "如果你下周必须拿到第一批真实用户，他们最可能是谁？你准备先从哪个渠道接触他们？",
    "H2": "如果这个项目今天不存在，谁还会持续为这个问题付出时间、金钱或风险？你准备先用什么最小方式解决？",
    "H4": "如果评委追问市场规模，你能把总市场、可服务市场和当前阶段能拿下的市场范围说清吗？",
    "H5": "如果用户认同价值，真正掏钱的人会是谁？他为什么现在就愿意付费？",
    "H8": "如果没有外部融资，按你当前的单位经济结构，还能撑多久？",
    "H9": "如果评委追问“这不是主观想象吗”，你现在能拿出哪条最小但可信的证据？",
    "H10": "如果只给你 4 周时间和当前团队资源，你最现实的首个可交付版本是什么？",
    "H11": "如果项目涉及敏感人群、数据或决策风险，哪些合规边界必须先说清才能继续推进？",
    "H12": "如果用户不选你而去用现有替代方案，最可能是因为什么？你到底在哪个维度更强？",
    "H13": "如果用户第一次用了你的产品，什么机制会让他在 7 天或 30 天后继续回来？",
    "H14": "如果把增长目标拆到月度，你真的有足够的渠道和资源吃下这些新增吗？",
    "H15": "如果只能做一个最小试点，第一批对象是谁、怎么进入、多久判断成败？",
    "H16": "你说的目标用户，真的会在你当前选择的渠道里被有效触达并完成转化吗？",
    "H17": "如果下一个 7 天的 MVP 只能验证一个假设，你会选哪一个，为什么？",
    "H18": "即便没有直接竞品，用户现在用什么替代方案解决问题？他们为什么要切换到你这里？",
    "H19": "你现在的收入设计，真的足以覆盖交付成本并形成闭环吗？",
    "H20": "按最保守收入假设，你的现金流 runway 还有多久？最先要优化哪项成本？",
    "H21": "你使用的数据、素材或模型，授权主体和使用边界真的说清了吗？",
    "H22": "这个关键结论来自哪条可追溯证据？样本量、采集时间和偏差控制怎么说明？",
    "H23": "当前团队和资源是否真的能支撑你写下的里程碑？最小可行边界在哪里？",
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

IDEA_DIALOGUE_SYSTEM_PROMPT = (
    "You are the dialogue writer inside an entrepreneurship idea-incubation agent. "
    "Return JSON only. Answer in concise Chinese. "
    "You must stay inside the provided focus rule, missing fields, and known evidence. "
    "Do not invent facts, users, metrics, validation, or product capabilities. "
    "Keep the tone sharp, Socratic, and action-oriented."
)


class IdeaCoachAgent:
    def __init__(
        self,
        extractor: ProjectExtractor | None = None,
        rule_engine: RuleEngine | None = None,
        runtime_logger: RuntimeLogger | None = None,
        constraint_graph: ConstraintGraphView | None = None,
        llm_client: DeepSeekClient | None = None,
    ) -> None:
        self.runtime_logger = runtime_logger or RuntimeLogger()
        self.llm_client = llm_client or DeepSeekClient()
        self.extractor = extractor or ProjectExtractor(
            llm_client=self.llm_client,
            enable_llm=True,
            runtime_logger=self.runtime_logger,
        )
        self.rule_engine = rule_engine or RuleEngine()
        self.constraint_graph = constraint_graph or load_constraint_graph()

    def bootstrap(self, seed_idea: str = "") -> IdeaCoachResponse:
        run_id = new_run_id("idea-coach")
        started_at = perf_counter()
        workspace = IdeaWorkspace(seed_idea=seed_idea.strip())
        if seed_idea.strip():
            workspace.answers.update(self._extract_updates(seed_idea.strip(), [], run_id=run_id))
        self.runtime_logger.log(
            "idea_coach_agent",
            "bootstrap_started",
            run_id=run_id,
            seed_preview=preview_text(seed_idea),
        )
        response = self._compose_response(workspace, run_id=run_id)
        self.runtime_logger.log(
            "idea_coach_agent",
            "bootstrap_completed",
            run_id=run_id,
            focus_rule=response.structured_output.focus_rule_id,
            completion_ratio=response.structured_output.completion_ratio,
            used_llm=response.used_llm,
            model=response.model,
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
            updates = self._extract_updates(answer, workspace.pending_fields, run_id=run_id)
            next_workspace.turn_count += 1
            next_workspace.answers.update(updates)
        response = self._compose_response(next_workspace, run_id=run_id)
        self.runtime_logger.log(
            "idea_coach_agent",
            "turn_completed",
            run_id=run_id,
            focus_rule=response.structured_output.focus_rule_id,
            updated_fields=sorted(response.workspace.answers.keys()),
            completion_ratio=response.structured_output.completion_ratio,
            used_llm=response.used_llm,
            model=response.model,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return response

    def _compose_response(self, workspace: IdeaWorkspace, *, run_id: str | None = None) -> IdeaCoachResponse:
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
        model_name = "idea-coach-agent"
        used_llm = False

        if focus_rule is None:
            workspace.pending_fields = []
            workspace.last_focus_rule = None
            next_action = "可以先生成项目草案，再送入 A2-A4 诊断；若还想继续打磨，可转去追问增长、留存或单位经济。"
            fallback_reply = self._build_completion_reply(overview)
            reply = fallback_reply
            llm_payload = self._generate_completion_guidance_with_llm(
                overview=overview,
                project_text=project_text,
                state=state,
                next_action=next_action,
                fallback_reply=fallback_reply,
                run_id=run_id,
            )
            if llm_payload:
                reply = self._clean_generated_reply(llm_payload.get("reply"), fallback_reply)
                next_action = self._clean_generated_text(llm_payload.get("next_action"), next_action)
                used_llm = True
                model_name = self.llm_client.default_model

            output = IdeaCoachOutput(
                stage_label=stage_label,
                overview=overview,
                focus_rule_id=None,
                focus_rule_message="",
                socratic_question="基础闭环已经基本成型。",
                answer_template="",
                next_action=next_action,
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
                reply=reply,
                structured_output=output,
                workspace=workspace,
                model=model_name,
                used_llm=used_llm,
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
        edge_type = str(
            graph_context.get("edge_type")
            or trace.get("retrieved_heterogeneous_subgraph", [{}])[0].get("edge_type", "Hypergraph_Edge")
        )
        next_action = focus_rule.fix_task or "先把这一轮回答补到可诊断的最小程度。"
        related_cases = self.constraint_graph.cases_for_rule(focus_rule.rule_id, limit=2)
        fallback_reply = self._build_focus_reply(
            overview=overview,
            focus_rule=focus_rule,
            edge_type=edge_type,
            question=question,
            answer_template=answer_template,
            related_cases=related_cases,
            next_action=next_action,
            ready_for_generation=ready_for_generation,
        )
        reply = fallback_reply

        llm_payload = self._generate_focus_guidance_with_llm(
            overview=overview,
            focus_rule=focus_rule,
            question=question,
            next_action=next_action,
            target_fields=target_fields,
            project_text=project_text,
            state=state,
            graph_context=graph_context,
            edge_type=edge_type,
            answer_template=answer_template,
            related_cases=related_cases,
            ready_for_generation=ready_for_generation,
            fallback_reply=fallback_reply,
            run_id=run_id,
        )
        if llm_payload:
            reply = self._clean_generated_reply(llm_payload.get("reply"), fallback_reply)
            question = self._clean_generated_text(llm_payload.get("socratic_question"), question)
            next_action = self._clean_generated_text(llm_payload.get("next_action"), next_action)
            used_llm = True
            model_name = self.llm_client.default_model

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
            model=model_name,
            used_llm=used_llm,
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

    def _extract_updates(self, text: str, target_fields: list[str], *, run_id: str | None = None) -> dict[str, str]:
        extracted_state, _ = self.extractor.extract(text, run_id=run_id)
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

    @staticmethod
    def _build_completion_reply(overview: str) -> str:
        return (
            f"{overview}\n\n"
            "基础约束已经基本成型。你现在可以直接生成一版项目草案，并送入 A2-A4 诊断。"
        )

    @staticmethod
    def _build_focus_reply(
        *,
        overview: str,
        focus_rule: RuleResult,
        edge_type: str,
        question: str,
        answer_template: str,
        related_cases: list[dict[str, Any]],
        next_action: str,
        ready_for_generation: bool,
    ) -> str:
        reply_lines = [
            f"先不急着把 idea 写成完整 BP。{overview}",
            "",
            f"当前我先卡在 {focus_rule.rule_id} 这条超图约束（{edge_type}）：{focus_rule.message}",
            f"苏格拉底式追问：{question}",
        ]
        if answer_template:
            reply_lines.extend(["", "请尽量按这个格式回答：", answer_template])
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
        return "\n".join(reply_lines)

    def _generate_focus_guidance_with_llm(
        self,
        *,
        overview: str,
        focus_rule: RuleResult,
        question: str,
        next_action: str,
        target_fields: list[str],
        project_text: str,
        state: ProjectState,
        graph_context: dict[str, Any],
        edge_type: str,
        answer_template: str,
        related_cases: list[dict[str, Any]],
        ready_for_generation: bool,
        fallback_reply: str,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.llm_client.available:
            return None

        schema = {
            "reply": "string",
            "socratic_question": "string",
            "next_action": "string",
        }
        prompt_payload = {
            "overview": overview,
            "focus_rule_id": focus_rule.rule_id,
            "focus_rule_message": focus_rule.message,
            "edge_type": edge_type,
            "fallback_question": question,
            "fallback_next_action": next_action,
            "answer_template": answer_template,
            "fallback_reply": fallback_reply,
            "target_fields": [PROJECT_FIELD_LABELS.get(field, field) for field in target_fields],
            "known_state": state.model_dump(mode="json", exclude_none=True),
            "project_text": project_text,
            "graph_context": {
                "edge_type": graph_context.get("edge_type"),
                "remediation_fields": graph_context.get("remediation_fields"),
                "strategy_question": (graph_context.get("strategies") or [{}])[0].get("generated_question", "")
                if graph_context.get("strategies")
                else "",
            },
            "related_cases": [
                {
                    "title": case.get("title"),
                    "outcome": case.get("outcome"),
                    "domain": case.get("domain"),
                }
                for case in related_cases[:2]
            ],
            "ready_for_generation": ready_for_generation,
        }
        user_prompt = (
            "你现在是 A0 创意孵化模块里的回答生成器。你要基于超图规则焦点、字段缺口、图谱案例和当前项目状态，"
            "直接生成这一轮给学生看的完整回答，而不是做润色器。\n\n"
            "要求：\n"
            "1. 不能修改 focus_rule_id，也不能跳到别的规则。\n"
            "2. 不能编造用户、市场、验证、收入、试点等事实。\n"
            "3. reply 必须是一段完整的 A0 回复，不是摘要，也不是改写建议。\n"
            "4. reply 里必须体现：当前卡住的规则、一句苏格拉底式追问、回答模板、一个最小推进动作。\n"
            "5. socratic_question 必须是一个问题句，并且直接服务于 target_fields。\n"
            "6. next_action 只能给一个最小动作，不能写成完整 BP 目录。\n"
            "7. 只输出 JSON。\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"输入:\n{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
        )
        self.runtime_logger.log(
            "idea_coach_agent",
            "llm_guidance_started",
            run_id=run_id,
            mode="focus",
            model=self.llm_client.default_model,
            focus_rule=focus_rule.rule_id,
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt=IDEA_DIALOGUE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_client.default_model,
                temperature=0.2,
            )
        except Exception as exc:
            self.runtime_logger.log_exception(
                "idea_coach_agent",
                "llm_guidance_failed",
                run_id=run_id,
                mode="focus",
                model=self.llm_client.default_model,
                focus_rule=focus_rule.rule_id,
                error=exc,
            )
            return None

        self.runtime_logger.log(
            "idea_coach_agent",
            "llm_guidance_completed",
            run_id=run_id,
            mode="focus",
            model=self.llm_client.default_model,
            focus_rule=focus_rule.rule_id,
        )
        return data if isinstance(data, dict) else None

    def _generate_completion_guidance_with_llm(
        self,
        *,
        overview: str,
        project_text: str,
        state: ProjectState,
        next_action: str,
        fallback_reply: str,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.llm_client.available:
            return None

        schema = {
            "reply": "string",
            "next_action": "string",
        }
        prompt_payload = {
            "overview": overview,
            "known_state": state.model_dump(mode="json", exclude_none=True),
            "project_text": project_text,
            "fallback_reply": fallback_reply,
            "fallback_next_action": next_action,
        }
        user_prompt = (
            "你现在是 A0 创意孵化模块的收束回答生成器。项目的关键基础闭环已经基本成型，"
            "请直接生成这一轮完整回复，而不是只写一条润色文案。\n\n"
            "要求：\n"
            "1. 不要编造新证据或新结论。\n"
            "2. reply 要明确说明可以进入草案或诊断阶段。\n"
            "3. next_action 只能给一个最直接动作。\n"
            "4. 只输出 JSON。\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"输入:\n{json.dumps(prompt_payload, ensure_ascii=False, indent=2)}"
        )
        self.runtime_logger.log(
            "idea_coach_agent",
            "llm_guidance_started",
            run_id=run_id,
            mode="completion",
            model=self.llm_client.default_model,
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt=IDEA_DIALOGUE_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_client.default_model,
                temperature=0.2,
            )
        except Exception as exc:
            self.runtime_logger.log_exception(
                "idea_coach_agent",
                "llm_guidance_failed",
                run_id=run_id,
                mode="completion",
                model=self.llm_client.default_model,
                error=exc,
            )
            return None

        self.runtime_logger.log(
            "idea_coach_agent",
            "llm_guidance_completed",
            run_id=run_id,
            mode="completion",
            model=self.llm_client.default_model,
        )
        return data if isinstance(data, dict) else None

    @staticmethod
    def _clean_generated_text(value: object, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        cleaned = " ".join(value.strip().split())
        return cleaned or fallback

    @staticmethod
    def _clean_generated_reply(value: object, fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        lines = [line.rstrip() for line in value.strip().splitlines()]
        cleaned = "\n".join(line for line in lines if line.strip())
        return cleaned or fallback
