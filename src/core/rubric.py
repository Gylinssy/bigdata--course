from __future__ import annotations

from pathlib import Path

import yaml

from .models import EvidenceItem, ProjectState, RubricScore, RuleResult, RuleStatus


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

        r1_score = self._compose_score(rule_map, ["H2", "H9"], base=self._presence_score(state.problem, state.customer_segment))
        r2_score = self._compose_score(rule_map, ["H1", "H5", "H12"], base=4)
        r3_score = self._compose_score(rule_map, ["H4", "H14"], base=4)
        r4_score = self._compose_score(rule_map, ["H8", "H13"], base=4)
        r5_score = self._compose_score(rule_map, ["H10", "H11", "H15"], base=4)

        return [
            RubricScore(
                rubric_id="R1",
                name=self._name("R1"),
                score=r1_score,
                rationale="问题定义清晰且有验证证据时，项目方向更可靠。",
                evidence=self._collect_rubric_evidence(rule_map, evidence_map, ["H2", "H9"], ["problem", "customer_segment", "validation_evidence"]),
            ),
            RubricScore(
                rubric_id="R2",
                name=self._name("R2"),
                score=r2_score,
                rationale="客户、渠道、付费链和竞争差异共同决定价值交付是否成立。",
                evidence=self._collect_rubric_evidence(rule_map, evidence_map, ["H1", "H5", "H12"], ["customer_segment", "value_proposition", "channel", "payer", "competitive_advantage"]),
            ),
            RubricScore(
                rubric_id="R3",
                name=self._name("R3"),
                score=r3_score,
                rationale="市场规模与增长目标必须同时可计算且相互一致。",
                evidence=self._collect_rubric_evidence(rule_map, evidence_map, ["H4", "H14"], ["tam", "sam", "som", "growth_target"]),
            ),
            RubricScore(
                rubric_id="R4",
                name=self._name("R4"),
                score=r4_score,
                rationale="单位经济与留存机制共同决定增长是否健康可持续。",
                evidence=self._collect_rubric_evidence(rule_map, evidence_map, ["H8", "H13"], ["ltv", "cac", "retention_strategy"]),
            ),
            RubricScore(
                rubric_id="R5",
                name=self._name("R5"),
                score=r5_score,
                rationale="执行路径、试点计划和合规准备度共同影响真实落地风险。",
                evidence=self._collect_rubric_evidence(rule_map, evidence_map, ["H10", "H11", "H15"], ["execution_plan", "pilot_plan", "compliance_notes"]),
            ),
        ]

    def _name(self, rubric_id: str) -> str:
        for rubric in self.rubrics:
            if rubric["rubric_id"] == rubric_id:
                return rubric["name"]
        return rubric_id

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
