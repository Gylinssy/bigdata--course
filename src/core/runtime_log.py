from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

from .env_utils import ROOT_DIR


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def preview_text(text: str | None, limit: int = 160) -> str | None:
    if text is None:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


class RuntimeLogger:
    _write_lock = Lock()

    def __init__(
        self,
        log_dir: Path | str | None = None,
        *,
        file_name: str = "agent_runtime.jsonl",
    ) -> None:
        self.log_dir = Path(log_dir) if log_dir else ROOT_DIR / "outputs" / "logs"
        self.log_path = self.log_dir / file_name

    def log(
        self,
        agent_name: str,
        event: str,
        *,
        run_id: str | None = None,
        level: str = "INFO",
        **details: Any,
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_name": agent_name,
            "event": event,
            "level": level,
            "run_id": run_id,
            "details": self._coerce(details),
        }
        self._append(payload)

    def log_exception(
        self,
        agent_name: str,
        event: str,
        *,
        error: Exception,
        run_id: str | None = None,
        **details: Any,
    ) -> None:
        error_payload = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        }
        self.log(
            agent_name,
            event,
            run_id=run_id,
            level="ERROR",
            error=error_payload,
            **details,
        )

    def read_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0 or not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    def _append(self, payload: dict[str, Any]) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with self._write_lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    @classmethod
    def _coerce(cls, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return cls._coerce(value.model_dump(mode="json"))
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {str(key): cls._coerce(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._coerce(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return repr(value)
