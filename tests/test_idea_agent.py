from core.extractor import ProjectExtractor
from core.idea_agent import IdeaCoachAgent
class FakeIdeaLLM:
    default_model = "fake-idea-model"
    available = True

    def chat_json(self, **_: object) -> dict[str, str]:
        return {
            "reply": "我先卡在 H2 这条超图约束：问题和方案的对应关系还不够清楚。\n\n请先按这个格式回答：\n- 问题：\n- 价值主张：\n\n苏格拉底式追问：如果你这周只能先验证一个用户场景，你准备找谁、怎么触达？\n\n这一轮的最小推进目标：先补一句目标用户和一个最真实的使用场景。",
            "socratic_question": "如果你这周只能先验证一个用户场景，你准备找谁、怎么触达？",
            "next_action": "先补一句目标用户和一个最真实的使用场景。",
        }


class NoIdeaLLM:
    default_model = "disabled-idea-model"
    available = False


def build_deterministic_agent() -> IdeaCoachAgent:
    return IdeaCoachAgent(
        llm_client=NoIdeaLLM(),  # type: ignore[arg-type]
        extractor=ProjectExtractor(enable_llm=False),
    )


def test_idea_agent_bootstrap_starts_with_rule_bound_question():
    agent = build_deterministic_agent()

    response = agent.bootstrap("")

    assert response.structured_output.focus_rule_id == "H2"
    assert "超图约束" in response.reply
    assert "问题：" in response.structured_output.answer_template
    assert "价值主张：" in response.structured_output.answer_template
    assert response.used_llm is False


def test_idea_agent_can_collect_fields_and_build_diagnosis_ready_draft():
    agent = build_deterministic_agent()

    bootstrap = agent.bootstrap("我想做一个帮助职业资格备考人群提升复习效率的工具。")
    step1 = agent.step(
        bootstrap.workspace,
        "问题：职业资格备考资料分散，复习效率低。\n价值主张：针对资料分散和复习效率低的问题，用 AI 自动整理资料并生成复习卡片。",
    )
    assert step1.structured_output.focus_rule_id == "H1"

    step2 = agent.step(
        step1.workspace,
        "客户：职业资格备考人群。\n渠道：B站备考区和垂直备考社群。",
    )
    assert "客户：职业资格备考人群" in step2.structured_output.generated_project_text
    assert "渠道：B站备考区和垂直备考社群" in step2.structured_output.generated_project_text

    step3 = agent.step(
        step2.workspace,
        "收入模式：会员订阅 19 元/月。\n验证证据：已访谈 12 名备考用户，其中 8 人愿意试用。\n执行计划：第 1 周完成 MVP，负责人是产品同学；第 4 周完成 50 人内测。",
    )

    assert step3.structured_output.ready_for_generation is True
    assert step3.structured_output.ready_for_diagnosis is True
    assert "收入模式：会员订阅 19 元/月" in step3.structured_output.generated_project_text
    assert "验证证据：已访谈 12 名备考用户，其中 8 人愿意试用" in step3.structured_output.generated_project_text
    assert step3.used_llm is False


def test_idea_agent_prioritizes_compliance_when_sensitive_seed_is_detected():
    agent = build_deterministic_agent()

    response = agent.bootstrap("我想做一个给未成年人提供心理诊断建议的产品。")

    assert response.structured_output.focus_rule_id == "H11"
    assert "合规" in response.reply
    assert "合规说明：" in response.structured_output.answer_template


def test_idea_agent_marks_llm_guidance_when_client_available():
    agent = IdeaCoachAgent(
        llm_client=FakeIdeaLLM(),  # type: ignore[arg-type]
        extractor=ProjectExtractor(enable_llm=False),
    )

    response = agent.bootstrap("我想做一个帮助考研学生自动整理资料的工具。")

    assert response.used_llm is True
    assert response.model == "fake-idea-model"
    assert "我先卡在 H2 这条超图约束" in response.reply
    assert "如果你这周只能先验证一个用户场景" in response.reply
    assert response.structured_output.next_action == "先补一句目标用户和一个最真实的使用场景。"
