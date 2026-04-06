from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceSource(str, Enum):
    USER_INPUT = "user_input"
    EXTRACTED_FIELD = "extracted_field"
    RULE_RESULT = "rule_result"
    CASE_PDF = "case_pdf"


class RuleStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    HIGH_RISK = "high_risk"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DiagnosisRiskLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    HIGH_RISK = "high_risk"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    NEEDS_VALIDATION = "needs_validation"


class ProjectState(BaseModel):
    project_name: str | None = None
    problem: str | None = None
    customer_segment: str | None = None
    value_proposition: str | None = None
    channel: str | None = None
    revenue_model: str | None = None
    cost_structure: str | None = None
    traction: str | None = None
    tam: float | None = None
    sam: float | None = None
    som: float | None = None
    ltv: float | None = None
    cac: float | None = None
    compliance_notes: str | None = None
    payer: str | None = None
    validation_evidence: str | None = None
    execution_plan: str | None = None
    competitive_advantage: str | None = None
    retention_strategy: str | None = None
    growth_target: str | None = None
    pilot_plan: str | None = None


class EvidenceItem(BaseModel):
    source: EvidenceSource
    quote: str
    start: int | None = None
    end: int | None = None
    field: str | None = None
    doc_id: str | None = None
    page_no: int | None = None
    chunk_id: str | None = None


class RuleResult(BaseModel):
    rule_id: str
    status: RuleStatus
    severity: Severity
    message: str
    probing_question: str | None = None
    fix_task: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class RubricScore(BaseModel):
    rubric_id: str
    name: str
    score: int = Field(ge=1, le=5)
    rationale: str
    evidence: list[EvidenceItem] = Field(default_factory=list)


class StructuredClaim(BaseModel):
    field: str
    statement: str
    evidence_refs: list[str] = Field(default_factory=list)
    status: ClaimStatus = ClaimStatus.SUPPORTED


class StructuredDiagnosis(BaseModel):
    diagnosis_summary: str
    risk_level: DiagnosisRiskLevel
    triggered_rules: list[str] = Field(default_factory=list)
    next_action: str
    claims: list[StructuredClaim] = Field(default_factory=list)


class ConstraintViolation(BaseModel):
    code: str
    message: str


class ConstraintValidationReport(BaseModel):
    passed: bool
    violations: list[ConstraintViolation] = Field(default_factory=list)
    rewrite_attempted: bool = False


class RenderedViews(BaseModel):
    student: str
    teacher: str
    debug: str


class CoachOutput(BaseModel):
    current_diagnosis: str
    evidence_used: list[EvidenceItem]
    impact: str
    next_task: str
    rubric_scores: list[RubricScore]
    detected_rules: list[RuleResult]
    retrieved_case_evidence: list[EvidenceItem] = Field(default_factory=list)
    structured_diagnosis: StructuredDiagnosis | None = None
    constraint_validation: ConstraintValidationReport | None = None
    rendered_views: RenderedViews | None = None
    markdown_report: str | None = None


class ProjectCoachRequest(BaseModel):
    user_id: str
    project_text: str
    project_id: str | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    user_id: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    mode: Literal["general", "reasoning"] = "general"
    include_project_context: bool = False
    project_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    used_llm: bool
    context_used: bool = False
    context_project_id: str | None = None


class LearningMode(str, Enum):
    TUTOR = "tutor"
    ANTI_GHOSTWRITING = "anti_ghostwriting"
    EMOTIONAL_REDIRECT = "emotional_redirect"
    CLARIFICATION = "clarification"


class LearningConstraintViolation(BaseModel):
    code: str
    message: str


class LearningConstraintReport(BaseModel):
    passed: bool
    violations: list[LearningConstraintViolation] = Field(default_factory=list)


class LearningTutorOutput(BaseModel):
    mode: LearningMode
    topic: str
    answer_summary: str
    project_grounding: str
    common_mistakes: list[str] = Field(default_factory=list)
    practice_task: str
    expected_artifact: str
    follow_up_question: str
    retrieved_kg_nodes: list[str] = Field(default_factory=list)
    context_project_id: str | None = None


class LearningTutorRequest(BaseModel):
    question: str
    user_id: str | None = None
    project_id: str | None = None
    include_project_context: bool = True


class LearningTutorResponse(BaseModel):
    reply: str
    structured_output: LearningTutorOutput
    validation: LearningConstraintReport
    model: str
    used_llm: bool
    context_used: bool = False
    context_project_id: str | None = None


class IdeaWorkspace(BaseModel):
    seed_idea: str = ""
    answers: dict[str, str] = Field(default_factory=dict)
    pending_fields: list[str] = Field(default_factory=list)
    last_focus_rule: str | None = None
    turn_count: int = 0


class IdeaCoachOutput(BaseModel):
    stage_label: str
    overview: str
    focus_rule_id: str | None = None
    focus_rule_message: str = ""
    socratic_question: str
    answer_template: str
    next_action: str
    generated_project_text: str
    ready_for_generation: bool
    ready_for_diagnosis: bool
    completion_ratio: float = Field(ge=0.0, le=1.0)
    missing_core_fields: list[str] = Field(default_factory=list)
    detected_rules: list[RuleResult] = Field(default_factory=list)
    hypergraph_focus: dict[str, Any] = Field(default_factory=dict)
    draft_state: ProjectState


class IdeaCoachRequest(BaseModel):
    latest_input: str = ""
    workspace: IdeaWorkspace | None = None


class IdeaCoachResponse(BaseModel):
    reply: str
    structured_output: IdeaCoachOutput
    workspace: IdeaWorkspace
    model: str
    used_llm: bool


class IngestRequest(BaseModel):
    input_dir: str = "data/cases"
    output_dir: str = "outputs/cases"
    backend: Literal["auto", "deepseek_ocr", "tesseract", "pdf_text"] = "auto"


class TeacherDashboard(BaseModel):
    total_projects: int
    top_rule_triggers: dict[str, int]
    high_risk_projects: list[str]
    field_missing_hotspots: dict[str, int]
    intervention_suggestions: list[str]
