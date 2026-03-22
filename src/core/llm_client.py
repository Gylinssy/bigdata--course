from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .env_utils import load_env_file

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
load_env_file()


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
        reasoner_model: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.default_model = default_model or os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat")
        self.reasoner_model = reasoner_model or os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner")
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url) if OpenAI and self.api_key else None

    @property
    def available(self) -> bool:
        return self._client is not None

    def chat_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> str:
        if not self._client:
            raise RuntimeError("DeepSeek API key not configured.")
        response = self._client.chat.completions.create(
            model=model or self.default_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.0,
        max_attempts: int = 2,
    ) -> dict[str, Any]:
        prompt = user_prompt
        last_error: Exception | None = None
        for _ in range(max_attempts):
            text = self.chat_text(
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=model,
                temperature=temperature,
            )
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = exc
                prompt = (
                    f"{user_prompt}\n\n"
                    "Return JSON only. Do not wrap in markdown fences or add explanations."
                )
        raise ValueError(f"Failed to parse DeepSeek JSON response: {last_error}") from last_error


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()
