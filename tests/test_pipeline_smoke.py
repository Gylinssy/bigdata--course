import json
from pathlib import Path

from core.extractor import ProjectExtractor
from core.models import ProjectCoachRequest
from core.pipeline import ProjectCoachPipeline
from core.retrieval.case_store import CaseStore
from core.retrieval.vector_store import SimpleVectorStore


def build_case_store(tmp_path: Path) -> CaseStore:
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


class DummyOfflineClient:
    available = False
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"


class DummyRefiningClient:
    available = True
    default_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"

    def chat_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, str]:  # noqa: ARG002
        return {
            "tam": "中国农业总产值10万亿",
            "sam": "5万亿",
            "som": "1万亿",
            "ltv": "极高",
            "cac": "几乎为0",
        }


def test_pipeline_returns_next_task_and_evidence(tmp_path: Path):
    case_store = build_case_store(tmp_path)
    pipeline = ProjectCoachPipeline(case_store=case_store, archive_dir=tmp_path / "archive")
    request = ProjectCoachRequest(
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

    output = pipeline.run(request)

    assert output.next_task
    assert output.evidence_used
    assert output.current_diagnosis
    assert output.structured_diagnosis is not None
    assert output.constraint_validation is not None
    assert output.constraint_validation.passed is True
    assert output.score_summary is not None
    assert output.score_summary.weighted_final_score > 0


def test_pipeline_handles_non_numeric_llm_refinement_without_crashing(tmp_path: Path):
    case_store = build_case_store(tmp_path)
    extractor = ProjectExtractor(llm_client=DummyRefiningClient())
    pipeline = ProjectCoachPipeline(extractor=extractor, case_store=case_store, archive_dir=tmp_path / "archive")
    pipeline.coach_agent.llm_client = DummyOfflineClient()
    request = ProjectCoachRequest(
        user_id="u1",
        project_id="d001",
        project_text=(
            "项目名称：农田无人机服务\n"
            "问题：农民缺少低成本植保手段。\n"
            "客户：农业合作社和种植户。\n"
            "价值主张：通过无人机提升喷洒效率。\n"
            "渠道：线下合作社推广。\n"
            "收入模式：按亩收费。\n"
            "市场规模：TAM=中国农业总产值10万亿，SAM=5万亿，SOM=1万亿。\n"
            "单位经济：CAC几乎为0，LTV极高。\n"
        ),
    )

    output = pipeline.run(request)

    h4 = next(rule for rule in output.detected_rules if rule.rule_id == "H4")
    h8 = next(rule for rule in output.detected_rules if rule.rule_id == "H8")

    assert output.current_diagnosis
    assert h4.status.value == "pass"
    assert h8.status.value in {"warning", "fail"}
