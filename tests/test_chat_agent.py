import json
from pathlib import Path

from core.chat_agent import ConversationAgent
from core.models import ChatMessage


class DummyOfflineClient:
    available = False
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"


class DummyOnlineClient:
    available = True
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"
    last_system_prompt = ""

    def chat_text(self, *, system_prompt: str, user_prompt: str, model: str, temperature: float) -> str:  # noqa: ARG002
        self.last_system_prompt = system_prompt
        return f"mock-response-{model}"


def test_conversation_agent_fallback_without_llm():
    agent = ConversationAgent(llm_client=DummyOfflineClient())
    resp = agent.chat([ChatMessage(role="user", content="你好")], mode="general")
    assert resp.used_llm is False
    assert resp.model == "offline-fallback"


def test_conversation_agent_uses_reasoner_model():
    llm = DummyOnlineClient()
    agent = ConversationAgent(llm_client=llm)
    resp = agent.chat([ChatMessage(role="user", content="帮我分析规则冲突")], mode="reasoning")
    assert resp.used_llm is True
    assert resp.model == "deepseek-reasoner"
    assert "mock-response-deepseek-reasoner" in resp.reply


def test_conversation_agent_loads_context_by_project_id(tmp_path: Path):
    archive = tmp_path / "p1.json"
    archive.write_text(
        json.dumps(
            {
                "request": {"user_id": "u1", "project_id": "p1"},
                "state": {"project_name": "护苗AI", "problem": "校园心理筛查"},
                "output": {"current_diagnosis": "H8 fail", "next_task": "重算LTV/CAC", "detected_rules": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    llm = DummyOnlineClient()
    agent = ConversationAgent(llm_client=llm, archive_dir=tmp_path)
    resp = agent.chat(
        [ChatMessage(role="user", content="下一步做什么")],
        include_project_context=True,
        project_id="p1",
    )
    assert resp.context_used is True
    assert resp.context_project_id == "p1"
    assert "PROJECT_CONTEXT" in llm.last_system_prompt
    assert "project_name=护苗AI" in llm.last_system_prompt


def test_conversation_agent_auto_picks_latest_context_by_user_id(tmp_path: Path):
    older = tmp_path / "old.json"
    newer = tmp_path / "new.json"
    older.write_text(
        json.dumps(
            {
                "request": {"user_id": "u1", "project_id": "old"},
                "state": {"project_name": "旧项目"},
                "output": {"current_diagnosis": "old", "next_task": "old", "detected_rules": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    newer.write_text(
        json.dumps(
            {
                "request": {"user_id": "u1", "project_id": "new"},
                "state": {"project_name": "新项目"},
                "output": {"current_diagnosis": "new", "next_task": "new", "detected_rules": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # Ensure mtime ordering for deterministic selection.
    newer.touch()

    llm = DummyOnlineClient()
    agent = ConversationAgent(llm_client=llm, archive_dir=tmp_path)
    resp = agent.chat(
        [ChatMessage(role="user", content="结合我最近项目给建议")],
        include_project_context=True,
        user_id="u1",
    )
    assert resp.context_used is True
    assert resp.context_project_id == "new"
