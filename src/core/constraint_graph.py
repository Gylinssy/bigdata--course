from __future__ import annotations

import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .case_library import build_case_retrieval_text, load_structured_cases
from .project_stages import bucket_rule_stage, stage_display_name, stage_scope
from .pressure_trace import EDGE_TYPE_BY_RULE, FALLACY_BY_RULE, STRATEGY_BY_RULE, load_strategy_pool
from .rule_engine import RuleEngine

TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")

RULE_HINT_TERMS = {
    "H9": ["evidence", "interview", "survey", "experiment", "sample", "访谈", "问卷", "实验", "样本", "证据", "验证"],
    "H11": [
        "compliance",
        "consent",
        "authorization",
        "authorization_docs",
        "privacy",
        "ethics",
        "safety",
        "healthtech",
        "medtech",
        "edtech",
        "fintech",
        "sensitive",
        "minor",
        "minors",
        "health",
        "medical",
        "education",
        "finance",
        "合规",
        "授权",
        "隐私",
        "伦理",
        "敏感",
        "医疗",
        "教育",
        "金融",
        "未成年人",
        "风控",
    ],
    "H15": ["pilot", "poc", "场景试点", "试点", "首批", "验证场景"],
    "H21": [
        "license",
        "licensing",
        "copyright",
        "patent",
        "model",
        "dataset",
        "asset",
        "素材",
        "模型",
        "版权",
        "专利",
        "知识产权",
        "授权链",
        "许可",
    ],
    "H22": ["traceability", "benchmark", "bias", "sample", "evidence", "偏差", "样本量", "可追溯", "基准", "证据"],
    "H23": ["roadmap", "milestone", "budget", "resource", "team", "排期", "里程碑", "预算", "资源", "交付"],
}

DOMAIN_HINT_TERMS = {
    "healthtech": ["healthtech", "medtech", "medical", "health", "医疗", "临床", "患者"],
    "fintech": ["fintech", "finance", "banking", "金融", "风控", "信贷"],
    "edtech": ["edtech", "education", "student", "campus", "教育", "学生", "校园"],
    "agritech": ["agritech", "agriculture", "farm", "农业", "农田", "种植"],
}

FIELD_DISPLAY_NAMES = {
    "project_name": "项目名称",
    "problem": "问题",
    "customer_segment": "客户",
    "value_proposition": "价值主张",
    "channel": "渠道",
    "revenue_model": "收入模式",
    "cost_structure": "成本结构",
    "traction": "进展",
    "tam": "TAM",
    "sam": "SAM",
    "som": "SOM",
    "ltv": "LTV",
    "cac": "CAC",
    "compliance_notes": "合规说明",
    "payer": "付费方",
    "validation_evidence": "验证证据",
    "execution_plan": "执行计划",
    "competitive_advantage": "竞争优势",
    "retention_strategy": "留存机制",
    "growth_target": "增长目标",
    "pilot_plan": "试点计划",
}

REMEDIATION_FIELDS_BY_RULE = {
    "H1": ["customer_segment", "value_proposition", "channel"],
    "H2": ["problem", "value_proposition"],
    "H4": ["tam", "sam", "som"],
    "H5": ["customer_segment", "revenue_model", "payer"],
    "H8": ["ltv", "cac", "cost_structure"],
    "H9": ["validation_evidence"],
    "H10": ["execution_plan", "traction"],
    "H11": ["compliance_notes"],
    "H12": ["competitive_advantage"],
    "H13": ["retention_strategy"],
    "H14": ["growth_target"],
    "H15": ["pilot_plan"],
    "H16": ["customer_segment", "channel"],
    "H17": ["problem", "value_proposition", "validation_evidence"],
    "H18": ["competitive_advantage"],
    "H19": ["revenue_model", "cost_structure"],
    "H20": ["ltv", "cac", "cost_structure"],
    "H21": ["compliance_notes"],
    "H22": ["validation_evidence"],
    "H23": ["execution_plan", "pilot_plan"],
}

RULE_STAGE_HINTS = {
    "H1": "problem_validation",
    "H2": "problem_validation",
    "H4": "market_modeling",
    "H5": "business_model",
    "H8": "unit_economics",
    "H9": "evidence_validation",
    "H10": "execution_design",
    "H11": "risk_boundary",
    "H12": "competition_design",
    "H13": "retention_design",
    "H14": "growth_design",
    "H15": "pilot_design",
    "H16": "channel_design",
    "H17": "mvp_validation",
    "H18": "competition_design",
    "H19": "business_model",
    "H20": "unit_economics",
    "H21": "risk_boundary",
    "H22": "evidence_validation",
    "H23": "execution_design",
}


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in TOKEN_RE.findall(text):
        token = raw_token.lower()
        tokens.add(token)
        if "_" in token:
            tokens.update(part for part in token.split("_") if len(part) >= 2)
    return tokens


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def _load_yaml(path: Path | str) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def _hint_tokens(values: list[str]) -> set[str]:
    return _tokenize(" ".join(values))


def build_constraint_graph_payload(
    *,
    ontology_path: Path | str = Path("data/ontology.yaml"),
    rules_dir: Path | str = Path("data/hyper_rules"),
    strategies_path: Path | str = Path("data/interrogation_strategies.yaml"),
    cases_path: Path | str = Path("data/case_library/structured_cases.jsonl"),
) -> dict[str, Any]:
    ontology = _load_yaml(ontology_path)
    rule_engine = RuleEngine(rules_dir=rules_dir)
    strategy_pool = load_strategy_pool(strategies_path)
    cases = load_structured_cases(cases_path)

    nodes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def add_node(node_id: str, label: str, **properties: Any) -> None:
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"node_id": node_id, "label": label, "properties": properties})

    def add_relationship(start: str, rel_type: str, end: str, **properties: Any) -> None:
        relationships.append(
            {
                "start": start,
                "type": rel_type,
                "end": end,
                "properties": properties,
            }
        )

    for field in ontology.get("project_fields", []):
        add_node(
            f"field:{field}",
            "ProjectField",
            name=field,
            display_name=FIELD_DISPLAY_NAMES.get(field, field),
            source="ontology",
        )

    for domain in ontology.get("sensitive_domains", []):
        add_node(f"sensitive:{domain}", "SensitiveDomain", name=domain, source="ontology")

    for rule_id, spec in rule_engine.rule_specs.items():
        stage_hint = RULE_STAGE_HINTS.get(rule_id, "idea_refinement")
        edge_type = EDGE_TYPE_BY_RULE.get(rule_id, "ConstraintEdge")
        add_node(
            f"rule:{rule_id}",
            "ConstraintRule",
            rule_id=rule_id,
            severity=spec.get("severity", "medium"),
            trigger_message=spec.get("trigger_message", ""),
            probing_question=spec.get("probing_question", ""),
            fix_task=spec.get("fix_task", ""),
            edge_type=edge_type,
            fallacy_label=FALLACY_BY_RULE.get(rule_id, ""),
            stage_hint=stage_hint,
            source="hyper_rule",
        )
        add_node(f"edge:{edge_type}", "ConstraintEdgeType", name=edge_type, source="hyper_rule")
        add_relationship(f"rule:{rule_id}", "USES_EDGE_TYPE", f"edge:{edge_type}")

        for field in spec.get("required_fields", []):
            add_node(
                f"field:{field}",
                "ProjectField",
                name=field,
                display_name=FIELD_DISPLAY_NAMES.get(field, field),
                source="ontology",
            )
            add_relationship(f"rule:{rule_id}", "REQUIRES_FIELD", f"field:{field}")

        for field in REMEDIATION_FIELDS_BY_RULE.get(rule_id, []):
            add_node(
                f"field:{field}",
                "ProjectField",
                name=field,
                display_name=FIELD_DISPLAY_NAMES.get(field, field),
                source="ontology",
            )
            add_relationship(f"rule:{rule_id}", "REMEDIATES_WITH_FIELD", f"field:{field}")

        stage_id = f"stage:{stage_hint}"
        add_node(stage_id, "IdeaStage", name=stage_hint, source="graph_rule_stage")
        add_relationship(f"rule:{rule_id}", "CONSTRAINS_STAGE", stage_id)

        if rule_id in FALLACY_BY_RULE:
            fallacy_id = f"fallacy:{_slugify(FALLACY_BY_RULE[rule_id])}"
            add_node(fallacy_id, "FallacyPattern", name=FALLACY_BY_RULE[rule_id], source="pressure_trace")
            add_relationship(f"rule:{rule_id}", "FLAGS_FALLACY", fallacy_id)

    for strategy_id, strategy in strategy_pool.items():
        edge_type = str(strategy.get("edge_type", "ConstraintEdge"))
        add_node(
            f"strategy:{strategy_id}",
            "InterrogationStrategy",
            strategy_id=strategy_id,
            name=str(strategy.get("name", strategy_id)),
            generated_question=str(strategy.get("generated_question", "")),
            edge_type=edge_type,
            source="strategy_pool",
        )
        add_node(f"edge:{edge_type}", "ConstraintEdgeType", name=edge_type, source="hyper_rule")
        add_relationship(f"strategy:{strategy_id}", "OPERATES_ON_EDGE", f"edge:{edge_type}")
        for rule_id in strategy.get("applies_to_rules", []):
            add_relationship(f"strategy:{strategy_id}", "SUPPORTS_RULE", f"rule:{rule_id}")
            add_relationship(f"rule:{rule_id}", "USES_STRATEGY", f"strategy:{strategy_id}")

    rule_text_index = {}
    for rule_id, spec in rule_engine.rule_specs.items():
        tokens = _tokenize(
            " ".join(
                [
                    spec.get("trigger_message", ""),
                    spec.get("probing_question", ""),
                    spec.get("fix_task", ""),
                    " ".join(spec.get("required_fields", [])),
                    " ".join(REMEDIATION_FIELDS_BY_RULE.get(rule_id, [])),
                    FIELD_DISPLAY_NAMES.get(rule_id, ""),
                ]
            )
        )
        for field in spec.get("required_fields", []):
            tokens |= _tokenize(FIELD_DISPLAY_NAMES.get(field, field))
        for field in REMEDIATION_FIELDS_BY_RULE.get(rule_id, []):
            tokens |= _tokenize(FIELD_DISPLAY_NAMES.get(field, field))
        tokens |= _hint_tokens(RULE_HINT_TERMS.get(rule_id, []))
        strategy_id = STRATEGY_BY_RULE.get(rule_id)
        if strategy_id and strategy_id in strategy_pool:
            tokens |= _tokenize(
                " ".join(
                    [
                        str(strategy_pool[strategy_id].get("name", "")),
                        str(strategy_pool[strategy_id].get("generated_question", "")),
                    ]
                )
            )
        rule_text_index[rule_id] = tokens

    for record in cases:
        case_id = str(record.get("case_id", "")).strip()
        if not case_id:
            continue
        case_node_id = f"case:{case_id}"
        domain = str(record.get("domain", "unknown"))
        stage = str(record.get("stage", "unknown"))
        outcome = str(record.get("outcome", "unknown"))
        add_node(
            case_node_id,
            "Case",
            case_id=case_id,
            title=str(record.get("title", case_id)),
            domain=domain,
            stage=stage,
            outcome=outcome,
            source=str(record.get("source", "")),
            year=record.get("year"),
        )
        add_node(f"domain:{domain}", "CaseDomain", name=domain, source="case_library")
        add_node(f"stage_case:{stage}", "CaseStage", name=stage, source="case_library")
        add_node(f"outcome:{outcome}", "CaseOutcome", name=outcome, source="case_library")
        add_relationship(case_node_id, "IN_DOMAIN", f"domain:{domain}")
        add_relationship(case_node_id, "AT_STAGE", f"stage_case:{stage}")
        add_relationship(case_node_id, "HAS_OUTCOME", f"outcome:{outcome}")

        case_text = build_case_retrieval_text(record)
        case_tokens = _tokenize(case_text)
        case_tokens |= _hint_tokens(DOMAIN_HINT_TERMS.get(domain.lower(), []))
        scored_rules: list[tuple[str, int]] = []
        for rule_id, tokens in rule_text_index.items():
            score = len(case_tokens & tokens)
            if score >= 2:
                scored_rules.append((rule_id, score))
        scored_rules.sort(key=lambda item: item[1], reverse=True)
        for rule_id, score in scored_rules[:4]:
            rel_type = "SHOWS_RECOVERY_PATTERN" if outcome == "success" else "EXPOSES_RISK_PATTERN"
            add_relationship(case_node_id, rel_type, f"rule:{rule_id}", score=score)
            add_relationship(f"rule:{rule_id}", "REFERENCES_CASE", case_node_id, score=score, outcome=outcome)

    graph = {
        "graph_id": "a0_constraint_graph_v1",
        "description": "Constraint knowledge graph for idea agent, built from hyper rules, strategies, ontology, and case library.",
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
    }
    return graph


def export_constraint_graph(
    output_path: Path | str = Path("outputs/graphs/constraint_graph.json"),
    **kwargs: Any,
) -> dict[str, Any]:
    graph = build_constraint_graph_payload(**kwargs)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def export_constraint_graph_cypher(
    graph: dict[str, Any],
    output_path: Path | str = Path("outputs/graphs/neo4j/constraint_graph.cypher"),
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "// Generated constraint graph import for Neo4j",
        f"// graph_id={graph.get('graph_id', 'constraint_graph')}",
        f"MATCH (n {{graph_id: '{graph.get('graph_id', 'constraint_graph')}'}}) DETACH DELETE n;",
    ]

    for node in graph.get("nodes", []):
        label = str(node.get("label", "GraphEntity")).replace("`", "")
        props = dict(node.get("properties", {}))
        props["node_id"] = node["node_id"]
        props["graph_id"] = graph.get("graph_id")
        serialized = json.dumps(props, ensure_ascii=False)
        lines.append(
            f"MERGE (n:`{label}` {{node_id: '{node['node_id']}'}}) "
            f"SET n += {serialized};"
        )

    for rel in graph.get("relationships", []):
        rel_type = str(rel.get("type", "RELATED_TO")).replace("`", "")
        props = dict(rel.get("properties", {}))
        props["graph_id"] = graph.get("graph_id")
        serialized = json.dumps(props, ensure_ascii=False)
        lines.append(
            f"MATCH (s {{node_id: '{rel['start']}'}}), (e {{node_id: '{rel['end']}'}}) "
            f"MERGE (s)-[r:`{rel_type}`]->(e) SET r += {serialized};"
        )

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def sync_constraint_graph_to_neo4j(
    graph: dict[str, Any],
    *,
    uri: str,
    username: str,
    password: str,
    database: str = "neo4j",
) -> dict[str, int]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Neo4j Python driver is not installed. Install `neo4j` first.") from exc

    graph_id = str(graph.get("graph_id", "constraint_graph"))
    grouped_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_relationships: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in graph.get("nodes", []):
        grouped_nodes[str(node["label"])].append(node)
    for rel in graph.get("relationships", []):
        grouped_relationships[str(rel["type"])].append(rel)

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            session.run("MATCH (n {graph_id: $graph_id}) DETACH DELETE n", graph_id=graph_id).consume()
            for label, rows in grouped_nodes.items():
                clean_label = label.replace("`", "")
                payload = [
                    {
                        "node_id": row["node_id"],
                        "props": {
                            **row.get("properties", {}),
                            "node_id": row["node_id"],
                            "graph_id": graph_id,
                        },
                    }
                    for row in rows
                ]
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:`{clean_label}` {{node_id: row.node_id}})
                    SET n += row.props
                    """,
                    rows=payload,
                ).consume()
            for rel_type, rows in grouped_relationships.items():
                clean_type = rel_type.replace("`", "")
                payload = [
                    {
                        "start": row["start"],
                        "end": row["end"],
                        "props": {**row.get("properties", {}), "graph_id": graph_id},
                    }
                    for row in rows
                ]
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (s {{node_id: row.start}})
                    MATCH (e {{node_id: row.end}})
                    MERGE (s)-[r:`{clean_type}`]->(e)
                    SET r += row.props
                    """,
                    rows=payload,
                ).consume()
    finally:
        driver.close()

    return {"nodes": len(graph.get("nodes", [])), "relationships": len(graph.get("relationships", []))}


class ConstraintGraphView:
    def __init__(self, graph: dict[str, Any]) -> None:
        self.graph = graph
        self.node_map = {node["node_id"]: node for node in graph.get("nodes", [])}
        self.outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in graph.get("relationships", []):
            self.outgoing[str(rel["start"])].append(rel)

    def fields_for_rule(self, rule_id: str, relation_type: str = "REMEDIATES_WITH_FIELD") -> list[str]:
        node_id = f"rule:{rule_id}"
        fields = []
        for rel in self.outgoing.get(node_id, []):
            if rel["type"] != relation_type:
                continue
            end = str(rel["end"])
            if end.startswith("field:"):
                fields.append(end.split(":", 1)[1])
        return fields

    def rule_context(self, rule_id: str) -> dict[str, Any]:
        node_id = f"rule:{rule_id}"
        rule_node = self.node_map.get(node_id, {})
        strategies = []
        cases = []
        edge_type = None
        for rel in self.outgoing.get(node_id, []):
            if rel["type"] == "USES_STRATEGY":
                strategy_node = self.node_map.get(rel["end"], {})
                strategies.append(strategy_node.get("properties", {}))
            elif rel["type"] == "USES_EDGE_TYPE":
                edge_node = self.node_map.get(rel["end"], {})
                edge_type = edge_node.get("properties", {}).get("name")
            elif rel["type"] == "REFERENCES_CASE":
                case_node = self.node_map.get(rel["end"], {})
                cases.append(
                    {
                        **case_node.get("properties", {}),
                        "link_score": rel.get("properties", {}).get("score", 0),
                    }
                )
        cases.sort(key=lambda item: (item.get("outcome") != "success", -int(item.get("link_score", 0))))
        return {
            **rule_node.get("properties", {}),
            "required_fields": self.fields_for_rule(rule_id, relation_type="REQUIRES_FIELD"),
            "remediation_fields": self.fields_for_rule(rule_id, relation_type="REMEDIATES_WITH_FIELD"),
            "edge_type": edge_type,
            "strategies": strategies,
            "cases": cases,
        }

    def cases_for_rule(self, rule_id: str, limit: int = 3) -> list[dict[str, Any]]:
        return self.rule_context(rule_id).get("cases", [])[:limit]

    def stage_subgraph(self, stage_key: str | None = None, *, cumulative: bool = True) -> dict[str, Any]:
        return build_stage_constraint_subgraph(self.graph, stage_key=stage_key, cumulative=cumulative)


@lru_cache(maxsize=1)
def load_constraint_graph(
    graph_path: Path | str = Path("outputs/graphs/constraint_graph.json"),
    *,
    rebuild_if_missing: bool = True,
) -> ConstraintGraphView:
    target = Path(graph_path)
    if not target.exists():
        if not rebuild_if_missing:
            raise FileNotFoundError(target)
        export_constraint_graph(target)
    graph = json.loads(target.read_text(encoding="utf-8"))
    return ConstraintGraphView(graph)


def build_stage_constraint_subgraph(
    graph: dict[str, Any],
    *,
    stage_key: str | None = None,
    cumulative: bool = True,
    max_hops: int = 2,
) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    node_map = {node.get("node_id"): node for node in nodes if node.get("node_id")}
    allowed_stages = set(stage_scope(stage_key, cumulative=cumulative))

    if not node_map:
        return {
            "graph_id": f"{graph.get('graph_id', 'constraint_graph')}::stage:empty",
            "description": "Stage hypergraph subgraph.",
            "node_count": 0,
            "relationship_count": 0,
            "stage_key": stage_key or "all",
            "stage_label": stage_display_name(stage_key or "idea") if stage_key else "全部阶段",
            "stage_scope": stage_scope(stage_key, cumulative=cumulative),
            "nodes": [],
            "relationships": [],
            "rule_count": 0,
            "node_type_counts": {},
            "source_graph_id": graph.get("graph_id", "constraint_graph"),
        }

    selected_rule_ids = {
        str(node.get("node_id"))
        for node in nodes
        if node.get("label") == "ConstraintRule"
        and bucket_rule_stage(
            str(node.get("properties", {}).get("rule_id", "")).strip() or str(node.get("node_id", "")).split(":", 1)[-1],
            str(node.get("properties", {}).get("stage_hint", "")),
        )
        in allowed_stages
    }

    if not stage_key:
        selected_rule_ids = {
            str(node.get("node_id"))
            for node in nodes
            if node.get("label") == "ConstraintRule" and node.get("node_id")
        }

    adjacency: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for index, rel in enumerate(relationships):
        start = str(rel.get("start"))
        end = str(rel.get("end"))
        adjacency[start].append((index, end))
        adjacency[end].append((index, start))

    visited_nodes = set(selected_rule_ids)
    visited_relationship_indexes: set[int] = set()
    frontier = set(selected_rule_ids)

    for _ in range(max_hops):
        next_frontier: set[str] = set()
        for node_id in frontier:
            for rel_index, neighbor in adjacency.get(node_id, []):
                neighbor_node = node_map.get(neighbor, {})
                if neighbor_node.get("label") == "ConstraintRule" and neighbor not in selected_rule_ids:
                    continue
                visited_relationship_indexes.add(rel_index)
                if neighbor not in visited_nodes:
                    visited_nodes.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break

    selected_relationships = [relationships[index] for index in sorted(visited_relationship_indexes)]
    selected_nodes = [node_map[node_id] for node_id in visited_nodes if node_id in node_map]
    node_type_counts: dict[str, int] = defaultdict(int)
    for node in selected_nodes:
        node_type_counts[str(node.get("label", "Unknown"))] += 1

    label = "全部阶段" if not stage_key else stage_display_name(stage_key)
    return {
        "graph_id": f"{graph.get('graph_id', 'constraint_graph')}::stage:{stage_key or 'all'}::{('cum' if cumulative else 'exact')}",
        "description": "Stage hypergraph subgraph derived from the full constraint graph.",
        "node_count": len(selected_nodes),
        "relationship_count": len(selected_relationships),
        "stage_key": stage_key or "all",
        "stage_label": label,
        "stage_scope": stage_scope(stage_key, cumulative=cumulative) if stage_key else list(stage_scope(None)),
        "nodes": selected_nodes,
        "relationships": selected_relationships,
        "rule_count": len(selected_rule_ids),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "source_graph_id": graph.get("graph_id", "constraint_graph"),
    }
