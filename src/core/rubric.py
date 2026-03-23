from __future__ import annotations

from pathlib import Path

import yaml

from .models import EvidenceItem, ProjectState, RubricScore, RuleResult, RuleStatus


RUBRIC_RULE_MAP: dict[str, list[str]] = {
    "R1": ["H2", "H9", "H17"],
    "R2": ["H1", "H16"],
    "R3": ["H2", "H17"],
    "R4": ["H12", "H18"],
    "R5": ["H5", "H19"],
    "R6": ["H8", "H20"],
    "R7": ["H10", "H15", "H23"],
    "R8": ["H11", "H21"],
    "R9": ["H9", "H22"],
    "R10": ["H13", "H14", "H23"],
}

RUBRIC_FIELD_MAP: dict[str, list[str]] = {
    "R1": ["problem", "customer_segment", "validation_evidence"],
    "R2": ["customer_segment", "channel", "validation_evidence"],
    "R3": ["problem", "value_proposition"],
    "R4": ["competitive_advantage", "customer_segment"],
    "R5": ["revenue_model", "payer", "cost_structure"],
    "R6": ["ltv", "cac", "cost_structure"],
    "R7": ["execution_plan", "pilot_plan", "traction"],
    "R8": ["compliance_notes", "value_proposition"],
    "R9": ["validation_evidence", "traction"],
    "R10": ["growth_target", "som", "execution_plan"],
}

RUBRIC_RATIONALE: dict[str, str] = {
    "R1": "问题定义与用户画像越清晰，越容易形成有效验证闭环。",
    "R2": "渠道和人群匹配决定获客效率与预算利用率。",
    "R3": "价值主张必须直接映射痛点，且具备可量化改善目标。",
    "R4": "竞争认知与护城河建设决定项目长期防御能力。",
    "R5": "收入结构与付费角色需要形成可解释的商业闭环。",
    "R6": "单位经济与成本覆盖能力决定项目是否可持续。",
    "R7": "执行与试点计划需要与团队资源规模相匹配。",
    "R8": "敏感场景中的合规和伦理边界决定项目上线风险。",
    "R9": "核心结论必须由可追溯证据支撑，避免主观幻觉。",
    "R10": "增长目标必须与市场空间、节奏与资源约束一致。",
}


class RubricScorer:
    def __init__(self, rubric_path: Path | str = Path("data/rubric.yaml")) -> None:
        self.rubrics = yaml.safe_load(Path(rubric_path).read_text(encoding="utf-8"))["rubrics"]

    def score(
        self,
        state: ProjectState,
        rules: list[RuleResult],
        evidence: list[EvidenceItem],
    ) -> list[RubricScore]:
        rule_map = {rule.rule_id: rule for rule in rules}
        evidence_map = {item.field: item for item in evidence if item.field}

        scores: list[RubricScore] = []
        for rubric in self.rubrics:
            rubric_id = rubric["rubric_id"]
            related_rules = RUBRIC_RULE_MAP.get(rubric_id, [])
            base = self._base_score_for_rubric(rubric_id, state)
            score = self._compose_score(rule_map, related_rules, base=base)
            fields = RUBRIC_FIELD_MAP.get(rubric_id, [])
            scores.append(
                RubricScore(
                    rubric_id=rubric_id,
                    name=rubric["name"],
                    score=score,
                    rationale=RUBRIC_RATIONALE.get(rubric_id, rubric.get("description", "")),
                    evidence=self._collect_rubric_evidence(rule_map, evidence_map, related_rules, fields),
                )
            )
        return scores

    @staticmethod
    def _base_score_for_rubric(rubric_id: str, state: ProjectState) -> int:
        if rubric_id == "R1":
            return RubricScorer._presence_score(state.problem, state.customer_segment)
        if rubric_id in {"R6", "R10"}:
            return 3
        return 4

    @staticmethod
    def _presence_score(*values: str | None) -> int:
        count = sum(1 for value in values if value)
        return {0: 1, 1: 3, 2: 4}.get(count, 4)

    @staticmethod
    def _filter_evidence(evidence_map: dict[str, EvidenceItem], fields: list[str]) -> list[EvidenceItem]:
        return [evidence_map[field] for field in fields if field in evidence_map]

    def _compose_score(self, rule_map: dict[str, RuleResult], rule_ids: list[str], base: int = 4) -> int:
        score = base
        for rule_id in rule_ids:
            rule = rule_map.get(rule_id)
            if not rule:
                continue
            score = min(score, self._status_score(rule.status))
        return max(1, min(score, 5))

    @staticmethod
    def _status_score(status: RuleStatus) -> int:
        if status == RuleStatus.HIGH_RISK:
            return 1
        if status == RuleStatus.FAIL:
            return 2
        if status == RuleStatus.WARNING:
            return 3
        return 4

    def _collect_rubric_evidence(
        self,
        rule_map: dict[str, RuleResult],
        evidence_map: dict[str, EvidenceItem],
        rule_ids: list[str],
        fields: list[str],
    ) -> list[EvidenceItem]:
        combined: list[EvidenceItem] = []
        for rule_id in rule_ids:
            rule = rule_map.get(rule_id)
            if rule:
                combined.extend(rule.evidence)
        combined.extend(self._filter_evidence(evidence_map, fields))

        deduped: list[EvidenceItem] = []
        seen: set[tuple[str, str | None, int | None, str | None]] = set()
        for item in combined:
            key = (item.quote, item.doc_id, item.page_no, item.field)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
