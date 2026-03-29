from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from time import perf_counter

from .coach_agent import StructuredCoachAgent
from .evidence import dedupe_evidence, format_evidence
from .extractor import ProjectExtractor
from .llm_client import DeepSeekClient
from .models import (
    CoachOutput,
    ConstraintValidationReport,
    EvidenceItem,
    EvidenceSource,
    ProjectState,
    ProjectCoachRequest,
    RenderedViews,
    RuleResult,
    RuleStatus,
    StructuredDiagnosis,
    TeacherDashboard,
)
from .pressure_trace import build_pressure_trace, pressure_trace_to_text
from .retrieval.case_store import CaseStore
from .runtime_log import RuntimeLogger, new_run_id, preview_text
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
        runtime_logger: RuntimeLogger | None = None,
    ) -> None:
        client = DeepSeekClient()
        self.runtime_logger = runtime_logger or RuntimeLogger()
        self.extractor = extractor or ProjectExtractor(client, runtime_logger=self.runtime_logger)
        self.rule_engine = rule_engine or RuleEngine()
        self.rubric_scorer = rubric_scorer or RubricScorer()
        self.case_store = case_store or CaseStore()
        self.coach_agent = StructuredCoachAgent(client, runtime_logger=self.runtime_logger)
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def run(self, request: ProjectCoachRequest) -> CoachOutput:
        run_id = new_run_id("project-coach")
        started_at = perf_counter()
        self.runtime_logger.log(
            "project_coach_pipeline",
            "request_started",
            run_id=run_id,
            user_id=request.user_id,
            project_id=request.project_id,
            project_preview=preview_text(request.project_text, limit=220),
        )
        try:
            state, extraction_evidence = self.extractor.extract(request.project_text, run_id=run_id)
            self.runtime_logger.log(
                "project_coach_pipeline",
                "extraction_completed",
                run_id=run_id,
                extracted_field_count=len(state.model_dump(exclude_none=True)),
                evidence_count=len(extraction_evidence),
            )
            detected_rules = self.rule_engine.evaluate(state, request.project_text, extraction_evidence)
            self.runtime_logger.log(
                "project_coach_pipeline",
                "rule_evaluation_completed",
                run_id=run_id,
                non_pass_rule_count=len([rule for rule in detected_rules if rule.status != RuleStatus.PASS]),
                high_risk_rule_count=len([rule for rule in detected_rules if rule.status == RuleStatus.HIGH_RISK]),
            )
            rubric_scores = self.rubric_scorer.score(state, detected_rules, extraction_evidence)

            top_rule = sorted(detected_rules, key=self.rule_engine.rank, reverse=True)[0]
            query = f"{top_rule.rule_id} {top_rule.message} {state.problem or ''} {state.customer_segment or ''}".strip()
            case_evidence = self.case_store.retrieve_cases(query, top_k=3) if self.case_store.has_cases() else []
            self.runtime_logger.log(
                "project_coach_pipeline",
                "case_retrieval_completed",
                run_id=run_id,
                top_rule=top_rule.rule_id,
                case_count=len(case_evidence),
                retrieval_query=preview_text(query),
            )
            structured_output, validation_report = self.coach_agent.generate(
                state=state,
                rules=detected_rules,
                extraction_evidence=extraction_evidence,
                case_evidence=case_evidence,
                project_text=request.project_text,
                fallback_task=self._fallback_task(top_rule.rule_id),
                run_id=run_id,
            )
            evidence_used = self._resolve_evidence(
                structured_output=structured_output,
                state=state,
                detected_rules=detected_rules,
                extraction_evidence=extraction_evidence,
                case_evidence=case_evidence,
            )
            rendered_views = self._render_views(
                structured_output,
                validation_report,
                detected_rules,
                case_evidence,
                rule_specs=self.rule_engine.rule_specs,
            )
            output = CoachOutput(
                current_diagnosis=structured_output.diagnosis_summary,
                evidence_used=evidence_used,
                impact=self._build_impact(structured_output.diagnosis_summary, case_evidence),
                next_task=structured_output.next_action,
                rubric_scores=rubric_scores,
                detected_rules=detected_rules,
                retrieved_case_evidence=case_evidence,
                structured_diagnosis=structured_output,
                constraint_validation=validation_report,
                rendered_views=rendered_views,
            )
            output.markdown_report = self.render_markdown(output)
            self._archive_run(request, state.model_dump(), output.model_dump(mode="json"))
            self.runtime_logger.log(
                "project_coach_pipeline",
                "request_completed",
                run_id=run_id,
                project_id=request.project_id,
                validation_passed=validation_report.passed,
                violation_count=len(validation_report.violations),
                non_pass_rule_count=len([rule for rule in detected_rules if rule.status != RuleStatus.PASS]),
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            return output
        except Exception as exc:
            self.runtime_logger.log_exception(
                "project_coach_pipeline",
                "request_failed",
                run_id=run_id,
                error=exc,
                user_id=request.user_id,
                project_id=request.project_id,
                duration_ms=round((perf_counter() - started_at) * 1000, 2),
            )
            raise

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
        rendered_views = output.rendered_views or RenderedViews(student="", teacher="", debug="")
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
            f"{rubric_lines}\n\n"
            "## Student View\n"
            f"{rendered_views.student}\n\n"
            "## Teacher View\n"
            f"{rendered_views.teacher}\n\n"
            "## Debug View\n"
            f"{rendered_views.debug}"
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

    @staticmethod
    def _render_views(
        structured_output: StructuredDiagnosis,
        validation_report: ConstraintValidationReport,
        detected_rules: list[RuleResult],
        case_evidence: list[EvidenceItem],
        rule_specs: dict[str, dict] | None = None,
    ) -> RenderedViews:
        student = (
            f"当前判断：{structured_output.diagnosis_summary}\n"
            f"下一步：{structured_output.next_action}"
        )
        risk_rules = [rule for rule in detected_rules if rule.status != RuleStatus.PASS]
        teacher = (
            f"风险等级：{structured_output.risk_level.value}；触发规则：{', '.join(structured_output.triggered_rules)}。\n"
            f"非通过规则数量：{len(risk_rules)}；建议优先跟进 {structured_output.triggered_rules[0] if structured_output.triggered_rules else 'H1'}。"
        )
        trace = build_pressure_trace(
            detected_rules=detected_rules,
            rule_specs=rule_specs or {},
            case_evidence=case_evidence,
        )
        trace.update(
            {
                "validation_passed": validation_report.passed,
                "violations": len(validation_report.violations),
                "rewrite_attempted": validation_report.rewrite_attempted,
            }
        )
        debug = pressure_trace_to_text(trace)
        return RenderedViews(student=student, teacher=teacher, debug=debug)

    @staticmethod
    def _resolve_evidence(
        *,
        structured_output: StructuredDiagnosis,
        state: ProjectState,
        detected_rules: list[RuleResult],
        extraction_evidence: list[EvidenceItem],
        case_evidence: list[EvidenceItem],
    ) -> list[EvidenceItem]:
        extraction_map = {item.field: item for item in extraction_evidence if item.field}
        rule_map = {rule.rule_id: rule for rule in detected_rules}
        case_doc_map = {item.doc_id: item for item in case_evidence if item.doc_id}
        case_chunk_map = {item.chunk_id: item for item in case_evidence if item.chunk_id}
        resolved: list[EvidenceItem] = []

        for claim in structured_output.claims:
            for ref in claim.evidence_refs:
                if ref.startswith("input:"):
                    field = ref.split(":", 1)[1]
                    if field in extraction_map:
                        resolved.append(extraction_map[field])
                        continue
                    value = getattr(state, field, None)
                    if value not in (None, "", [], {}):
                        resolved.append(
                            EvidenceItem(
                                source=EvidenceSource.USER_INPUT,
                                quote=f"{field}: {value}",
                                field=field,
                            )
                        )
                elif ref.startswith("rule:"):
                    rule_id = ref.split(":", 1)[1]
                    rule = rule_map.get(rule_id)
                    if rule:
                        if rule.evidence:
                            resolved.extend(rule.evidence)
                        else:
                            resolved.append(
                                EvidenceItem(
                                    source=EvidenceSource.RULE_RESULT,
                                    quote=f"{rule.rule_id}: {rule.message}",
                                    field="rule_assessment",
                                )
                            )
                elif ref.startswith("case:"):
                    case_id = ref.split(":", 1)[1]
                    if case_id in case_doc_map:
                        resolved.append(case_doc_map[case_id])
                elif ref.startswith("case_chunk:"):
                    chunk_id = ref.split(":", 1)[1]
                    if chunk_id in case_chunk_map:
                        resolved.append(case_chunk_map[chunk_id])

        if not resolved:
            resolved = extraction_evidence[:2] + case_evidence[:1]
        return dedupe_evidence(resolved)
