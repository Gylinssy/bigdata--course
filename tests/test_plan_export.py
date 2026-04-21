from io import BytesIO
from zipfile import ZipFile

from core.plan_export import build_word_plan_document


def test_build_word_plan_document_merges_multiple_results() -> None:
    idea_output = {
        "stage_label": "可生成草案",
        "overview": "项目核心信息已经基本齐备，可以生成一版计划书。",
        "focus_rule_id": "H9",
        "next_action": "补充首批试点访谈证据。",
        "generated_project_text": (
            "项目名称：校园健康AI\n"
            "问题：学生压力筛查 & 干预 <试点>\n"
            "客户：学校心理中心"
        ),
        "draft_state": {
            "project_name": "校园健康AI",
            "problem": "学生压力筛查 & 干预 <试点>",
            "customer_segment": "学校心理中心",
            "value_proposition": "用低成本问卷和访谈提前发现高风险学生。",
            "channel": "校内试点和教师推荐",
            "revenue_model": "按校年费订阅",
            "validation_evidence": "已完成 12 份教师访谈。",
            "execution_plan": "先在两所学校跑 4 周 MVP。",
            "competitive_advantage": "更快部署且更适合校园流程。",
            "pilot_plan": "首批 2 所学校，覆盖 200 名学生。",
            "compliance_notes": "仅在校方授权和家长同意下使用数据。",
        },
    }
    diagnosis_payload = {
        "request": {
            "project_id": "p-001",
            "project_text": "项目名称：校园健康AI\n问题：学生压力筛查 & 干预 <试点>",
        },
        "output": {
            "current_diagnosis": "需求验证证据仍偏弱。",
            "impact": "如果不先补足证据，后续试点会建立在错误假设上。",
            "next_task": "补充 10 份目标用户访谈。",
            "markdown_report": "## Current Diagnosis\n需求验证证据仍偏弱。\n\n## Next Task\n补充 10 份目标用户访谈。",
            "evidence_used": [
                {"source": "user_input", "field": "problem", "quote": "问题：学生压力筛查 & 干预 <试点>"},
                {"source": "user_input", "field": "validation_evidence", "quote": "已完成 12 份教师访谈。"},
            ],
            "rubric_scores": [
                {"rubric_id": "R1", "name": "问题定义", "score": 3, "rationale": "问题和用户有基础描述。"},
                {"rubric_id": "R9", "name": "证据支撑", "score": 2, "rationale": "访谈样本仍然偏少。"},
            ],
            "detected_rules": [
                {"rule_id": "H9", "status": "warning", "message": "需求验证证据偏弱。"},
                {"rule_id": "H10", "status": "pass", "message": "执行计划基本可用。"},
            ],
            "structured_diagnosis": {
                "risk_level": "warning",
                "claims": [
                    {"field": "validation_evidence", "statement": "现有证据能说明方向，但不足以支撑规模化判断。"},
                ],
            },
        },
    }
    finance_payload = {
        "reply": "月收入和现金跑道目前可支撑小规模试点，但尚未形成稳定闭环。",
        "structured_output": {
            "summary": "财务模型可用于试点阶段，但仍需验证转化率。",
            "commercialization_assessment": "适合先做校内试点，再决定是否扩大。",
            "strongest_signal": "现金跑道足够支撑首轮 MVP。",
            "biggest_risk": "LTV/CAC 还缺少真实转化数据。",
            "next_action": "先验证首批付费学校的转化率。",
            "follow_up_question": "首批试点学校的签约周期大概多长？",
            "strengths": ["单校部署成本可控。"],
            "risks": ["转化率未验证。"],
            "assumptions": ["按校年费订阅能被学校预算接受。"],
            "metrics": [
                {"key": "monthly_revenue", "name": "月收入", "display": "12000", "note": "按当前试点估算"},
                {"key": "ltv_cac_ratio", "name": "LTV/CAC", "display": "1.8x", "note": "仍需更多样本"},
                {"key": "runway_months", "name": "现金跑道", "display": "9个月", "note": "基于当前烧钱速度"},
            ],
        },
    }
    competition_payload = {
        "template_name": "创新创业通用",
        "final_score": 3.8,
        "item_reports": [
            {
                "name": "证据支撑",
                "estimated_score": "2/5",
                "missing_evidence": "访谈样本数量不足",
                "fix_24h": "补充 5 份访谈并更新纪要",
            }
        ],
    }
    idea_messages = [
        {"role": "user", "content": "我想做一个校园心理健康项目。"},
        {"role": "assistant", "content": "先说清你的目标用户和最小试点场景。"},
    ]

    filename, docx_bytes = build_word_plan_document(
        idea_output=idea_output,
        diagnosis_payload=diagnosis_payload,
        finance_payload=finance_payload,
        competition_payload=competition_payload,
        idea_messages=idea_messages,
    )

    assert filename == "校园健康AI_计划书.docx"
    with ZipFile(BytesIO(docx_bytes)) as archive:
        assert {"[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "word/document.xml"} <= set(archive.namelist())
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "校园健康AI计划书" in document_xml
    assert "一、项目概述" in document_xml
    assert "八、财务与商业化分析" in document_xml
    assert "九、路演评分与改进建议" in document_xml
    assert "学生压力筛查 &amp; 干预 &lt;试点&gt;" in document_xml
    assert "创新创业通用" in document_xml


def test_build_word_plan_document_supports_partial_results() -> None:
    filename, docx_bytes = build_word_plan_document(
        diagnosis_payload={
            "request": {"project_id": "p-002", "project_text": "一个面向校园社团的协作平台。"},
            "output": {
                "current_diagnosis": "渠道与用户仍有错位。",
                "next_task": "先补目标用户访谈。",
            },
        }
    )

    assert filename == "p-002_计划书.docx"
    with ZipFile(BytesIO(docx_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "创业项目" not in document_xml
    assert "渠道与用户仍有错位。" in document_xml
    assert "二、当前项目草案" in document_xml


class DummyPlanPolishClient:
    available = True

    def chat_json(self, *, system_prompt: str, user_prompt: str, model=None, temperature=0.0, max_attempts=2):  # noqa: ARG002
        assert "Return JSON only." in system_prompt
        assert "附录" not in user_prompt
        return {
            "sections": [
                {
                    "heading": "一、项目概述",
                    "paragraphs": [
                        "这是经过 AI 润色后的项目概述，表达更适合正式项目书提交。",
                        "当前项目已形成问题、用户和阶段性行动的基本闭环。",
                    ],
                }
            ]
        }


def test_build_word_plan_document_can_polish_body_and_preserve_appendix() -> None:
    idea_output = {
        "overview": "原始概述",
        "generated_project_text": "项目名称：知识卡片助手\n问题：资料零散\n客户：考研学生",
        "draft_state": {
            "project_name": "知识卡片助手",
            "problem": "资料零散",
            "customer_segment": "考研学生",
        },
    }
    idea_messages = [
        {"role": "user", "content": "我想做一个帮助学生整理资料的工具。"},
        {"role": "assistant", "content": "请先明确你的目标用户和最小方案。"},
    ]

    filename, docx_bytes = build_word_plan_document(
        idea_output=idea_output,
        idea_messages=idea_messages,
        beautify_with_ai=True,
        llm_client=DummyPlanPolishClient(),
    )

    assert filename == "知识卡片助手_计划书.docx"
    with ZipFile(BytesIO(docx_bytes)) as archive:
        document_xml = archive.read("word/document.xml").decode("utf-8")

    assert "AI 润色：已启用，附录原始内容保持不改写。" in document_xml
    assert "这是经过 AI 润色后的项目概述，表达更适合正式项目书提交。" in document_xml
    assert "A0 追问记录摘录" in document_xml
    assert "我想做一个帮助学生整理资料的工具。" in document_xml
    assert "请先明确你的目标用户和最小方案。" in document_xml
