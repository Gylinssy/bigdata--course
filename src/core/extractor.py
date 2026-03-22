from __future__ import annotations

import re
from typing import Any

from .llm_client import DeepSeekClient, load_prompt
from .models import EvidenceItem, EvidenceSource, ProjectState


FIELD_LABELS: dict[str, list[str]] = {
    "project_name": ["项目名称", "项目名", "project name", "name"],
    "problem": ["问题", "problem", "痛点"],
    "customer_segment": ["客户", "目标客户", "用户", "customer", "segment"],
    "value_proposition": ["价值主张", "方案", "产品价值", "value proposition"],
    "channel": ["渠道", "获客渠道", "channel"],
    "revenue_model": ["收入模式", "盈利模式", "revenue", "business model"],
    "cost_structure": ["成本结构", "主要成本", "cost"],
    "traction": ["进展", "里程碑", "traction"],
    "compliance_notes": ["合规", "风控", "伦理", "compliance", "risk"],
    "payer": ["付费方", "付款方", "谁付费", "payer"],
    "validation_evidence": ["验证证据", "需求验证", "用户访谈", "试点数据", "问卷结果"],
    "execution_plan": ["执行计划", "落地计划", "时间计划", "版本计划", "milestone"],
    "competitive_advantage": ["差异化", "竞争优势", "竞争壁垒", "竞品对比", "护城河"],
    "retention_strategy": ["留存机制", "复购机制", "留存策略", "续费策略", "retention"],
    "growth_target": ["增长目标", "用户目标", "营收目标", "季度目标", "growth target"],
    "pilot_plan": ["试点计划", "试点路径", "试点对象", "首批试点", "pilot plan"],
}

NUMERIC_LABELS: dict[str, list[str]] = {
    "tam": ["tam"],
    "sam": ["sam"],
    "som": ["som"],
    "ltv": ["ltv"],
    "cac": ["cac"],
}


class ProjectExtractor:
    def __init__(self, llm_client: DeepSeekClient | None = None, enable_llm: bool = True) -> None:
        self.llm_client = llm_client or DeepSeekClient()
        self.enable_llm = enable_llm

    def extract(self, project_text: str) -> tuple[ProjectState, list[EvidenceItem]]:
        heuristic_state, evidence = self._heuristic_extract(project_text)
        if self.enable_llm and self.llm_client.available:
            try:
                refined = self._llm_refine(project_text, heuristic_state)
                return heuristic_state.model_copy(update=refined), evidence
            except Exception:
                return heuristic_state, evidence
        return heuristic_state, evidence

    def _heuristic_extract(self, text: str) -> tuple[ProjectState, list[EvidenceItem]]:
        data: dict[str, Any] = {}
        evidence: list[EvidenceItem] = []

        for field, labels in FIELD_LABELS.items():
            value, quote, start, end = self._extract_labeled_field(text, labels)
            if value:
                data[field] = value
                evidence.append(
                    EvidenceItem(
                        source=EvidenceSource.EXTRACTED_FIELD,
                        quote=quote,
                        start=start,
                        end=end,
                        field=field,
                    )
                )

        for field, labels in NUMERIC_LABELS.items():
            value, quote, start, end = self._extract_numeric_field(text, labels)
            if value is not None:
                data[field] = value
                evidence.append(
                    EvidenceItem(
                        source=EvidenceSource.EXTRACTED_FIELD,
                        quote=quote,
                        start=start,
                        end=end,
                        field=field,
                    )
                )

        if "project_name" not in data:
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), None)
            if first_line:
                start = text.find(first_line)
                data["project_name"] = first_line[:80]
                evidence.append(
                    EvidenceItem(
                        source=EvidenceSource.USER_INPUT,
                        quote=first_line,
                        start=start,
                        end=start + len(first_line),
                        field="project_name",
                    )
                )

        return ProjectState(**data), evidence

    def _llm_refine(self, text: str, heuristic_state: ProjectState) -> dict[str, Any]:
        system_prompt = load_prompt("system.md")
        extractor_prompt = load_prompt("extractor.md")
        user_prompt = (
            f"{extractor_prompt}\n\n"
            f"Project text:\n{text}\n\n"
            f"Heuristic JSON:\n{heuristic_state.model_dump_json()}\n\n"
            "Return a JSON object with only known ProjectState fields."
        )
        return self.llm_client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)

    @staticmethod
    def _extract_labeled_field(text: str, labels: list[str]) -> tuple[str | None, str | None, int | None, int | None]:
        for label in labels:
            pattern = re.compile(rf"{re.escape(label)}\s*[:：]\s*(.+)", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                value = match.group(1).strip()
                return value, match.group(0).strip(), match.start(), match.end()
        return None, None, None, None

    @staticmethod
    def _extract_numeric_field(
        text: str,
        labels: list[str],
    ) -> tuple[float | None, str | None, int | None, int | None]:
        for label in labels:
            pattern = re.compile(rf"{re.escape(label)}\s*[:：]?\s*(-?\d+(?:,\d{{3}})*(?:\.\d+)?)", re.IGNORECASE)
            match = pattern.search(text)
            if match:
                number = float(match.group(1).replace(",", ""))
                return number, match.group(0).strip(), match.start(), match.end()

        market_line = re.search(r"市场规模[:：]?\s*(.+)", text)
        if market_line:
            snippet = market_line.group(1)
            for label in labels:
                inline = re.search(rf"{re.escape(label)}\s*(-?\d+(?:,\d{{3}})*(?:\.\d+)?)", snippet, re.IGNORECASE)
                if inline:
                    number = float(inline.group(1).replace(",", ""))
                    start = market_line.start(1) + inline.start()
                    end = market_line.start(1) + inline.end()
                    return number, inline.group(0), start, end
        return None, None, None, None
