import json
from pathlib import Path

from core.chat_agent import ConversationAgent
from core.extractor import ProjectExtractor
from core.learning_agent import LearningTutorAgent
from core.models import ChatMessage, ProjectCoachRequest
from core.pipeline import ProjectCoachPipeline
from core.retrieval.case_store import CaseStore
from core.retrieval.vector_store import SimpleVectorStore
from core.runtime_log import RuntimeLogger


class DummyOfflineClient:
    available = False
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"


class DummyOnlineClient:
    available = True
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"

    def chat_text(self, *, system_prompt: str, user_prompt: str, model: str, temperature: float) -> str:  # noqa: ARG002
        return "ok"


def build_case_store(tmp_path: Path) -> CaseStore:
    tmp_path.mkdir(parents=True, exist_ok=True)
    chunks_path = tmp_path / "chunks.jsonl"
    records = [
        {
            "chunk_id": "case-a-p1-c1",
            "doc_id": "case-a",
            "page_no": 1,
            "text": "A student mental health startup added a compliance memo before pilot.",
            "start_char": 0,
            "end_char": 70,
        }
    ]
    chunks_path.write_text("\n".join(json.dumps(record, ensure_ascii=False) for record in records), encoding="utf-8")
    SimpleVectorStore(tmp_path / "index").build(records)
    return CaseStore(chunks_path=chunks_path, index_dir=tmp_path / "index")


def test_runtime_logger_writes_and_reads_events(tmp_path: Path):
    logger = RuntimeLogger(tmp_path)

    logger.log("test-agent", "started", run_id="run-1", value=1)
    logger.log("test-agent", "completed", run_id="run-1", level="WARN", ok=False)

    records = logger.read_recent(limit=10)

    assert [item["event"] for item in records] == ["started", "completed"]
    assert logger.log_path.exists()


def test_conversation_agent_writes_runtime_events(tmp_path: Path):
    logger = RuntimeLogger(tmp_path)
    agent = ConversationAgent(llm_client=DummyOnlineClient(), runtime_logger=logger)

    agent.chat([ChatMessage(role="user", content="Please analyze the user's main pain point.")])

    events = [item["event"] for item in logger.read_recent(limit=10)]
    assert "request_started" in events
    assert "llm_request_started" in events
    assert "llm_request_completed" in events
    assert "request_completed" in events


def test_learning_agent_writes_runtime_events(tmp_path: Path):
    logger = RuntimeLogger(tmp_path)
    agent = LearningTutorAgent(llm_client=DummyOfflineClient(), runtime_logger=logger)

    agent.respond("什么是 TAM/SAM/SOM？", include_project_context=False)

    events = [item["event"] for item in logger.read_recent(limit=10)]
    assert "request_started" in events
    assert "knowledge_retrieval_completed" in events
    assert "request_completed" in events


def test_project_coach_pipeline_writes_runtime_events(tmp_path: Path):
    logger = RuntimeLogger(tmp_path / "logs")
    extractor = ProjectExtractor(llm_client=DummyOfflineClient(), runtime_logger=logger)
    pipeline = ProjectCoachPipeline(
        extractor=extractor,
        case_store=build_case_store(tmp_path / "cases"),
        archive_dir=tmp_path / "archive",
        runtime_logger=logger,
    )
    pipeline.coach_agent.llm_client = DummyOfflineClient()

    pipeline.run(
        ProjectCoachRequest(
            user_id="u1",
            project_id="p1",
            project_text=(
                "项目名称：护苗AI\n"
                "问题：为中学生提供心理健康筛查和干预建议。\n"
                "客户：学校老师和家长。\n"
                "价值主张：用问卷和随访提早发现高风险学生。\n"
                "渠道：抖音投流获客。\n"
                "收入模式：按学校订阅收费。\n"
                "市场规模：TAM 10000 SAM 5000 SOM 1000\n"
                "单位经济：LTV 500 CAC 300\n"
            ),
        )
    )

    events = [item["event"] for item in logger.read_recent(limit=20)]
    assert "request_started" in events
    assert "extraction_completed" in events
    assert "rule_evaluation_completed" in events
    assert "case_retrieval_completed" in events
    assert "request_completed" in events
