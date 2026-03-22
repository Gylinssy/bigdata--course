from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .evidence import dedupe_evidence, format_evidence
from .extractor import ProjectExtractor
from .llm_client import DeepSeekClient
from .models import CoachOutput, EvidenceItem, ProjectCoachRequest, TeacherDashboard
from .retrieval.case_store import CaseStore
from .rule_engine import RuleEngine
from .rubric import RubricScorer


class ProjectCoachPipeline:
    def __init__(
        self,
        extractor: ProjectExtractor | None = None,
        rule_engine: RuleEngine | None = None,
        rubric_scorer: RubricScorer | None = None,
        case_store: CaseStore | None = None,
        archive_dir: Path | str = Path("outputs/projects"),
    ) -> None:
        client = DeepSeekClient()
        self.extractor = extractor or ProjectExtractor(client)
        self.rule_engine = rule_engine or RuleEngine()
        self.rubric_scorer = rubric_scorer or RubricScorer()
        self.case_store = case_store or CaseStore()
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def run(self, request: ProjectCoachRequest) -> CoachOutput:
        state, extraction_evidence = self.extractor.extract(request.project_text)
        detected_rules = self.rule_engine.evaluate(state, request.project_text, extraction_evidence)
        rubric_scores = self.rubric_scorer.score(state, detected_rules, extraction_evidence)

        top_rule = sorted(detected_rules, key=self.rule_engine.rank, reverse=True)[0]
        query = f"{top_rule.rule_id} {top_rule.message} {state.problem or ''} {state.customer_segment or ''}".strip()
        case_evidence = self.case_store.retrieve_cases(query, top_k=3) if self.case_store.has_cases() else []

        evidence_used = dedupe_evidence(top_rule.evidence + case_evidence + extraction_evidence[:2])
        output = CoachOutput(
            current_diagnosis=f"{top_rule.rule_id}: {top_rule.message}",
            evidence_used=evidence_used,
            impact=self._build_impact(top_rule.message, case_evidence),
            next_task=top_rule.fix_task or self._fallback_task(top_rule.rule_id),
            rubric_scores=rubric_scores,
            detected_rules=detected_rules,
            retrieved_case_evidence=case_evidence,
        )
        output.markdown_report = self.render_markdown(output)
        self._archive_run(request, state.model_dump(), output.model_dump(mode="json"))
        return output

    def render_markdown(self, output: CoachOutput) -> str:
        evidence_lines = "\n".join(f"- {format_evidence(item)}" for item in output.evidence_used)
        rubric_lines = "\n".join(
            f"- {score.rubric_id} {score.name}: {score.score}/5 ({score.rationale})"
            for score in output.rubric_scores
        )
        rule_lines = "\n".join(
            f"- {rule.rule_id}: {rule.status.value} / {rule.severity.value} / {rule.message}"
            for rule in output.detected_rules
        )
        return (
            "## Current Diagnosis\n"
            f"{output.current_diagnosis}\n\n"
            "## Evidence Used\n"
            f"{evidence_lines or '- None'}\n\n"
            "## Impact\n"
            f"{output.impact}\n\n"
            "## Next Task\n"
            f"{output.next_task}\n\n"
            "## Triggered Rules\n"
            f"{rule_lines}\n\n"
            "## Rubric Scores\n"
            f"{rubric_lines}"
        )

    def teacher_dashboard(self) -> TeacherDashboard:
        records = []
        for path in sorted(self.archive_dir.glob("*.json")):
            records.append(json.loads(path.read_text(encoding="utf-8")))

        rule_counter = Counter()
        high_risk_projects = []
        field_hotspots = Counter()
        tracked_fields = (
            "problem",
            "customer_segment",
            "value_proposition",
            "channel",
            "tam",
            "sam",
            "som",
            "ltv",
            "cac",
            "compliance_notes",
            "payer",
            "validation_evidence",
            "execution_plan",
            "competitive_advantage",
            "retention_strategy",
            "growth_target",
            "pilot_plan",
        )
        for record in records:
            output = record["output"]
            for rule in output["detected_rules"]:
                if rule["status"] != "pass":
                    rule_counter[rule["rule_id"]] += 1
                if rule["status"] == "high_risk":
                    high_risk_projects.append(record["request"].get("project_id") or record["request"]["user_id"])
            extracted_fields = {item.get("field") for item in output["evidence_used"] if item.get("field")}
            for field in tracked_fields:
                if field not in extracted_fields:
                    field_hotspots[field] += 1

        suggestions = []
        if rule_counter:
            top_rule, _ = rule_counter.most_common(1)[0]
            suggestions.append(f"优先做 {top_rule} 主题的集中讲解和模板化练习。")
        if high_risk_projects:
            suggestions.append("先单独审阅 high_risk 项目，避免敏感场景直接进入试点。")

        return TeacherDashboard(
            total_projects=len(records),
            top_rule_triggers=dict(rule_counter),
            high_risk_projects=high_risk_projects,
            field_missing_hotspots=dict(field_hotspots),
            intervention_suggestions=suggestions,
        )

    def _archive_run(self, request: ProjectCoachRequest, state: dict, output: dict) -> None:
        archive_name = request.project_id or f"{request.user_id}-latest"
        (self.archive_dir / f"{archive_name}.json").write_text(
            json.dumps({"request": request.model_dump(), "state": state, "output": output}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _fallback_task(rule_id: str) -> str:
        return f"围绕 {rule_id} 补一页修复说明；验收标准：问题、数据、动作、负责人四项齐全。"

    @staticmethod
    def _build_impact(rule_message: str, case_evidence: list[EvidenceItem]) -> str:
        if case_evidence:
            return f"{rule_message} 类似问题在案例库中也出现过，若不修正会直接拖累验证效率和落地风险。"
        return f"{rule_message} 如果不先处理，后续的市场验证、获客和试点都可能建立在错误假设上。"
