from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from .knowledge_graph import load_kg_nodes, retrieve_kg_nodes
from .llm_client import DeepSeekClient
from .models import (
    LearningConstraintReport,
    LearningConstraintViolation,
    LearningMode,
    LearningTutorOutput,
    LearningTutorResponse,
)
from .runtime_log import RuntimeLogger, new_run_id, preview_text


GHOSTWRITING_MARKERS = (
    "代写",
    "直接写",
    "帮我写完",
    "写一篇",
    "可直接提交",
    "不用我改",
    "1000字",
    "2000字",
)

EMOTIONAL_MARKERS = (
    "太难",
    "不想思考",
    "随便",
    "交差",
    "帮我直接写完",
)

BANNED_DELIVERABLE_PHRASES = (
    "以下是完整",
    "可直接提交",
    "我已帮你写好",
    "直接复制",
    "一键提交",
)
LLM_SYSTEM_PROMPT = (
    "You are the generation component inside a constrained entrepreneurship learning tutor AI agent. "
    "Return JSON only. Answer in concise Chinese. "
    "Do not ghostwrite ready-to-submit essays, BP copy, speeches, or homework. "
    "Keep the content instructional, project-grounded, and action-oriented."
)

ORGANIZER_SYSTEM_PROMPT = (
    "You are the response organizer inside a constrained entrepreneurship learning tutor AI agent. "
    "Answer in concise Chinese. Keep strong relevance to the user's exact question. "
    "Do not inject unrelated concepts. If the question is ambiguous or off-topic, ask for clarification instead of forcing entrepreneurship jargon."
)

GENERAL_STARTUP_KEYWORDS = (
    "创业",
    "项目",
    "商业",
    "市场",
    "用户",
    "客户",
    "竞品",
    "竞赛",
    "路演",
    "bp",
    "mvp",
    "tam",
    "sam",
    "som",
    "ltv",
    "cac",
    "盈利",
    "定价",
    "渠道",
    "访谈",
    "问卷",
    "需求验证",
    "单位经济",
    "价值主张",
)

TOPIC_LIBRARY: list[dict[str, object]] = [
    {
        "topic": "TAM / SAM / SOM",
        "keywords": ("tam", "sam", "som", "市场规模", "市场空间"),
        "answer_summary": "先区分总市场、可服务市场和现阶段可拿下市场，再按同一口径估算，不要把大盘直接写成你能拿到的结果。",
        "mistakes": [
            "把 TAM 直接当成阶段目标。",
            "没有说明统计口径、时间边界和地区边界。",
            "SOM 超过当前团队渠道和资源承载能力。",
        ],
        "practice_task": "写一版 TAM/SAM/SOM 口径表，每个数字都要注明来源和计算过程。",
        "expected_artifact": "一页市场口径表：定义、数值、来源链接、计算公式。",
        "follow_up_question": "你现在最确定的一层市场口径是哪一层，依据是什么？",
    },
    {
        "topic": "MVP",
        "keywords": ("mvp", "最小可行", "原型", "最小原型"),
        "answer_summary": "MVP 的目标不是做完整产品，而是用最小成本验证一个关键假设，比如用户是否真的愿意持续使用或付费。",
        "mistakes": [
            "把 MVP 做成完整版产品。",
            "没有定义成功阈值和观察周期。",
            "一次验证多个假设，最后无法判断结论来自哪里。",
        ],
        "practice_task": "只定义 1 个 MVP 假设、1 个验证动作和 1 个判断阈值。",
        "expected_artifact": "一张 MVP 假设卡：假设、动作、样本量、阈值、复盘时间。",
        "follow_up_question": "你最想先验证的是用户愿不愿意用，还是用户愿不愿意付费？",
    },
    {
        "topic": "需求验证",
        "keywords": ("访谈", "问卷", "试点", "验证", "需求验证", "用户验证"),
        "answer_summary": "需求验证的核心不是收集很多主观好评，而是拿到能支持或推翻假设的真实证据，例如访谈、试点、转化和留存信号。",
        "mistakes": [
            "只记录支持性反馈，不记录反例。",
            "问题设计带引导性，导致答案失真。",
            "只有态度数据，没有行为数据或转化数据。",
        ],
        "practice_task": "补一版验证表：假设、样本、证据、结论、下一步动作。",
        "expected_artifact": "一页验证记录表，至少包含 5 条真实样本。",
        "follow_up_question": "你现在手里最像证据的材料，是访谈、问卷，还是试点行为数据？",
    },
    {
        "topic": "单位经济",
        "keywords": ("ltv", "cac", "单位经济", "留存", "复购", "毛利"),
        "answer_summary": "单位经济要看单个用户在一个完整周期内能贡献多少价值，以及为了获得这个用户付出了多少成本，LTV/CAC 只是其中一个结果表达。",
        "mistakes": [
            "把一次性收入当成长期价值。",
            "CAC 只算广告费，不算销售和运营投入。",
            "没有把留存和复购放进 LTV 假设里。",
        ],
        "practice_task": "拆一版 LTV/CAC 测算表，把收入、成本、留存假设分开写。",
        "expected_artifact": "一页单位经济测算表：收入项、成本项、假设来源、敏感性区间。",
        "follow_up_question": "你现在最不确定的是收入假设、成本口径，还是留存假设？",
    },
    {
        "topic": "获客与转化",
        "keywords": ("渠道", "获客", "转化", "漏斗", "拉新"),
        "answer_summary": "不要只写渠道名称，要写清楚从曝光到转化的路径、每一步指标以及为什么这个渠道适合你的目标用户。",
        "mistakes": [
            "只有渠道名，没有转化路径。",
            "目标用户和渠道场景不匹配。",
            "没有最小预算和试投验证方案。",
        ],
        "practice_task": "画一条最小获客漏斗：触达、点击、咨询、成交或报名。",
        "expected_artifact": "一页渠道漏斗表：阶段、指标、预算、负责人、复盘时间。",
        "follow_up_question": "你当前最想优先验证的，是哪个渠道的第一轮转化效率？",
    },
    {
        "topic": "竞争优势",
        "keywords": ("竞品", "差异化", "壁垒", "护城河", "竞争"),
        "answer_summary": "差异化不能只写“更好”，要写清楚你和替代方案相比具体在哪个环节更快、更准、更便宜，或者更容易被组织采纳。",
        "mistakes": [
            "只写自己有什么，不写竞品怎么做。",
            "把功能差异误当成竞争壁垒。",
            "没有给出可验证的对比维度。",
        ],
        "practice_task": "做一张 3 列竞品对比表：你、替代方案、关键差异。",
        "expected_artifact": "一页竞品对比表：对象、差异点、证据、风险。",
        "follow_up_question": "你最希望评委先记住你的哪一个差异点？",
    },
    {
        "topic": "路演表达",
        "keywords": ("路演", "答辩", "评分", "评委", "演讲"),
        "answer_summary": "路演表达的重点不是信息越多越好，而是让评委在有限时间内听清问题、方案、证据和下一步计划。",
        "mistakes": [
            "先讲功能细节，后讲用户问题。",
            "没有证据链，导致结论像口号。",
            "一页塞太多文字，评委抓不到主线。",
        ],
        "practice_task": "用 3 页重新组织你的主线：问题、证据、下一步。",
        "expected_artifact": "一版 3 页核心路演结构草图。",
        "follow_up_question": "如果只允许你保留 3 张页，你最想留下哪 3 张？",
    },
]

DEFAULT_TOPIC = {
    "topic": "创业学习辅导",
    "answer_summary": "先把抽象概念落到你的项目动作里：明确对象、证据、指标和时间边界，再决定下一步。",
    "mistakes": [
        "只背概念定义，不连接项目场景。",
        "只写结论，不给证据来源。",
        "一次安排太多任务，导致执行失败。",
    ],
    "practice_task": "先完成一页“问题-证据-指标”单页。",
    "expected_artifact": "一页表格：问题、目标用户、证据来源、验证指标、截止时间。",
    "follow_up_question": "你现在最需要补的是概念理解、证据、还是执行计划？",
}


class LearningConstraintValidator:
    def validate(self, output: LearningTutorOutput) -> LearningConstraintReport:
        violations: list[LearningConstraintViolation] = []
        if not output.topic.strip():
            violations.append(self._violation("field.missing_topic", "topic 不能为空。"))
        if not output.answer_summary.strip():
            violations.append(self._violation("field.missing_summary", "answer_summary 不能为空。"))
        if not output.practice_task.strip():
            violations.append(self._violation("field.missing_task", "practice_task 不能为空。"))
        if not output.expected_artifact.strip():
            violations.append(self._violation("field.missing_artifact", "expected_artifact 不能为空。"))
        if not output.follow_up_question.strip():
            violations.append(self._violation("field.missing_follow_up", "follow_up_question 不能为空。"))

        if output.mode == LearningMode.TUTOR and len(output.common_mistakes) < 2:
            violations.append(self._violation("tutor.missing_mistakes", "tutor 模式至少需要 2 条 common_mistakes。"))

        combined = "\n".join(
            [
                output.answer_summary,
                output.project_grounding,
                output.practice_task,
                output.expected_artifact,
                output.follow_up_question,
            ]
        )
        if output.mode in {LearningMode.ANTI_GHOSTWRITING, LearningMode.EMOTIONAL_REDIRECT}:
            if "代写" not in combined and "一步一步" not in combined and "最小步" not in combined:
                violations.append(
                    self._violation(
                        "safety.missing_redirect",
                        "安全模式输出必须明确拒绝直接代写或引导用户回到最小任务。",
                    )
                )

        for phrase in BANNED_DELIVERABLE_PHRASES:
            if phrase in combined:
                violations.append(
                    self._violation(
                        "safety.direct_deliverable",
                        f"输出包含违规短语: {phrase}。",
                    )
                )
                break

        return LearningConstraintReport(passed=not violations, violations=violations)

    @staticmethod
    def _violation(code: str, message: str) -> LearningConstraintViolation:
        return LearningConstraintViolation(code=code, message=message)


class LearningResponseOrganizerAgent:
    def __init__(self, llm_client: DeepSeekClient | None = None) -> None:
        self.llm_client = llm_client

    def organize(
        self,
        *,
        question: str,
        output: LearningTutorOutput,
        context_used: bool,
    ) -> str:
        if output.mode == LearningMode.ANTI_GHOSTWRITING:
            return (
                f"先说明一下：{output.answer_summary}\n\n"
                f"先把任务缩小：{output.practice_task}\n"
                f"本轮只产出：{output.expected_artifact}\n"
                f"我先追问你一个关键问题：{output.follow_up_question}"
            )

        if output.mode == LearningMode.EMOTIONAL_REDIRECT:
            return (
                f"先别着急，当前最重要的是把问题缩到能动手的一步。\n\n"
                f"直接建议：{output.answer_summary}\n"
                f"现在先做：{output.practice_task}\n"
                f"本轮产出：{output.expected_artifact}\n"
                f"下一问：{output.follow_up_question}"
            )

        if output.mode == LearningMode.CLARIFICATION:
            return (
                f"我先不硬答，因为你这句“{question.strip()}”上下文还不够。\n\n"
                f"{output.answer_summary}\n"
                f"请先补一句：{output.practice_task}\n"
                f"最好补成：{output.expected_artifact}\n"
                f"我先确认一下：{output.follow_up_question}"
            )

        mistakes = "\n".join(f"- {item}" for item in output.common_mistakes[:3])
        grounding_lines: list[str] = []
        if context_used and output.project_grounding.strip():
            grounding_lines.append(f"结合当前项目：{output.project_grounding}")

        return (
            f"先直接回答你的问题：{output.answer_summary}\n\n"
            + ("\n\n".join(grounding_lines) + "\n\n" if grounding_lines else "")
            + f"常见误区：\n{mistakes}\n\n"
            + f"你现在可以先做：{output.practice_task}\n"
            + f"本轮产出：{output.expected_artifact}\n"
            + f"如果你愿意，我下一步继续帮你拆：{output.follow_up_question}"
        )


class LearningTutorAgent:
    def __init__(
        self,
        llm_client: DeepSeekClient | None = None,
        archive_dir: Path | str = Path("outputs/projects"),
        validator: LearningConstraintValidator | None = None,
        organizer: LearningResponseOrganizerAgent | None = None,
        runtime_logger: RuntimeLogger | None = None,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.archive_dir = Path(archive_dir)
        self.validator = validator or LearningConstraintValidator()
        self.organizer = organizer or LearningResponseOrganizerAgent(self.llm_client)
        self.runtime_logger = runtime_logger or RuntimeLogger()

    def respond(
        self,
        question: str,
        *,
        user_id: str | None = None,
        project_id: str | None = None,
        include_project_context: bool = True,
    ) -> LearningTutorResponse:
        run_id = new_run_id("learning-tutor")
        started_at = perf_counter()
        cleaned_question = question.strip()
        plan = self._plan_question(cleaned_question)
        context = None
        context_project_id = None
        self.runtime_logger.log(
            "learning_tutor_agent",
            "request_started",
            run_id=run_id,
            user_id=user_id,
            requested_project_id=project_id,
            include_project_context=include_project_context,
            question_preview=preview_text(cleaned_question),
            plan=plan,
        )
        if include_project_context and bool(plan["use_project_context"]):
            context, context_project_id = self._load_project_context(project_id=project_id, user_id=user_id)
        self.runtime_logger.log(
            "learning_tutor_agent",
            "project_context_resolved",
            run_id=run_id,
            context_used=context is not None,
            context_project_id=context_project_id,
        )

        retrieved_nodes = retrieve_kg_nodes(cleaned_question, load_kg_nodes(), top_k=6) if bool(plan["retrieve_kg"]) else []
        self.runtime_logger.log(
            "learning_tutor_agent",
            "knowledge_retrieval_completed",
            run_id=run_id,
            retrieved_node_count=len(retrieved_nodes),
            retrieved_node_names=[str(node.get("name", "unknown")) for node in retrieved_nodes[:4]],
        )
        fallback_output = self._build_output(cleaned_question, context, context_project_id, retrieved_nodes, plan)
        output = fallback_output
        used_llm = False
        model_name = "learning-tutor-agent"

        if fallback_output.mode == LearningMode.TUTOR and self.llm_client.available and bool(plan["allow_llm"]):
            generated = self._generate_tutor_output_with_llm(
                question=cleaned_question,
                context=context,
                context_project_id=context_project_id,
                retrieved_nodes=retrieved_nodes,
                fallback_output=fallback_output,
                run_id=run_id,
            )
            if generated is not None:
                output = generated
                used_llm = True
                model_name = self.llm_client.default_model
                self.runtime_logger.log(
                    "learning_tutor_agent",
                    "llm_generation_completed",
                    run_id=run_id,
                    model=model_name,
                    mode=output.mode,
                )

        report = self.validator.validate(output)
        if not report.passed and output.mode == LearningMode.TUTOR and self.llm_client.available:
            self.runtime_logger.log(
                "learning_tutor_agent",
                "validation_failed",
                run_id=run_id,
                violation_count=len(report.violations),
                violations=report.violations,
            )
            rewritten = self._rewrite_tutor_output_with_llm(
                question=cleaned_question,
                context=context,
                current_output=output,
                violations=report.violations,
                retrieved_nodes=retrieved_nodes,
                fallback_output=fallback_output,
                run_id=run_id,
            )
            if rewritten is not None:
                output = rewritten
                used_llm = True
                model_name = self.llm_client.default_model
                report = self.validator.validate(output)
                self.runtime_logger.log(
                    "learning_tutor_agent",
                    "llm_rewrite_completed",
                    run_id=run_id,
                    model=model_name,
                    validation_passed=report.passed,
                    violation_count=len(report.violations),
                )

        if not report.passed:
            output = self._repair_output(output, cleaned_question, context, retrieved_nodes)
            report = self.validator.validate(output)
            self.runtime_logger.log(
                "learning_tutor_agent",
                "output_repaired",
                run_id=run_id,
                validation_passed=report.passed,
                violation_count=len(report.violations),
            )

        reply = self.organizer.organize(
            question=cleaned_question,
            output=output,
            context_used=context is not None and output.mode == LearningMode.TUTOR,
        )
        self.runtime_logger.log(
            "learning_tutor_agent",
            "request_completed",
            run_id=run_id,
            used_llm=used_llm,
            model=model_name,
            context_used=context is not None,
            context_project_id=context_project_id,
            mode=output.mode,
            validation_passed=report.passed,
            violation_count=len(report.violations),
            reply_preview=preview_text(reply),
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
        )
        return LearningTutorResponse(
            reply=reply,
            structured_output=output,
            validation=report,
            model=model_name,
            used_llm=used_llm,
            context_used=context is not None,
            context_project_id=context_project_id,
        )

    def _build_output(
        self,
        question: str,
        context: dict | None,
        context_project_id: str | None,
        retrieved_nodes: list[dict],
        plan: dict[str, Any],
    ) -> LearningTutorOutput:
        normalized = question.lower()
        kg_names = [str(node.get("name", "unknown")) for node in retrieved_nodes[:4]]
        if self._contains_any(normalized, GHOSTWRITING_MARKERS):
            return LearningTutorOutput(
                mode=LearningMode.ANTI_GHOSTWRITING,
                topic="反代写引导",
                answer_summary="我不会直接代写可提交文本，但可以把任务拆成最小可执行步骤，帮助你自己完成。",
                project_grounding=self._build_project_grounding(context, fallback="先回到你的项目问题、证据和目标用户，再决定具体写哪一页。"),
                common_mistakes=[
                    "上来就索要完整成稿。",
                    "没有先定义这轮要解决的单一问题。",
                ],
                practice_task="先回答三个问题：你要交什么、最缺哪块、这轮只产出什么最小成果。",
                expected_artifact="一个最小产出定义，而不是完整可提交成稿。",
                follow_up_question="这轮你只想先完成哪一个最小成果：一页口径表、访谈提纲，还是一页问题定义？",
                retrieved_kg_nodes=kg_names,
                context_project_id=context_project_id,
            )

        if self._contains_any(question, EMOTIONAL_MARKERS):
            return LearningTutorOutput(
                mode=LearningMode.EMOTIONAL_REDIRECT,
                topic="情绪减压与最小步推进",
                answer_summary="先不要追求完整版本。我们把任务缩到一个最小动作，先做出可继续推进的第一步。",
                project_grounding=self._build_project_grounding(context, fallback="你当前最需要的不是大段成稿，而是先把一个核心判断说清楚。"),
                common_mistakes=[
                    "任务过大，导致迟迟无法开始。",
                    "把当前问题和最终成稿混成一件事。",
                ],
                practice_task="现在只写 3 句话：目标用户是谁、最痛问题是什么、下一周验证哪一个假设。",
                expected_artifact="3 句最小问题定义，而不是完整 BP。",
                follow_up_question="你愿意先把这 3 句话写出来吗？我再继续帮你往下拆。",
                retrieved_kg_nodes=kg_names,
                context_project_id=context_project_id,
            )

        if str(plan.get("intent")) == "clarification":
            focus = self._extract_focus_phrase(question)
            return LearningTutorOutput(
                mode=LearningMode.CLARIFICATION,
                topic="问题澄清",
                answer_summary=f"我现在不能确认“{focus}”具体指什么，所以不适合直接给定义，也不应该擅自把它改写成另一个问题。",
                project_grounding="等你补一句上下文后，我再按你的真实问题回答。",
                common_mistakes=[
                    "只给一个孤立词语，没有上下文。",
                    "默认系统一定知道这个词在你这里指什么。",
                ],
                practice_task="补一句上下文：它是概念、产品名、昵称、人物，还是你项目里的某个字段？",
                expected_artifact=f"例如：我这里说的“{focus}”是____，我想知道它的定义/作用/和项目的关系。",
                follow_up_question=f"你说的“{focus}”具体是哪个场景里的词？",
                retrieved_kg_nodes=kg_names,
                context_project_id=None,
            )

        topic_spec = plan.get("topic_spec") or self._build_question_focused_default_topic(question)
        topic = str(topic_spec["topic"])
        answer_summary = str(topic_spec["answer_summary"])
        practice_task = str(topic_spec["practice_task"])
        expected_artifact = str(topic_spec["expected_artifact"])
        follow_up_question = str(topic_spec["follow_up_question"])
        common_mistakes = [str(item) for item in topic_spec["mistakes"]]

        if context and context.get("next_task"):
            practice_task = f"{practice_task} 优先顺序上，先对齐当前诊断中的下一步：{context['next_task']}。"

        return LearningTutorOutput(
            mode=LearningMode.TUTOR,
            topic=topic,
            answer_summary=answer_summary,
            project_grounding=self._build_project_grounding(
                context,
                fallback="如果你还没做项目诊断，先把问题、用户、方案和证据写成四行最小信息。",
            ),
            common_mistakes=common_mistakes,
            practice_task=practice_task,
            expected_artifact=expected_artifact,
            follow_up_question=follow_up_question,
            retrieved_kg_nodes=kg_names,
            context_project_id=context_project_id,
        )

    def _generate_tutor_output_with_llm(
        self,
        *,
        question: str,
        context: dict | None,
        context_project_id: str | None,
        retrieved_nodes: list[dict],
        fallback_output: LearningTutorOutput,
        run_id: str | None = None,
    ) -> LearningTutorOutput | None:
        kg_names = [str(node.get("name", "unknown")) for node in retrieved_nodes[:6]]
        schema = {
            "mode": "tutor",
            "topic": "string",
            "answer_summary": "string",
            "project_grounding": "string",
            "common_mistakes": ["string", "string", "string"],
            "practice_task": "string",
            "expected_artifact": "string",
            "follow_up_question": "string",
        }
        user_prompt = (
            "你现在是 A1 学习辅导 AI Agent 的生成模块。请基于学生问题、项目上下文和知识节点，"
            "输出一个用于学习辅导的 JSON 对象，不要输出 markdown，不要输出代码块。\n\n"
            "约束：\n"
            "1. mode 必须固定为 tutor。\n"
            "2. 不能直接代写可提交文稿，只能解释概念、指出误区、布置练习、要求最小产出。\n"
            "3. 回答必须优先紧扣学生原问题，不能把无关概念硬塞进回答。\n"
            "4. 只有当项目上下文和学生问题直接相关时，才能引用项目上下文；否则请弱化或省略。\n"
            "5. 如果学生问题本身含义不清，请直接要求澄清，不要擅自把问题改写成 TAM/SAM/CAC 等创业术语。\n"
            "6. common_mistakes 至少 2 条。\n"
            "7. 输出内容简洁、可执行。\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            f"学生问题:\n{question}\n\n"
            f"项目上下文:\n{json.dumps(context or {}, ensure_ascii=False, indent=2)}\n\n"
            f"检索到的知识节点:\n{json.dumps(kg_names, ensure_ascii=False, indent=2)}\n\n"
            f"参考草稿:\n{fallback_output.model_dump_json(indent=2)}"
        )
        self.runtime_logger.log(
            "learning_tutor_agent",
            "llm_generation_started",
            run_id=run_id,
            model=self.llm_client.default_model,
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt=LLM_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_client.default_model,
                temperature=0.2,
            )
        except Exception as exc:
            self.runtime_logger.log_exception(
                "learning_tutor_agent",
                "llm_generation_failed",
                run_id=run_id,
                error=exc,
                model=self.llm_client.default_model,
            )
            return None

        return self._normalize_llm_output(
            payload=data,
            fallback_output=fallback_output,
            context_project_id=context_project_id,
            retrieved_nodes=retrieved_nodes,
        )

    def _rewrite_tutor_output_with_llm(
        self,
        *,
        question: str,
        context: dict | None,
        current_output: LearningTutorOutput,
        violations: list[LearningConstraintViolation],
        retrieved_nodes: list[dict],
        fallback_output: LearningTutorOutput,
        run_id: str | None = None,
    ) -> LearningTutorOutput | None:
        violation_lines = [f"{index}. {item.code}: {item.message}" for index, item in enumerate(violations, start=1)]
        user_prompt = (
            "你刚才生成的 A1 学习辅导 JSON 没有通过 Agent 约束校验，请严格修复后只输出 JSON。\n\n"
            "违反的约束：\n"
            f"{chr(10).join(violation_lines)}\n\n"
            "修复要求：\n"
            "1. 仍然只输出 tutor 模式。\n"
            "2. 不能给出可直接提交的代写内容。\n"
            "3. 必须保留学习辅导结构：解释、误区、练习、产出、追问。\n"
            "4. 必须与项目上下文一致。\n\n"
            f"学生问题:\n{question}\n\n"
            f"项目上下文:\n{json.dumps(context or {}, ensure_ascii=False, indent=2)}\n\n"
            f"当前输出:\n{current_output.model_dump_json(indent=2)}\n\n"
            f"保底草稿:\n{fallback_output.model_dump_json(indent=2)}"
        )
        self.runtime_logger.log(
            "learning_tutor_agent",
            "llm_rewrite_started",
            run_id=run_id,
            model=self.llm_client.default_model,
            violation_count=len(violations),
        )
        try:
            data = self.llm_client.chat_json(
                system_prompt=LLM_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.llm_client.default_model,
                temperature=0.0,
            )
        except Exception as exc:
            self.runtime_logger.log_exception(
                "learning_tutor_agent",
                "llm_rewrite_failed",
                run_id=run_id,
                error=exc,
                model=self.llm_client.default_model,
                violation_count=len(violations),
            )
            return None

        return self._normalize_llm_output(
            payload=data,
            fallback_output=fallback_output,
            context_project_id=current_output.context_project_id,
            retrieved_nodes=retrieved_nodes,
        )

    def _normalize_llm_output(
        self,
        *,
        payload: dict[str, Any],
        fallback_output: LearningTutorOutput,
        context_project_id: str | None,
        retrieved_nodes: list[dict],
    ) -> LearningTutorOutput | None:
        base = fallback_output.model_dump(mode="json")
        merged = {
            **base,
            **{key: value for key, value in payload.items() if key in base},
        }
        merged["mode"] = LearningMode.TUTOR.value
        merged["context_project_id"] = context_project_id
        merged["retrieved_kg_nodes"] = merged.get("retrieved_kg_nodes") or [
            str(node.get("name", "unknown")) for node in retrieved_nodes[:4]
        ]
        try:
            return LearningTutorOutput.model_validate(merged)
        except Exception:
            return None

    def _repair_output(
        self,
        output: LearningTutorOutput,
        question: str,
        context: dict | None,
        retrieved_nodes: list[dict],
    ) -> LearningTutorOutput:
        repaired = output.model_copy(deep=True)
        if not repaired.topic.strip():
            repaired.topic = "创业学习辅导"
        if not repaired.answer_summary.strip():
            repaired.answer_summary = "先把当前学习问题转成一个可执行动作。"
        if not repaired.project_grounding.strip():
            repaired.project_grounding = self._build_project_grounding(
                context,
                fallback="先对齐你的项目阶段，再决定补概念、证据还是动作。",
            )
        if len(repaired.common_mistakes) < 2:
            repaired.common_mistakes = [
                "只记定义，不落到项目。",
                "只写结论，不给证据。",
            ]
        if not repaired.practice_task.strip():
            repaired.practice_task = "先完成一页最小练习，不要一次写完整稿。"
        if not repaired.expected_artifact.strip():
            repaired.expected_artifact = "一页最小可复核的练习产出。"
        if not repaired.follow_up_question.strip():
            repaired.follow_up_question = "你希望我下一步继续帮你拆概念，还是拆动作？"
        if not repaired.retrieved_kg_nodes:
            repaired.retrieved_kg_nodes = [str(node.get("name", "unknown")) for node in retrieved_nodes[:3]]

        combined = "\n".join(
            [
                repaired.answer_summary,
                repaired.project_grounding,
                repaired.practice_task,
                repaired.expected_artifact,
                repaired.follow_up_question,
            ]
        )
        if any(phrase in combined for phrase in BANNED_DELIVERABLE_PHRASES):
            repaired.answer_summary = "我不会直接给你可提交成稿，我会继续把任务拆成可执行步骤。"
            repaired.expected_artifact = "一个最小练习产出，而不是完整提交稿。"
        if repaired.mode in {LearningMode.ANTI_GHOSTWRITING, LearningMode.EMOTIONAL_REDIRECT} and "代写" not in repaired.answer_summary:
            repaired.answer_summary = "我不会直接代写可提交文本，但会继续帮你拆到最小动作。"
        return repaired

    def _render_reply(self, output: LearningTutorOutput) -> str:
        if output.mode == LearningMode.ANTI_GHOSTWRITING:
            return (
                f"当前模式：{output.topic}\n\n"
                f"{output.answer_summary}\n\n"
                f"结合当前项目：{output.project_grounding}\n\n"
                f"先做这一步：{output.practice_task}\n"
                f"本轮产出：{output.expected_artifact}\n"
                f"继续追问：{output.follow_up_question}"
            )
        if output.mode == LearningMode.EMOTIONAL_REDIRECT:
            return (
                f"当前模式：{output.topic}\n\n"
                f"{output.answer_summary}\n\n"
                f"结合当前项目：{output.project_grounding}\n\n"
                f"最小动作：{output.practice_task}\n"
                f"本轮产出：{output.expected_artifact}\n"
                f"继续追问：{output.follow_up_question}"
            )
        mistakes = "\n".join(f"- {item}" for item in output.common_mistakes[:3])
        kg_text = "、".join(output.retrieved_kg_nodes[:4]) if output.retrieved_kg_nodes else "无"
        return (
            f"主题：{output.topic}\n\n"
            f"解释：{output.answer_summary}\n\n"
            f"结合当前项目：{output.project_grounding}\n\n"
            f"常见误区：\n{mistakes}\n\n"
            f"练习任务：{output.practice_task}\n\n"
            f"期望产出：{output.expected_artifact}\n\n"
            f"下一问：{output.follow_up_question}\n\n"
            f"参考知识节点：{kg_text}"
        )

    @staticmethod
    def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
        return any(marker in text for marker in markers)

    def _plan_question(self, question: str) -> dict[str, Any]:
        normalized = self._normalize_question(question)
        topic_spec = self._match_topic(normalized)
        has_startup_keyword = self._contains_any(normalized, GENERAL_STARTUP_KEYWORDS)
        focus = self._extract_focus_phrase(question)
        is_ambiguous = len(focus) <= 4 or not has_startup_keyword

        if self._contains_any(normalized, GHOSTWRITING_MARKERS) or self._contains_any(question, EMOTIONAL_MARKERS):
            return {
                "intent": "safety",
                "topic_spec": topic_spec,
                "use_project_context": True,
                "retrieve_kg": True,
                "allow_llm": False,
            }

        if topic_spec is not None:
            return {
                "intent": "topic_matched",
                "topic_spec": topic_spec,
                "use_project_context": True,
                "retrieve_kg": True,
                "allow_llm": True,
            }

        if is_ambiguous:
            return {
                "intent": "clarification",
                "topic_spec": None,
                "use_project_context": False,
                "retrieve_kg": False,
                "allow_llm": False,
            }

        return {
            "intent": "question_focused_tutor",
            "topic_spec": None,
            "use_project_context": has_startup_keyword,
            "retrieve_kg": has_startup_keyword,
            "allow_llm": has_startup_keyword,
        }

    def _match_topic(self, normalized_question: str) -> dict[str, object] | None:
        for item in TOPIC_LIBRARY:
            keywords = item.get("keywords", ())
            if any(keyword in normalized_question for keyword in keywords):
                return item
        return None

    @staticmethod
    def _normalize_question(question: str) -> str:
        return (
            question.lower()
            .replace("？", " ")
            .replace("?", " ")
            .replace("。", " ")
            .replace("，", " ")
            .replace(",", " ")
            .replace("：", " ")
            .replace(":", " ")
            .strip()
        )

    def _extract_focus_phrase(self, question: str) -> str:
        focus = question.strip()
        for prefix in ("什么是", "请问", "想问", "我想问", "帮我解释一下", "解释一下", "能讲讲", "能解释下"):
            if focus.startswith(prefix):
                focus = focus[len(prefix):].strip()
                break
        focus = focus.strip("？?。！!：:，,；; ")
        return focus or question.strip()

    def _build_question_focused_default_topic(self, question: str) -> dict[str, object]:
        focus = self._extract_focus_phrase(question)
        return {
            "topic": f"围绕“{focus}”的学习澄清",
            "answer_summary": f"我会先围绕“{focus}”本身回答，不额外跳到 TAM、CAC 或别的概念；只有当它们和你的问题直接相关时才会提到。",
            "mistakes": [
                "问题太短，导致概念边界不清楚。",
                "一句话里混了多个目标，不知道是在问定义、用途还是写法。",
                "还没确认术语指代，就直接往项目分析上套。",
            ],
            "practice_task": f"把你的问题补成一句完整话：你想知道“{focus}”的定义、作用，还是它在项目里的具体写法？",
            "expected_artifact": f"一句澄清后的问题，例如：{focus} 在我的项目里是什么意思？或者：{focus} 应该怎么写进 BP？",
            "follow_up_question": f"你现在最想让我先回答“{focus}”的哪一部分：定义、作用，还是项目用法？",
        }

    @staticmethod
    def _build_project_grounding(context: dict | None, fallback: str) -> str:
        if not context:
            return fallback

        project_name = context.get("project_name") or "当前项目"
        diagnosis = context.get("current_diagnosis") or "暂无诊断"
        next_task = context.get("next_task") or "暂无下一步"
        top_rules = context.get("top_non_pass_rules") or "暂无非通过规则"
        return (
            f"结合 {project_name} 的最近诊断，当前关注点是“{diagnosis}”。"
            f" 你在学习这个概念时，优先要服务于下一步任务“{next_task}”，"
            f" 并避开这些风险提示：{top_rules}。"
        )

    def _load_project_context(self, project_id: str | None, user_id: str | None) -> tuple[dict | None, str | None]:
        if not self.archive_dir.exists():
            return None, None

        payload: dict | None = None
        used_project_id: str | None = None
        if project_id:
            archive_file = self.archive_dir / f"{project_id.removesuffix('.json')}.json"
            if archive_file.exists():
                payload = self._read_json(archive_file)
                used_project_id = project_id.removesuffix(".json")

        if payload is None and user_id:
            candidates = sorted(self.archive_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
            for candidate in candidates:
                data = self._read_json(candidate)
                request = data.get("request") if isinstance(data, dict) else None
                if isinstance(request, dict) and request.get("user_id") == user_id:
                    payload = data
                    used_project_id = request.get("project_id") or candidate.stem
                    break

        if not payload:
            return None, None

        state = payload.get("state", {}) if isinstance(payload, dict) else {}
        output = payload.get("output", {}) if isinstance(payload, dict) else {}
        top_rules: list[str] = []
        for rule in output.get("detected_rules", []):
            if isinstance(rule, dict) and rule.get("status") != "pass":
                top_rules.append(f"{rule.get('rule_id')}:{rule.get('status')}")
            if len(top_rules) >= 3:
                break

        context = {
            "project_name": state.get("project_name"),
            "problem": state.get("problem"),
            "customer_segment": state.get("customer_segment"),
            "current_diagnosis": output.get("current_diagnosis"),
            "next_task": output.get("next_task"),
            "top_non_pass_rules": " / ".join(top_rules) if top_rules else "暂无",
        }
        return context, used_project_id

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
