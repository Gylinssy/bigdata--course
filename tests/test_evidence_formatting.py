from core.evidence import format_evidence
from core.models import EvidenceItem, EvidenceSource


def test_format_evidence_accepts_model() -> None:
    item = EvidenceItem(source=EvidenceSource.EXTRACTED_FIELD, quote="目标客户是高中生", field="customer_segment")
    assert format_evidence(item) == "customer_segment: 目标客户是高中生"


def test_format_evidence_accepts_dict_payload() -> None:
    payload = {
        "source": "case_pdf",
        "quote": "先做合规评估",
        "doc_id": "case-01",
        "page_no": 3,
    }
    assert format_evidence(payload) == '[case: case-01 p.3] "先做合规评估"'
