from __future__ import annotations

import json
from pathlib import Path

from .llm_client import DeepSeekClient
from .models import ChatMessage, ChatResponse


DEFAULT_SYSTEM_PROMPT = (
    "You are a practical startup education assistant. "
    "Give concise, actionable advice in Chinese. "
    "When information is missing, ask one clear follow-up question. "
    "The current system has exactly 20 implemented rules: H1, H2, H4, H5, H8, H9, H10, H11, H12, H13, H14, H15, H16, H17, H18, H19, H20, H21, H22, H23. "
    "If the user asks how many rules exist, how the evaluation dimensions are structured, or asks for a rule-by-rule explanation, "
    "you must answer strictly according to these 20 implemented rules only. "
    "Do not say there are 8 rules, 12 rules, 16 rules, or any other count unless you explicitly state those are not implemented in the current system. "
    "If needed, explain that the current repository has 20 implemented rules in the rule engine."
)


class ConversationAgent:
    def __init__(
        self,
        llm_client: DeepSeekClient | None = None,
        archive_dir: Path | str = Path("outputs/projects"),
    ) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.archive_dir = Path(archive_dir)

    def chat(
        self,
        messages: list[ChatMessage],
        mode: str = "general",
        *,
        user_id: str | None = None,
        include_project_context: bool = False,
        project_id: str | None = None,
    ) -> ChatResponse:
        cleaned = [msg for msg in messages if msg.content.strip()]
        context_text: str | None = None
        context_project_id: str | None = None
        if include_project_context:
            context_text, context_project_id = self._load_project_context(project_id=project_id, user_id=user_id)

        if not cleaned:
            return ChatResponse(
                reply="请先输入你的问题或项目背景，我再给你可执行建议。",
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        if not self.llm_client.available:
            return ChatResponse(
                reply=self._fallback_reply(cleaned, context_text=context_text),
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        model = self.llm_client.reasoner_model if mode == "reasoning" else self.llm_client.default_model
        system_prompt = DEFAULT_SYSTEM_PROMPT
        if context_text:
            system_prompt = (
                f"{DEFAULT_SYSTEM_PROMPT}\n\n"
                "You are provided with project context from a previous diagnostic run. "
                "Use it as grounding evidence and keep answers consistent with it.\n"
                f"PROJECT_CONTEXT:\n{context_text}"
            )
        user_prompt = self._to_prompt(cleaned)

        try:
            reply = self.llm_client.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=0.2,
            ).strip()
        except Exception:
            return ChatResponse(
                reply=self._fallback_reply(cleaned, context_text=context_text, reason="timeout"),
                model="offline-fallback",
                used_llm=False,
                context_used=bool(context_text),
                context_project_id=context_project_id,
            )

        if not reply:
            reply = "我没有生成有效回答。请重试，或补充你的具体目标与当前约束。"
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
