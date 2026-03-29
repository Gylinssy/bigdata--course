from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter

from .llm_client import DeepSeekClient
from .models import ChatMessage, ChatResponse
from .runtime_log import RuntimeLogger, new_run_id, preview_text


DEFAULT_SYSTEM_PROMPT = (
    "You are a practical startup education assistant. "
    "Give concise, actionable advice in Chinese. "
    "Answer the user's latest question directly. "
    "Use project context only when it is relevant to that question. "
    "When information is missing, ask one clear follow-up question."
)

RULE_REFERENCE_PROMPT = (
    "The current system has exactly 20 implemented rules: "
    "H1, H2, H4, H5, H8, H9, H10, H11, H12, H13, H14, H15, H16, H17, H18, H19, H20, H21, H22, H23. "
    "Only use this rule list when the user explicitly asks how many rules exist, how the evaluation dimensions are structured, "
    "or asks for a rule-by-rule explanation. "
    "Do not volunteer the rule count or rule list in unrelated conversations."
)

RULE_QUERY_MARKERS = (
    "how many rules",
    "implemented rules",
    "rule-by-rule",
    "rule by rule",
    "evaluation dimensions",
    "规则",
    "维度",
)


class ConversationAgent:
    def __init__(
        self,
        llm_client: DeepSeekClient | None = None,
        archive_dir: Path | str = Path("outputs/projects"),
        runtime_logger: RuntimeLogger | None = None,
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.archive_dir = Path(archive_dir)
        self.runtime_logger = runtime_logger or RuntimeLogger()

    def chat(
        self,
        messages: list[ChatMessage],
        mode: str = "general",
        *,
        user_id: str | None = None,
        include_project_context: bool = False,
        project_id: str | None = None,
    ) -> ChatResponse:
        run_id = new_run_id("conversation")
        started_at = perf_counter()
        cleaned = [msg for msg in messages if msg.content.strip()]
        system_notes = [msg.content.strip() for msg in cleaned if msg.role == "system"]
        dialogue = [msg for msg in cleaned if msg.role != "system"]
        last_user_message = next((msg.content for msg in reversed(dialogue) if msg.role == "user"), None)
        context_text: str | None = None
        context_project_id: str | None = None
        self.runtime_logger.log(
            "conversation_agent",
            "request_started",
            run_id=run_id,
            mode=mode,
            user_id=user_id,
            include_project_context=include_project_context,
            requested_project_id=project_id,
            message_count=len(dialogue),
            last_user_message=preview_text(last_user_message),
        )
        if include_project_context:
            context_text, context_project_id = self._load_project_context(project_id=project_id, user_id=user_id)
            self.runtime_logger.log(
                "conversation_agent",
                "project_context_resolved",
                run_id=run_id,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        if not dialogue:
            self.runtime_logger.log(
                "conversation_agent",
                "request_completed",
                run_id=run_id,
                used_llm=False,
                model="offline-fallback",
                context_used=bool(context_text),
                context_project_id=context_project_id,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                outcome="empty_dialogue",
            )
            return ChatResponse(
                reply="请先输入你的问题或项目背景，我再给你可执行建议。",
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        if not self.llm_client.available:
            self.runtime_logger.log(
                "conversation_agent",
                "fallback_used",
                run_id=run_id,
                reason="llm_unavailable",
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )
            self.runtime_logger.log(
                "conversation_agent",
                "request_completed",
                run_id=run_id,
                used_llm=False,
                model="offline-fallback",
                context_used=bool(context_text),
                context_project_id=context_project_id,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                outcome="offline_fallback",
            )
            return ChatResponse(
                reply=self._fallback_reply(dialogue, context_text=context_text),
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        model = self.llm_client.reasoner_model if mode == "reasoning" else self.llm_client.default_model
        system_prompt = self._build_system_prompt(
            dialogue,
            context_text=context_text,
            system_notes=system_notes,
        )
        user_prompt = self._to_prompt(dialogue)
        self.runtime_logger.log(
            "conversation_agent",
            "llm_request_started",
            run_id=run_id,
            model=model,
            context_used=bool(context_text),
            context_project_id=context_project_id,
        )

        try:
            reply = self.llm_client.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=0.2,
            ).strip()
        except Exception as exc:
            self.runtime_logger.log_exception(
                "conversation_agent",
                "llm_request_failed",
                run_id=run_id,
                error=exc,
                model=model,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )
            self.runtime_logger.log(
                "conversation_agent",
                "fallback_used",
                run_id=run_id,
                reason="llm_exception",
                model=model,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )
            self.runtime_logger.log(
                "conversation_agent",
                "request_completed",
                run_id=run_id,
                used_llm=False,
                model="offline-fallback",
                context_used=bool(context_text),
                context_project_id=context_project_id,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
                outcome="timeout_fallback",
            )
            return ChatResponse(
                reply=self._fallback_reply(dialogue, context_text=context_text, reason="timeout"),
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        if not reply:
            reply = "我没有生成有效回答。请重试，或补充你的具体目标与当前约束。"
        self.runtime_logger.log(
            "conversation_agent",
            "llm_request_completed",
            run_id=run_id,
            model=model,
            reply_preview=preview_text(reply),
        )
        self.runtime_logger.log(
            "conversation_agent",
            "request_completed",
            run_id=run_id,
            used_llm=True,
            model=model,
            context_used=bool(context_text),
            context_project_id=context_project_id,
            duration_ms=round((perf_counter() - started_at) * 1000, 2),
            outcome="ok",
        )
        return ChatResponse(
            reply=reply,
            model=model,
            used_llm=True,
            context_used=bool(context_text),
            context_project_id=context_project_id,
        )

    @staticmethod
    def _to_prompt(messages: list[ChatMessage]) -> str:
        lines = []
        for msg in messages:
            role = msg.role.upper()
            lines.append(f"{role}: {msg.content.strip()}")
        return "\n".join(lines) + "\nASSISTANT:"

    @classmethod
    def _build_system_prompt(
        cls,
        messages: list[ChatMessage],
        *,
        context_text: str | None,
        system_notes: list[str],
    ) -> str:
        sections = [DEFAULT_SYSTEM_PROMPT]
        if cls._should_include_rule_reference(messages):
            sections.append(RULE_REFERENCE_PROMPT)
        if system_notes:
            sections.append("ADDITIONAL_SYSTEM_NOTES:\n" + "\n".join(f"- {note}" for note in system_notes))
        if context_text:
            sections.append(
                "You are provided with project context from a previous diagnostic run. "
                "Use it as grounding evidence and keep answers consistent with it.\n"
                f"PROJECT_CONTEXT:\n{context_text}"
            )
        return "\n\n".join(sections)

    @staticmethod
    def _should_include_rule_reference(messages: list[ChatMessage]) -> bool:
        combined = " ".join(msg.content.lower() for msg in messages if msg.role == "user")
        return any(marker in combined for marker in RULE_QUERY_MARKERS)

    @staticmethod
    def _fallback_reply(
        messages: list[ChatMessage],
        *,
        context_text: str | None = None,
        reason: str = "missing_key",
    ) -> str:
        last_user = next((msg.content for msg in reversed(messages) if msg.role == "user"), None)
        if not last_user:
            return "我已收到上下文。请直接输入你的问题，我会给出可执行建议。"

        prefix = ""
        if context_text:
            prefix = "已加载项目上下文，但当前切到离线提示模式。\n"

        if reason == "timeout":
            return prefix + (
                "DeepSeek 请求超时，暂时无法返回在线结果。\n"
                "你可以继续补充目标用户、核心痛点、验证假设或关键约束，我会先给出离线建议。"
            )

        return prefix + (
            "当前未检测到可用的 DeepSeek API Key，已切换离线模式。\n"
            "你可以先按这个模板继续：目标用户是谁、当前痛点是什么、你准备先验证哪一项。"
        )

    def _load_project_context(self, project_id: str | None, user_id: str | None) -> tuple[str | None, str | None]:
        if not self.archive_dir.exists():
            return None, None

        payload: dict | None = None
        used_project_id: str | None = None
        if project_id:
            cleaned_project_id = project_id.removesuffix(".json")
            archive_file = self.archive_dir / f"{cleaned_project_id}.json"
            if archive_file.exists():
                payload = self._read_json(archive_file)
                used_project_id = cleaned_project_id

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
        top_rules = []
        for rule in output.get("detected_rules", []):
            if isinstance(rule, dict) and rule.get("status") != "pass":
                top_rules.append(f"{rule.get('rule_id')}: {rule.get('status')} - {rule.get('message')}")
            if len(top_rules) >= 3:
                break

        context_lines = [
            f"project_id={used_project_id or 'unknown'}",
            f"project_name={state.get('project_name') or 'N/A'}",
            f"problem={state.get('problem') or 'N/A'}",
            f"customer_segment={state.get('customer_segment') or 'N/A'}",
            f"value_proposition={state.get('value_proposition') or 'N/A'}",
            f"channel={state.get('channel') or 'N/A'}",
            f"current_diagnosis={output.get('current_diagnosis') or 'N/A'}",
            f"next_task={output.get('next_task') or 'N/A'}",
            f"top_non_pass_rules={'; '.join(top_rules) if top_rules else 'N/A'}",
        ]
        return "\n".join(context_lines), used_project_id

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
