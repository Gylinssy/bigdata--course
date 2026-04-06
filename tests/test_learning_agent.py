import json
from pathlib import Path

from core.learning_agent import LearningTutorAgent
from core.models import LearningMode


class DummyClient:
    available = False
    default_model = "deepseek-chat"


class DummyOnlineClient:
    available = True
    default_model = "deepseek-chat"
    last_user_prompt = ""

    def chat_json(self, *, system_prompt: str, user_prompt: str, model: str, temperature: float):  # noqa: ARG002
        self.last_user_prompt = user_prompt
        return {
            "mode": "tutor",
            "topic": "TAM / SAM / SOM",
            "answer_summary": "先统一市场口径，再估算你当前阶段可服务与可拿下的市场。",
            "project_grounding": "先结合当前项目，避免把大盘直接写成阶段目标。",
            "common_mistakes": ["把 TAM 当阶段目标。", "没有交代口径边界。"],
            "practice_task": "写一页 TAM/SAM/SOM 口径表。",
            "expected_artifact": "一页口径表。",
            "follow_up_question": "你最确定的市场层级是哪一层？",
        }


def test_learning_agent_returns_tutor_mode_for_normal_question():
    agent = LearningTutorAgent(llm_client=DummyClient())
    response = agent.respond("什么是 TAM/SAM/SOM，应该如何落到我的项目里？", include_project_context=False)

    assert response.structured_output.mode == LearningMode.TUTOR
    assert response.validation.passed is True
    assert response.structured_output.topic == "TAM / SAM / SOM"
    assert response.structured_output.retrieved_kg_nodes


def test_learning_agent_blocks_ghostwriting_requests():
    agent = LearningTutorAgent(llm_client=DummyClient())
    response = agent.respond("直接帮我写完一篇可直接提交的路演稿", include_project_context=False)

    assert response.structured_output.mode == LearningMode.ANTI_GHOSTWRITING
    assert response.validation.passed is True
    assert "不会直接代写" in response.reply


def test_learning_agent_loads_project_context(tmp_path: Path):
    archive = tmp_path / "p1.json"
    archive.write_text(
        json.dumps(
            {
                "request": {"user_id": "u1", "project_id": "p1"},
                "state": {"project_name": "护苗AI", "problem": "校园心理筛查"},
                "output": {
                    "current_diagnosis": "H9: 需求验证证据偏弱",
                    "next_task": "补 10 份访谈",
                    "detected_rules": [{"rule_id": "H9", "status": "warning", "message": "验证证据偏弱"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent = LearningTutorAgent(llm_client=DummyClient(), archive_dir=tmp_path)

    response = agent.respond("什么是用户访谈，应该怎么做？", user_id="u1", include_project_context=True)

    assert response.context_used is True
    assert response.context_project_id == "p1"
    assert "护苗AI" in response.structured_output.project_grounding
    assert response.validation.passed is True


def test_learning_agent_uses_llm_when_available():
    llm = DummyOnlineClient()
    agent = LearningTutorAgent(llm_client=llm)

    response = agent.respond("什么是 TAM/SAM/SOM，应该如何落到我的项目里？", include_project_context=False)

    assert response.used_llm is True
    assert response.model == "deepseek-chat"
    assert response.structured_output.mode == LearningMode.TUTOR
    assert "Schema" in llm.last_user_prompt


def test_learning_agent_asks_for_clarification_on_ambiguous_question():
    agent = LearningTutorAgent(llm_client=DummyClient())

    response = agent.respond("什么是米米", include_project_context=False)

    assert response.structured_output.mode == LearningMode.CLARIFICATION
    assert "TAM" not in response.reply
    assert "米米" in response.reply


def test_learning_agent_uses_general_definition_tone_for_unmatched_project_term():
    agent = LearningTutorAgent(llm_client=DummyClient())

    response = agent.respond("什么是闭环设计，它在我的项目里有什么影响？", include_project_context=False)

    assert response.structured_output.mode == LearningMode.TUTOR
    assert response.structured_output.topic == "围绕“闭环设计”的概念解释"
    assert response.structured_output.answer_summary.startswith("一般来讲，“闭环设计”")
    assert "它和你的项目还没有建立明确关联" in response.reply
    assert "它在你的项目里对应哪个环节" in response.reply


def test_learning_agent_does_not_force_project_context_on_ambiguous_question(tmp_path: Path):
    archive = tmp_path / "p1.json"
    archive.write_text(
        json.dumps(
            {
                "request": {"user_id": "u1", "project_id": "p1"},
                "state": {"project_name": "DroneFarm", "problem": "农村物流"},
                "output": {
                    "current_diagnosis": "渠道与用户错位",
                    "next_task": "补 10 份访谈",
                    "detected_rules": [{"rule_id": "H2", "status": "warning", "message": "渠道错位"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    agent = LearningTutorAgent(llm_client=DummyClient(), archive_dir=tmp_path)

    response = agent.respond("什么是米米", user_id="u1", include_project_context=True)

    assert response.context_used is False
    assert response.structured_output.mode == LearningMode.CLARIFICATION
    assert response.context_project_id is None
    assert "DroneFarm" not in response.reply
