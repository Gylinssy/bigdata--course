from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MOCK_TEACHER_RECORDS = [
    {
        "project_id": "mock-campus-ai",
        "user_id": "student",
        "current_diagnosis": "H11：项目涉及学生敏感场景，但合规说明不足。",
        "next_task": "补充数据授权、风险边界和试点伦理说明。",
        "rule_statuses": {"H11": "high_risk", "H9": "warning", "H12": "warning"},
        "rubric_scores": [
            {"rubric_id": "R1", "name": "Problem Clarity", "score": 4, "rationale": "问题定义较清晰。"},
            {"rubric_id": "R2", "name": "User-Channel Fit", "score": 3, "rationale": "渠道与人群匹配度一般。"},
            {"rubric_id": "R3", "name": "Value Proposition Fit", "score": 3, "rationale": "价值链路基本完整。"},
            {"rubric_id": "R4", "name": "Competition & Moat", "score": 2, "rationale": "竞品防御策略不足。"},
            {"rubric_id": "R5", "name": "Business Model", "score": 3, "rationale": "商业闭环有待细化。"},
            {"rubric_id": "R6", "name": "Unit Economics", "score": 2, "rationale": "单位经济偏弱。"},
            {"rubric_id": "R7", "name": "Execution Plan", "score": 3, "rationale": "里程碑可执行性一般。"},
            {"rubric_id": "R8", "name": "Compliance & Ethics", "score": 1, "rationale": "敏感数据合规说明不足。"},
            {"rubric_id": "R9", "name": "Evidence Quality", "score": 2, "rationale": "证据链不完整。"},
            {"rubric_id": "R10", "name": "Growth Feasibility", "score": 3, "rationale": "增长目标尚可但需验证。"},
        ],
    },
    {
        "project_id": "mock-health-assistant",
        "user_id": "student",
        "current_diagnosis": "H8：LTV/CAC 偏低，商业模型尚未闭环。",
        "next_task": "重算 CAC 并补齐转化漏斗数据。",
        "rule_statuses": {"H8": "fail", "H10": "warning"},
        "rubric_scores": [
            {"rubric_id": "R1", "name": "Problem Clarity", "score": 4, "rationale": "问题描述较完整。"},
            {"rubric_id": "R2", "name": "User-Channel Fit", "score": 4, "rationale": "渠道策略较清楚。"},
            {"rubric_id": "R3", "name": "Value Proposition Fit", "score": 4, "rationale": "价值主张清楚。"},
            {"rubric_id": "R4", "name": "Competition & Moat", "score": 3, "rationale": "竞品对比需要更深入。"},
            {"rubric_id": "R5", "name": "Business Model", "score": 3, "rationale": "收入路径有待补证据。"},
            {"rubric_id": "R6", "name": "Unit Economics", "score": 2, "rationale": "经济模型不稳定。"},
            {"rubric_id": "R7", "name": "Execution Plan", "score": 3, "rationale": "执行计划仍需细化。"},
            {"rubric_id": "R8", "name": "Compliance & Ethics", "score": 3, "rationale": "风险说明不完整。"},
            {"rubric_id": "R9", "name": "Evidence Quality", "score": 2, "rationale": "证据颗粒度不足。"},
            {"rubric_id": "R10", "name": "Growth Feasibility", "score": 3, "rationale": "增长节奏需要保守估计。"},
        ],
    },
]


def load_project_records(archive_dir: Path | str = Path("outputs/projects")) -> list[dict]:
    records: list[dict] = []
    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return records

    for path in sorted(archive_path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        request = payload.get("request", {}) if isinstance(payload, dict) else {}
        output = payload.get("output", {}) if isinstance(payload, dict) else {}
        records.append(
            {
                "project_id": request.get("project_id") or request.get("user_id") or path.stem,
                "user_id": request.get("user_id") or "unknown",
                "current_diagnosis": output.get("current_diagnosis") or "暂无诊断",
                "next_task": output.get("next_task") or "暂无下一步建议",
                "rule_statuses": {
                    item.get("rule_id", "unknown"): item.get("status", "pass")
                    for item in output.get("detected_rules", [])
                    if isinstance(item, dict)
                },
                "rubric_scores": [
                    {
                        "rubric_id": item.get("rubric_id", "unknown"),
                        "name": item.get("name", item.get("rubric_id", "unknown")),
                        "score": int(item.get("score", 0) or 0),
                        "rationale": item.get("rationale", ""),
                    }
                    for item in output.get("rubric_scores", [])
                    if isinstance(item, dict)
                ],
            }
        )
    return records


def load_records_or_mock(archive_dir: Path | str = Path("outputs/projects")) -> tuple[list[dict], bool]:
    records = load_project_records(archive_dir)
    if records:
        return records, False
    return MOCK_TEACHER_RECORDS, True


def average_rubric_scores(records: list[dict]) -> list[dict]:
    totals: dict[str, dict[str, float | str | int]] = {}
    for record in records:
        for item in record.get("rubric_scores", []):
            name = item["name"]
            if name not in totals:
                totals[name] = {"name": name, "sum": 0.0, "count": 0}
            totals[name]["sum"] += float(item["score"])
            totals[name]["count"] += 1

    rows = []
    for name, item in totals.items():
        count = int(item["count"])
        avg = float(item["sum"]) / count if count else 0.0
        rows.append({"name": name, "average_score": round(avg, 2)})
    return sorted(rows, key=lambda row: row["name"])


def top_rule_counts(records: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    for record in records:
        for rule_id, status in record.get("rule_statuses", {}).items():
            if status != "pass":
                counts[rule_id] = counts.get(rule_id, 0) + 1
    return sorted(
        [{"rule_id": rule_id, "count": count} for rule_id, count in counts.items()],
        key=lambda row: row["count"],
        reverse=True,
    )


def high_risk_projects(records: list[dict]) -> list[str]:
    risky = []
    for record in records:
        if any(status == "high_risk" for status in record.get("rule_statuses", {}).values()):
            risky.append(record["project_id"])
    return risky


def average_score_value(records: list[dict]) -> float:
    scores = [item["score"] for record in records for item in record.get("rubric_scores", [])]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 2)


def build_admin_metrics(records: list[dict], auth_users: list[dict[str, str]]) -> dict[str, Any]:
    role_counts: dict[str, int] = {}
    for user in auth_users:
        role = user.get("role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1

    return {
        "total_users": len(auth_users),
        "role_counts": role_counts,
        "total_projects": len(records),
        "high_risk_count": len(high_risk_projects(records)),
        "top_rules": top_rule_counts(records)[:3],
    }
