from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from .evidence import format_evidence
from .llm_client import DeepSeekClient

PROJECT_FIELD_LABELS = {
    "project_name": "项目名称",
    "problem": "问题",
    "customer_segment": "客户",
    "value_proposition": "价值主张",
    "channel": "渠道",
    "revenue_model": "收入模式",
    "cost_structure": "成本结构",
    "traction": "进展",
    "tam": "TAM",
    "sam": "SAM",
    "som": "SOM",
    "ltv": "LTV",
    "cac": "CAC",
    "compliance_notes": "合规说明",
    "payer": "付费方",
    "validation_evidence": "验证证据",
    "execution_plan": "执行计划",
    "competitive_advantage": "竞争优势",
    "retention_strategy": "留存机制",
    "growth_target": "增长目标",
    "pilot_plan": "试点计划",
}

PROJECT_FIELD_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("二、项目基础信息", ("project_name", "problem", "customer_segment")),
    ("三、解决方案与商业模式", ("value_proposition", "competitive_advantage", "channel", "revenue_model", "payer")),
    ("四、市场、验证与试点安排", ("tam", "sam", "som", "validation_evidence", "traction", "pilot_plan")),
    ("五、执行与增长规划", ("execution_plan", "growth_target", "retention_strategy", "cost_structure", "compliance_notes")),
)

KEY_FINANCE_METRICS: tuple[str, ...] = (
    "monthly_revenue",
    "gross_margin_pct",
    "monthly_net_profit",
    "ltv_cac_ratio",
    "runway_months",
    "payback_months",
)

STATUS_LABELS = {
    "pass": "通过",
    "warning": "预警",
    "fail": "失败",
    "high_risk": "高风险",
}

RISK_LEVEL_LABELS = {
    "normal": "正常",
    "warning": "预警",
    "high_risk": "高风险",
}


@dataclass(frozen=True)
class DocxParagraph:
    text: str
    kind: str = "body"


@dataclass(frozen=True)
class PlanSection:
    heading: str
    lines: list[str]
    preserve_raw: bool = False


class WordPlanBeautifierAgent:
    def __init__(self, llm_client: DeepSeekClient | None = None) -> None:
        self.llm_client = llm_client or DeepSeekClient()

    @property
    def available(self) -> bool:
        return self.llm_client.available

    def polish_sections(self, *, project_title: str, sections: list[PlanSection]) -> list[PlanSection]:
        if not self.available:
            return sections

        editable_sections = [section for section in sections if not section.preserve_raw]
        if not editable_sections:
            return sections

        payload = [
            {"heading": section.heading, "lines": section.lines}
            for section in editable_sections
        ]
        system_prompt = (
            "You are a venture project-book editor. "
            "Rewrite the provided sections in concise, professional Chinese. "
            "Improve structure, wording, and readability for a formal project document. "
            "Do not invent facts. Preserve numeric values, rule IDs, evidence references, and action items. "
            "Return JSON only."
        )
        user_prompt = (
            f"Project title: {project_title}\n\n"
            "Polish the following project-book sections. Keep the same order and headings. "
            "Each section should return 2 to 6 polished paragraphs. "
            "Do not include appendix-like raw dialogue or transcript content.\n\n"
            f"Input JSON:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "Return this JSON shape exactly:\n"
            '{"sections":[{"heading":"原标题","paragraphs":["段落1","段落2"]}]}'
        )
        try:
            response = self.llm_client.chat_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2,
            )
        except Exception:
            return sections

        polished_map: dict[str, list[str]] = {}
        for item in response.get("sections", []):
            if not isinstance(item, dict):
                continue
            heading = _text(item.get("heading"))
            paragraphs = [_normalize_line(text) for text in item.get("paragraphs", []) if _normalize_line(text)]
            if heading and paragraphs:
                polished_map[heading] = paragraphs[:6]

        result: list[PlanSection] = []
        for section in sections:
            if section.preserve_raw:
                result.append(section)
                continue
            polished_lines = polished_map.get(section.heading)
            result.append(
                PlanSection(
                    heading=section.heading,
                    lines=polished_lines or section.lines,
                    preserve_raw=False,
                )
            )
        return result


def build_word_plan_document(
    *,
    idea_output: dict[str, Any] | None = None,
    diagnosis_payload: dict[str, Any] | None = None,
    finance_payload: dict[str, Any] | None = None,
    competition_payload: dict[str, Any] | None = None,
    idea_messages: list[dict[str, Any]] | None = None,
    exported_at: datetime | None = None,
    beautify_with_ai: bool = False,
    llm_client: DeepSeekClient | None = None,
) -> tuple[str, bytes]:
    idea_output = _as_dict(idea_output)
    diagnosis_payload = _as_dict(diagnosis_payload)
    finance_payload = _as_dict(finance_payload)
    competition_payload = _as_dict(competition_payload)
    idea_messages = idea_messages or []

    if not any((idea_output, diagnosis_payload, finance_payload, competition_payload, idea_messages)):
        raise ValueError("No result payload available for plan export.")

    exported_at = exported_at or datetime.now()
    project_title = _infer_project_title(idea_output, diagnosis_payload)
    document_title = f"{project_title}计划书"
    sections = _build_sections(
        idea_output=idea_output,
        diagnosis_payload=diagnosis_payload,
        finance_payload=finance_payload,
        competition_payload=competition_payload,
        idea_messages=idea_messages,
    )
    if beautify_with_ai:
        sections = WordPlanBeautifierAgent(llm_client=llm_client).polish_sections(
            project_title=project_title,
            sections=sections,
        )

    paragraphs = [
        DocxParagraph(document_title, "title"),
        DocxParagraph(f"导出时间：{exported_at.strftime('%Y-%m-%d %H:%M')}", "subtitle"),
        DocxParagraph(f"生成来源：Idea / 诊断 / 财务 / 路演评分自动汇总", "subtitle"),
        DocxParagraph("AI 润色：已启用，附录原始内容保持不改写。" if beautify_with_ai else "AI 润色：未启用。", "subtitle"),
        DocxParagraph("", "page_break"),
    ]

    for section in sections:
        paragraphs.append(DocxParagraph(section.heading, "heading1"))
        paragraphs.extend(DocxParagraph(line, "body") for line in section.lines)

    filename = f"{_safe_filename(project_title)}_计划书.docx"
    return filename, _render_docx(document_title=document_title, paragraphs=paragraphs, exported_at=exported_at)


def _build_sections(
    *,
    idea_output: dict[str, Any],
    diagnosis_payload: dict[str, Any],
    finance_payload: dict[str, Any],
    competition_payload: dict[str, Any],
    idea_messages: list[dict[str, Any]],
) -> list[PlanSection]:
    sections: list[PlanSection] = []

    diagnosis_output = _as_dict(diagnosis_payload.get("output"))
    diagnosis_request = _as_dict(diagnosis_payload.get("request"))
    finance_output = _as_dict(finance_payload.get("structured_output"))
    draft_state = _as_dict(idea_output.get("draft_state"))

    overview_lines: list[str] = []
    if _text(idea_output.get("overview")):
        overview_lines.append(_text(idea_output.get("overview")))
    if _text(idea_output.get("stage_label")):
        overview_lines.append(f"当前阶段：{_text(idea_output.get('stage_label'))}")
    if _text(idea_output.get("focus_rule_id")):
        overview_lines.append(f"当前超图焦点：{_text(idea_output.get('focus_rule_id'))}")
    if _text(diagnosis_output.get("current_diagnosis")):
        overview_lines.append(f"当前诊断：{_text(diagnosis_output.get('current_diagnosis'))}")
    if _text(diagnosis_output.get("next_task")):
        overview_lines.append(f"当前优先动作：{_text(diagnosis_output.get('next_task'))}")
    if _text(finance_output.get("summary")):
        overview_lines.append(f"商业化判断：{_text(finance_output.get('summary'))}")
    _append_section(sections, "一、项目概述", overview_lines)

    if draft_state:
        for heading, fields in PROJECT_FIELD_SECTIONS:
            _append_section(sections, heading, _build_field_lines(draft_state, fields))
    else:
        fallback_draft = _split_text_block(_text(idea_output.get("generated_project_text")) or _text(diagnosis_request.get("project_text")))
        _append_section(sections, "二、当前项目草案", fallback_draft)

    diagnosis_lines = _build_diagnosis_lines(diagnosis_output, idea_output)
    _append_section(sections, "六、风险诊断与修复建议", diagnosis_lines)

    evidence_and_scores = _build_evidence_and_score_lines(diagnosis_output)
    _append_section(sections, "七、关键证据与评分", evidence_and_scores)

    finance_lines = _build_finance_lines(finance_payload, finance_output)
    _append_section(sections, "八、财务与商业化分析", finance_lines)

    competition_lines = _build_competition_lines(competition_payload)
    _append_section(sections, "九、路演评分与改进建议", competition_lines)

    appendix_lines = _build_appendix_lines(idea_output, diagnosis_output, idea_messages)
    _append_section(sections, "十、附录与过程摘录", appendix_lines, preserve_raw=True)

    return sections


def _build_field_lines(draft_state: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for field in fields:
        value = draft_state.get(field)
        if value in (None, "", [], {}):
            continue
        label = PROJECT_FIELD_LABELS.get(field, field)
        lines.append(f"{label}：{_stringify(value)}")
    return lines


def _build_diagnosis_lines(diagnosis_output: dict[str, Any], idea_output: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if _text(diagnosis_output.get("current_diagnosis")):
        lines.append(f"核心诊断：{_text(diagnosis_output.get('current_diagnosis'))}")
    if _text(diagnosis_output.get("impact")):
        lines.append(f"影响说明：{_text(diagnosis_output.get('impact'))}")
    if _text(diagnosis_output.get("next_task")):
        lines.append(f"下一步任务：{_text(diagnosis_output.get('next_task'))}")
    elif _text(idea_output.get("next_action")):
        lines.append(f"下一步任务：{_text(idea_output.get('next_action'))}")

    structured = _as_dict(diagnosis_output.get("structured_diagnosis"))
    if structured:
        if _text(structured.get("risk_level")):
            risk_label = RISK_LEVEL_LABELS.get(_text(structured.get("risk_level")), _text(structured.get("risk_level")))
            lines.append(f"风险等级：{risk_label}")
        for claim in structured.get("claims", [])[:5]:
            claim_dict = _as_dict(claim)
            statement = _text(claim_dict.get("statement"))
            if not statement:
                continue
            claim_field = _text(claim_dict.get("field"))
            field_label = PROJECT_FIELD_LABELS.get(claim_field, claim_field) if claim_field else "关键判断"
            lines.append(f"- {field_label}：{statement}")

    non_pass_rules = [rule for rule in diagnosis_output.get("detected_rules", []) if _text(_as_dict(rule).get("status")) != "pass"]
    if non_pass_rules:
        lines.append("重点规则：")
        for rule in non_pass_rules[:5]:
            rule_dict = _as_dict(rule)
            status = STATUS_LABELS.get(_text(rule_dict.get("status")), _text(rule_dict.get("status")))
            lines.append(f"- {rule_dict.get('rule_id', 'unknown')} [{status}] {_text(rule_dict.get('message'))}")
    return lines


def _build_evidence_and_score_lines(diagnosis_output: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    evidence_items = diagnosis_output.get("evidence_used", [])
    if evidence_items:
        lines.append("关键证据：")
        for item in evidence_items[:6]:
            lines.append(f"- {format_evidence(item)}")

    score_summary = _as_dict(diagnosis_output.get("score_summary"))
    if score_summary:
        lines.append(
            "统一评分摘要："
            f"{_text(score_summary.get('weighted_final_score'))}/5"
            f"；阶段：{_text(score_summary.get('stage_label'))}"
            f"；等级：{_text(score_summary.get('score_band'))}"
        )
        if _text(score_summary.get("summary")):
            lines.append(f"统一评分结论：{_text(score_summary.get('summary'))}")
        weakest = [_text(item) for item in score_summary.get("weakest_dimensions", []) if _text(item)]
        if weakest:
            lines.append(f"优先修复维度：{'、'.join(weakest[:3])}")

    rubric_scores = diagnosis_output.get("rubric_scores", [])
    if rubric_scores:
        lines.append("Rubric 评分：")
        ordered_scores = sorted((_as_dict(item) for item in rubric_scores), key=lambda item: item.get("score", 0))
        for item in ordered_scores[:6]:
            rationale = _text(item.get("rationale"))
            tail = f"；说明：{rationale}" if rationale else ""
            lines.append(f"- {item.get('name', item.get('rubric_id', 'Rubric'))}：{item.get('score', '-')}/5{tail}")
    return lines


def _build_finance_lines(finance_payload: dict[str, Any], finance_output: dict[str, Any]) -> list[str]:
    if not finance_output:
        return []

    lines: list[str] = []
    if _text(finance_output.get("summary")):
        lines.append(f"财务结论：{_text(finance_output.get('summary'))}")
    if _text(finance_output.get("commercialization_assessment")):
        lines.append(f"商业化评估：{_text(finance_output.get('commercialization_assessment'))}")
    if _text(finance_output.get("strongest_signal")):
        lines.append(f"最强信号：{_text(finance_output.get('strongest_signal'))}")
    if _text(finance_output.get("biggest_risk")):
        lines.append(f"最大风险：{_text(finance_output.get('biggest_risk'))}")
    if _text(finance_output.get("next_action")):
        lines.append(f"财务优先动作：{_text(finance_output.get('next_action'))}")
    if _text(finance_output.get("follow_up_question")):
        lines.append(f"继续追问：{_text(finance_output.get('follow_up_question'))}")
    if _text(finance_payload.get("reply")):
        lines.append(f"Agent 说明：{_text(finance_payload.get('reply'))}")

    strengths = [_text(item) for item in finance_output.get("strengths", []) if _text(item)]
    if strengths:
        lines.append("优势信号：")
        lines.extend(f"- {item}" for item in strengths[:4])

    risks = [_text(item) for item in finance_output.get("risks", []) if _text(item)]
    if risks:
        lines.append("风险信号：")
        lines.extend(f"- {item}" for item in risks[:4])

    assumptions = [_text(item) for item in finance_output.get("assumptions", []) if _text(item)]
    if assumptions:
        lines.append("当前口径假设：")
        lines.extend(f"- {item}" for item in assumptions[:4])

    metrics = {
        _text(_as_dict(item).get("key")): _as_dict(item)
        for item in finance_output.get("metrics", [])
        if _text(_as_dict(item).get("key"))
    }
    metric_lines: list[str] = []
    for key in KEY_FINANCE_METRICS:
        item = metrics.get(key)
        if not item:
            continue
        display = _text(item.get("display"))
        if not display or display == "—":
            continue
        note = _text(item.get("note"))
        suffix = f"（{note}）" if note else ""
        metric_lines.append(f"- {_text(item.get('name'))}：{display}{suffix}")
    if metric_lines:
        lines.append("关键财务指标：")
        lines.extend(metric_lines)
    return lines


def _build_competition_lines(competition_payload: dict[str, Any]) -> list[str]:
    if not competition_payload:
        return []

    lines: list[str] = []
    if _text(competition_payload.get("template_name")):
        lines.append(f"评分模板：{_text(competition_payload.get('template_name'))}")
    if competition_payload.get("final_score") not in (None, ""):
        lines.append(f"加权总分：{competition_payload.get('final_score')}/5")
    if _text(competition_payload.get("stage_label")):
        lines.append(f"当前阶段：{_text(competition_payload.get('stage_label'))}")
    if _text(competition_payload.get("score_band")):
        lines.append(f"评分等级：{_text(competition_payload.get('score_band'))}")
    if _text(competition_payload.get("summary")):
        lines.append(f"统一评分结论：{_text(competition_payload.get('summary'))}")
    if competition_payload.get("average_score") not in (None, ""):
        lines.append(f"Rubric 均分：{competition_payload.get('average_score')}/5")
    reports = competition_payload.get("item_reports", [])
    if reports:
        lines.append("优先改进维度：")
        for item in reports[:5]:
            item_dict = _as_dict(item)
            lines.append(
                f"- {item_dict.get('name', '维度')}：{item_dict.get('estimated_score', '-')}"
                f"；证据缺口：{_text(item_dict.get('missing_evidence'))}"
                f"；24h 修复：{_text(item_dict.get('fix_24h'))}"
            )
    return lines


def _build_appendix_lines(
    idea_output: dict[str, Any],
    diagnosis_output: dict[str, Any],
    idea_messages: list[dict[str, Any]],
) -> list[str]:
    lines: list[str] = []
    generated_project_text = _text(idea_output.get("generated_project_text"))
    if generated_project_text:
        lines.append("当前自动收敛草案：")
        lines.extend(_split_text_block(generated_project_text))

    markdown_report = _text(diagnosis_output.get("markdown_report"))
    if markdown_report:
        lines.append("Markdown 报告摘录：")
        lines.extend(_split_text_block(markdown_report, limit=16))

    if idea_messages:
        lines.append("A0 追问记录摘录：")
        for item in idea_messages[-8:]:
            role = "用户" if _text(_as_dict(item).get("role")) == "user" else "系统"
            content = _truncate(_text(_as_dict(item).get("content")), limit=120)
            if content:
                lines.append(f"- {role}：{content}")
    return lines


def _append_section(
    sections: list[PlanSection],
    heading: str,
    lines: list[str],
    *,
    preserve_raw: bool = False,
) -> None:
    normalized = [line for line in (_normalize_line(item) for item in lines) if line]
    if normalized:
        sections.append(PlanSection(heading=heading, lines=normalized, preserve_raw=preserve_raw))


def _render_docx(*, document_title: str, paragraphs: list[DocxParagraph], exported_at: datetime) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _build_content_types_xml())
        archive.writestr("_rels/.rels", _build_root_relationships_xml())
        archive.writestr("docProps/core.xml", _build_core_properties_xml(document_title, exported_at))
        archive.writestr("docProps/app.xml", _build_app_properties_xml())
        archive.writestr("word/document.xml", _build_document_xml(paragraphs))
    return buffer.getvalue()


def _build_document_xml(paragraphs: list[DocxParagraph]) -> str:
    body = "".join(_render_paragraph(item) for item in paragraphs)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}"
        '<w:sectPr>'
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>'
        "</w:sectPr>"
        "</w:body></w:document>"
    )


def _render_paragraph(paragraph: DocxParagraph) -> str:
    if paragraph.kind == "page_break":
        return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'

    text = _normalize_line(paragraph.text)
    if not text:
        return "<w:p/>"

    alignment = ""
    spacing = ""
    run_props = (
        '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Microsoft YaHei"/>'
        '<w:lang w:val="zh-CN" w:eastAsia="zh-CN"/>'
    )

    if paragraph.kind == "title":
        alignment = '<w:jc w:val="center"/>'
        spacing = '<w:spacing w:after="240"/>'
        run_props += '<w:b/><w:sz w:val="32"/><w:szCs w:val="32"/>'
    elif paragraph.kind == "subtitle":
        alignment = '<w:jc w:val="center"/>'
        spacing = '<w:spacing w:after="120"/>'
        run_props += '<w:color w:val="666666"/><w:sz w:val="21"/><w:szCs w:val="21"/>'
    elif paragraph.kind == "heading1":
        spacing = '<w:spacing w:before="240" w:after="120"/>'
        run_props += '<w:b/><w:sz w:val="28"/><w:szCs w:val="28"/>'
    else:
        spacing = '<w:spacing w:after="90"/>'
        run_props += '<w:sz w:val="22"/><w:szCs w:val="22"/>'

    paragraph_props = f"<w:pPr>{alignment}{spacing}</w:pPr>" if alignment or spacing else ""
    return (
        f"<w:p>{paragraph_props}"
        f"<w:r><w:rPr>{run_props}</w:rPr><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r>"
        "</w:p>"
    )


def _build_content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def _build_root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _build_core_properties_xml(document_title: str, exported_at: datetime) -> str:
    timestamp = exported_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_title = escape(document_title)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{safe_title}</dc:title>"
        "<dc:creator>startup-edu-agent</dc:creator>"
        "<cp:lastModifiedBy>startup-edu-agent</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{timestamp}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _build_app_properties_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>startup-edu-agent</Application>"
        "</Properties>"
    )


def _infer_project_title(idea_output: dict[str, Any], diagnosis_payload: dict[str, Any]) -> str:
    draft_state = _as_dict(idea_output.get("draft_state"))
    for candidate in (
        draft_state.get("project_name"),
        idea_output.get("project_name"),
        _extract_project_name(_text(idea_output.get("generated_project_text"))),
        _extract_project_name(_text(_as_dict(diagnosis_payload.get("request")).get("project_text"))),
        _as_dict(diagnosis_payload.get("request")).get("project_id"),
    ):
        text = _text(candidate)
        if text:
            return text
    return "创业项目"


def _extract_project_name(project_text: str) -> str:
    if not project_text:
        return ""
    lines = [line.strip() for line in project_text.splitlines() if line.strip()]
    for line in lines:
        if "：" in line:
            label, value = line.split("：", 1)
        elif ":" in line:
            label, value = line.split(":", 1)
        else:
            continue
        if "项目" in label and "名称" in label:
            return value.strip()
    return ""


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "创业项目"


def _split_text_block(text: str, *, limit: int | None = None) -> list[str]:
    lines = [_normalize_line(line) for line in text.splitlines()]
    filtered = [line for line in lines if line]
    if limit is not None:
        return filtered[:limit]
    return filtered


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _stringify(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalize_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return str(value).strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
