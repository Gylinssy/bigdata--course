from __future__ import annotations

from fastapi import APIRouter

from core.chat_agent import ConversationAgent
from core.finance_agent import FinanceAgent
from core.idea_agent import IdeaCoachAgent
from core.learning_agent import LearningTutorAgent
from core.models import (
    ChatRequest,
    FinanceAnalysisRequest,
    IdeaCoachRequest,
    IngestRequest,
    LearningTutorRequest,
    ProjectCoachRequest,
    TeacherDashboard,
)
from core.ocr.ingest import ingest_directory
from core.pipeline import ProjectCoachPipeline


router = APIRouter()
pipeline = ProjectCoachPipeline()
conversation_agent = ConversationAgent()
idea_coach_agent = IdeaCoachAgent()
learning_tutor_agent = LearningTutorAgent()
finance_agent = FinanceAgent()


@router.post("/chat/project_coach")
def project_coach(request: ProjectCoachRequest):
    return pipeline.run(request)


@router.post("/chat/conversation")
def chat_conversation(request: ChatRequest):
    return conversation_agent.chat(
        request.messages,
        mode=request.mode,
        user_id=request.user_id,
        include_project_context=request.include_project_context,
        project_id=request.project_id,
    )


@router.post("/chat/idea_coach")
def chat_idea_coach(request: IdeaCoachRequest):
    if request.workspace is None:
        return idea_coach_agent.bootstrap(request.latest_input)
    return idea_coach_agent.step(request.workspace, request.latest_input)


@router.post("/chat/learning_tutor")
def chat_learning_tutor(request: LearningTutorRequest):
    return learning_tutor_agent.respond(
        request.question,
        user_id=request.user_id,
        project_id=request.project_id,
        include_project_context=request.include_project_context,
    )


@router.post("/analysis/finance")
def analyze_finance(request: FinanceAnalysisRequest):
    return finance_agent.analyze(request)


@router.post("/cases/ingest")
def ingest_cases(request: IngestRequest):
    stats = ingest_directory(request.input_dir, request.output_dir, backend_name=request.backend)
    return {
        "documents": stats.documents,
        "pages": stats.pages,
        "chunks": stats.chunks,
        "backend": stats.backend,
    }


@router.get("/dashboard/teacher", response_model=TeacherDashboard)
def teacher_dashboard(class_id: str | None = None):  # noqa: ARG001
    return pipeline.teacher_dashboard()
