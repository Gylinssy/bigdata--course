from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from core.scoring import build_unified_score_output


MOCK_TEACHER_RECORDS = [
    {
        "project_id": "mock-campus-ai",
        "user_id": "student",
        "current_diagnosis": "H11：项目涉及学生敏感场景，但合规说明不足。",
        "next_task": "补充数据授权、风险边界和试点伦理说明。",
        "rule_statuses": {"H11": "high_risk", "H9": "warning", "H12": "warning"},
        "detected_rules": [
            {"rule_id": "H11", "status": "high_risk", "message": "敏感场景缺少合规说明。"},
            {"rule_id": "H9", "status": "warning", "message": "验证证据偏弱。"},
            {"rule_id": "H12", "status": "warning", "message": "竞争壁垒证据不足。"},
        ],
        "rubric_scores": [
            {"rubric_id": "R1", "name": "Problem Clarity", "score": 4, "rationale": "问题定义较清晰。", "evidence": []},
            {"rubric_id": "R2", "name": "User-Channel Fit", "score": 3, "rationale": "渠道与人群匹配度一般。", "evidence": []},
            {"rubric_id": "R4", "name": "Competition & Moat", "score": 2, "rationale": "竞争壁垒证据较弱。", "evidence": []},
            {"rubric_id": "R8", "name": "Compliance & Ethics", "score": 1, "rationale": "合规说明严重不足。", "evidence": []},
            {"rubric_id": "R9", "name": "Evidence Quality", "score": 2, "rationale": "证据链不完整。", "evidence": []},
        ],
        "evidence_used": [],
    },
    {
        "project_id": "mock-health-assistant",
        "user_id": "student",
        "current_diagnosis": "H8：LTV/CAC 偏低，商业模型尚未闭环。",
        "next_task": "重算 CAC 并补齐转化漏斗数据。",
        "rule_statuses": {"H8": "fail", "H10": "warning"},
        "detected_rules": [
            {"rule_id": "H8", "status": "fail", "message": "单位经济不足。"},
            {"rule_id": "H10", "status": "warning", "message": "执行计划偏弱。"},
        ],
        "rubric_scores": [
            {"rubric_id": "R1", "name": "Problem Clarity", "score": 4, "rationale": "问题描述较完整。", "evidence": []},
            {"rubric_id": "R2", "name": "User-Channel Fit", "score": 4, "rationale": "渠道策略较清楚。", "evidence": []},
            {"rubric_id": "R6", "name": "Unit Economics", "score": 2, "rationale": "单位经济模型不稳定。", "evidence": []},
            {"rubric_id": "R7", "name": "Execution Plan", "score": 3, "rationale": "执行计划仍需细化。", "evidence": []},
            {"rubric_id": "R9", "name": "Evidence Quality", "score": 2, "rationale": "证据颗粒度不足。", "evidence": []},
        ],
        "evidence_used": [],
    },
]


def load_project_records(archive_dir: Path | str = Path("outputs/projects")) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    archive_path = Path(archive_dir)
    if not archive_path.exists():
        return records

    rubric_meta_map = _load_rubric_meta_map()
    for path in sorted(archive_path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        request = payload.get("request", {}) if isinstance(payload, dict) else {}
        output = payload.get("output", {}) if isinstance(payload, dict) else {}
        record = {
            "project_id": request.get("project_id") or request.get("user_id") or path.stem,
            "user_id": request.get("user_id") or "unknown",
            "current_diagnosis": output.get("current_diagnosis") or "暂无诊断",
            "next_task": output.get("next_task") or "暂无下一步建议",
            "rule_statuses": {
                item.get("rule_id", "unknown"): item.get("status", "pass")
                for item in output.get("detected_rules", [])
                if isinstance(item, dict)
            },
            "detected_rules": [
                item
                for item in output.get("detected_rules", [])
                if isinstance(item, dict)
            ],
            "rubric_scores": [
                {
                    "rubric_id": item.get("rubric_id", "unknown"),
                    "name": item.get("name", item.get("rubric_id", "unknown")),
                    "score": int(item.get("score", 0) or 0),
                    "rationale": item.get("rationale", ""),
                    "evidence": item.get("evidence", []),
                }
                for item in output.get("rubric_scores", [])
                if isinstance(item, dict)
            ],
            "evidence_used": [
                item
                for item in output.get("evidence_used", [])
                if isinstance(item, dict)
            ],
            "score_summary": output.get("score_summary"),
        }
        records.append(_enrich_record(record, rubric_meta_map=rubric_meta_map))
    return records


def load_records_or_mock(archive_dir: Path | str = Path("outputs/projects")) -> tuple[list[dict[str, Any]], bool]:
    records = load_project_records(archive_dir)
    if records:
        return records, False
    rubric_meta_map = _load_rubric_meta_map()
    return [_enrich_record(record, rubric_meta_map=rubric_meta_map) for record in MOCK_TEACHER_RECORDS], True


def average_rubric_scores(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, float | int]] = {}
    for record in records:
        for item in record.get("rubric_scores", []):
            name = str(item["name"])
            if name not in totals:
                totals[name] = {"sum": 0.0, "count": 0}
            totals[name]["sum"] += float(item["score"])
            totals[name]["count"] += 1

    rows = []
    for name, item in totals.items():
        count = int(item["count"])
        avg = float(item["sum"]) / count if count else 0.0
        rows.append({"name": name, "average_score": round(avg, 2)})
    return sorted(rows, key=lambda row: row["name"])


def top_rule_counts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in records:
        for rule_id, status in record.get("rule_statuses", {}).items():
            if status != "pass":
                counts[rule_id] += 1
    return sorted(
        [{"rule_id": rule_id, "count": count} for rule_id, count in counts.items()],
        key=lambda row: row["count"],
        reverse=True,
    )


def high_risk_projects(records: list[dict[str, Any]]) -> list[str]:
    return [
        str(record["project_id"])
        for record in records
        if any(status == "high_risk" for status in record.get("rule_statuses", {}).values())
    ]


def average_score_value(records: list[dict[str, Any]]) -> float:
    scores = [float(record.get("weighted_final_score", 0.0)) for record in records if record.get("weighted_final_score") is not None]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 2)


def build_teacher_dashboard_snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
    score_distribution: Counter[str] = Counter()
    stage_distribution: Counter[str] = Counter()
    weakest_dimensions: Counter[str] = Counter()
    low_score_hotspots: Counter[str] = Counter()
    rubric_average_scores = average_rubric_scores(records)

    stage_rollups: dict[str, dict[str, Any]] = {}
    for record in records:
        score_distribution[str(record.get("score_band", "stable"))] += 1
        stage_distribution[str(record.get("stage_label", "未知阶段"))] += 1
        weakest_dimensions.update(record.get("weakest_dimensions", [])[:2])

        stage_key = str(record.get("stage_key", "idea"))
        bucket = stage_rollups.setdefault(
            stage_key,
            {
                "stage_key": stage_key,
                "stage_label": str(record.get("stage_label", "未知阶段")),
                "project_count": 0,
                "average_score": 0.0,
                "high_risk_count": 0,
                "top_rule_counter": Counter(),
            },
        )
        bucket["project_count"] += 1
        bucket["average_score"] += float(record.get("weighted_final_score", 0.0))
        bucket["high_risk_count"] += int(record.get("high_risk", False))
        bucket["top_rule_counter"].update(record.get("top_rules", []))

        for item in record.get("score_dimensions", []):
            if float(item.get("score", 0.0)) <= 2.0:
                low_score_hotspots[str(item.get("name", "unknown"))] += 1

    stage_insights = []
    for item in stage_rollups.values():
        count = int(item["project_count"])
        stage_insights.append(
            {
                "stage_key": item["stage_key"],
                "stage_label": item["stage_label"],
                "project_count": count,
                "average_score": round(float(item["average_score"]) / count, 2) if count else 0.0,
                "high_risk_count": int(item["high_risk_count"]),
                "top_rules": [rule_id for rule_id, _ in item["top_rule_counter"].most_common(3)],
            }
        )
    stage_insights.sort(key=lambda row: (row["average_score"], -row["project_count"]))

    project_rankings = sorted(
        [
            {
                "project_id": record["project_id"],
                "user_id": record["user_id"],
                "stage_label": record.get("stage_label", "未知阶段"),
                "weighted_final_score": record.get("weighted_final_score", 0.0),
                "high_risk": record.get("high_risk", False),
                "top_rules": record.get("top_rules", []),
                "weakest_dimensions": record.get("weakest_dimensions", []),
            }
            for record in records
        ],
        key=lambda row: (not row["high_risk"], row["weighted_final_score"], row["project_id"]),
    )

    suggestions: list[str] = []
    top_rules = top_rule_counts(records)
    if top_rules:
        suggestions.append(f"优先讲解 {top_rules[0]['rule_id']} 对应的证据与修复路径。")
    if weakest_dimensions:
        dimension_name, _ = weakest_dimensions.most_common(1)[0]
        suggestions.append(f"{dimension_name} 是当前统一评分里最常见的薄弱维度，建议做专项讲评。")
    if stage_insights:
        suggestions.append(f"{stage_insights[0]['stage_label']} 是当前最薄弱阶段，适合按阶段子图组织课堂复盘。")

    return {
        "average_score": average_score_value(records),
        "score_distribution": dict(score_distribution),
        "stage_distribution": dict(stage_distribution),
        "rubric_average_scores": rubric_average_scores,
        "low_score_hotspots": [{"name": name, "count": count} for name, count in low_score_hotspots.most_common(5)],
        "weakest_dimensions": [name for name, _ in weakest_dimensions.most_common(5)],
        "stage_insights": stage_insights,
        "project_rankings": project_rankings[:10],
        "intervention_suggestions": suggestions,
    }


def build_admin_metrics(records: list[dict[str, Any]], auth_users: list[dict[str, str]]) -> dict[str, Any]:
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


def _enrich_record(record: dict[str, Any], *, rubric_meta_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    score_summary = record.get("score_summary")
    if not isinstance(score_summary, dict):
        score_summary = build_unified_score_output(
            record.get("rubric_scores", []),
            rules=record.get("detected_rules", []),
            rubric_meta_map=rubric_meta_map,
        ).model_dump(mode="json")

    detected_rules = record.get("detected_rules", [])
    sorted_rules = [
        item.get("rule_id", "unknown")
        for item in detected_rules
        if isinstance(item, dict) and item.get("status") != "pass"
    ][:3]

    enriched = dict(record)
    enriched["score_summary"] = score_summary
    enriched["weighted_final_score"] = float(score_summary.get("weighted_final_score", 0.0))
    enriched["average_score"] = float(score_summary.get("average_score", 0.0))
    enriched["score_band"] = str(score_summary.get("score_band", "stable"))
    enriched["stage_key"] = str(score_summary.get("stage_key", "idea"))
    enriched["stage_label"] = str(score_summary.get("stage_label", "未知阶段"))
    enriched["weakest_dimensions"] = list(score_summary.get("weakest_dimensions", []))
    enriched["strongest_dimensions"] = list(score_summary.get("strongest_dimensions", []))
    enriched["score_dimensions"] = list(score_summary.get("dimensions", []))
    enriched["high_risk"] = any(status == "high_risk" for status in enriched.get("rule_statuses", {}).values())
    enriched["top_rules"] = sorted_rules
    return enriched


def _load_rubric_meta_map() -> dict[str, dict[str, Any]]:
    rubric_path = Path("data/rubric.yaml")
    if not rubric_path.exists():
        return {}
    payload = yaml.safe_load(rubric_path.read_text(encoding="utf-8")) or {}
    rubrics = payload.get("rubrics", []) if isinstance(payload, dict) else []
    return {
        str(item.get("rubric_id")): item
        for item in rubrics
        if isinstance(item, dict) and item.get("rubric_id")
    }
