from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .case_library import build_case_retrieval_text, load_structured_cases, validate_case_record
from .project_stages import bucket_case_stage, stage_display_name, stage_scope

TOKEN_RE = re.compile("[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}")

DEFAULT_GRAPH_ID = "case_knowledge_graph_v1"
DEFAULT_CASES_PATH = Path("data/case_library/structured_cases.jsonl")
DEFAULT_ONTOLOGY_PATH = Path("data/ontology.yaml")
DEFAULT_GRAPH_PATH = Path("outputs/graphs/knowledge_graph.json")
DEFAULT_CYPHER_PATH = Path("outputs/graphs/neo4j/knowledge_graph.cypher")

FIELD_ALIASES: dict[str, set[str]] = {
    "problem": {"problem", "pain point", "痛点", "需求"},
    "customer_segment": {"customer", "segment", "用户", "客群", "人群"},
    "value_proposition": {"value", "proposition", "价值主张", "卖点"},
    "channel": {"channel", "获客", "渠道", "推广"},
    "revenue_model": {"revenue", "pricing", "营收", "收费", "定价"},
    "cost_structure": {"cost", "成本", "开支"},
    "ltv": {"ltv", "lifetime value", "终身价值"},
    "cac": {"cac", "获客成本"},
    "tam": {"tam", "total addressable market"},
    "sam": {"sam", "serviceable addressable market"},
    "som": {"som", "serviceable obtainable market"},
    "validation_evidence": {"evidence", "validation", "验证", "访谈", "问卷"},
    "execution_plan": {"execution", "milestone", "里程碑", "执行"},
    "competitive_advantage": {"competition", "advantage", "竞争", "护城河"},
}


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw_token in TOKEN_RE.findall(text or ""):
        token = raw_token.lower()
        tokens.add(token)
        if re.fullmatch(r"[\u4e00-\u9fff]{2,}", raw_token):
            for size in (2, 3):
                if len(raw_token) >= size:
                    for index in range(0, len(raw_token) - size + 1):
                        tokens.add(raw_token[index : index + size].lower())
    return tokens


def _safe_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _safe_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value.strip().lower())
    return slug.strip("_") or "unknown"


def _safe_read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _add_node(
    nodes: list[dict[str, Any]],
    node_index: dict[str, dict[str, Any]],
    node_id: str,
    label: str,
    name: str,
    *,
    text: str = "",
    source: str = "case_library",
    **props: Any,
) -> dict[str, Any]:
    if node_id in node_index:
        node = node_index[node_id]
        merged_props = dict(node.get("properties", {}))
        for key, value in props.items():
            if value not in ("", None, [], {}):
                merged_props[key] = value
        node["properties"] = merged_props
        if text and len(text) > len(str(node.get("text", ""))):
            node["text"] = text
        return node

    node = {
        "node_id": node_id,
        "label": label,
        "name": name,
        "text": text,
        "source": source,
        "properties": dict(props),
    }
    nodes.append(node)
    node_index[node_id] = node
    return node


def _add_relationship(
    relationships: list[dict[str, Any]],
    start: str,
    rel_type: str,
    end: str,
    **props: Any,
) -> None:
    relationships.append(
        {
            "start": start,
            "type": rel_type,
            "end": end,
            "properties": dict(props),
        }
    )


def _field_terms(field_name: str) -> set[str]:
    base = field_name.strip()
    tokens = {_slugify(base), base.lower()}
    tokens.update(_tokenize(base))
    tokens.update(FIELD_ALIASES.get(base, set()))
    return {item.lower() for item in tokens if item}


def build_knowledge_graph(
    *,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
) -> dict[str, Any]:
    cases = load_structured_cases(cases_path)
    ontology = _safe_read_yaml(Path(ontology_path))

    nodes: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    node_index: dict[str, dict[str, Any]] = {}

    project_fields = [_safe_str(item) for item in ontology.get("project_fields", []) if _safe_str(item)]
    sensitive_domains = [_safe_str(item) for item in ontology.get("sensitive_domains", []) if _safe_str(item)]

    for field_name in project_fields:
        _add_node(
            nodes,
            node_index,
            f"field:{field_name}",
            "ProjectField",
            field_name,
            text=f"project field: {field_name}",
            source="ontology",
        )

    for domain_name in sensitive_domains:
        _add_node(
            nodes,
            node_index,
            f"sensitive:{domain_name}",
            "SensitiveDomain",
            domain_name,
            text=f"sensitive domain: {domain_name}",
            source="ontology",
        )

    for record in cases:
        if validate_case_record(record):
            continue

        case_id = _safe_str(record.get("case_id"))
        if not case_id:
            continue

        title = _safe_str(record.get("title")) or case_id
        domain = _safe_str(record.get("domain"))
        outcome = _safe_str(record.get("outcome"))
        stage = _safe_str(record.get("stage"))
        tags = _safe_list(record.get("tags"))
        failure_reasons = _safe_list(record.get("failure_reasons"))
        lessons = _safe_list(record.get("lessons"))
        metrics = record.get("key_metrics") if isinstance(record.get("key_metrics"), dict) else {}

        case_node_id = f"case:{case_id}"
        case_text = build_case_retrieval_text(record)
        case_tokens = _tokenize(case_text)

        case_node = _add_node(
            nodes,
            node_index,
            case_node_id,
            "Case",
            title,
            text=case_text,
            source="case_library",
            case_id=case_id,
            domain=domain,
            outcome=outcome,
            stage=stage,
        )
        case_node["properties"]["token_count"] = len(case_tokens)

        if domain:
            domain_id = f"domain:{domain}"
            _add_node(nodes, node_index, domain_id, "CaseDomain", domain, text=f"domain: {domain}", source="case_library")
            _add_relationship(relationships, case_node_id, "HAS_DOMAIN", domain_id)

        if outcome:
            outcome_id = f"outcome:{outcome}"
            _add_node(nodes, node_index, outcome_id, "CaseOutcome", outcome, text=f"outcome: {outcome}", source="case_library")
            _add_relationship(relationships, case_node_id, "HAS_OUTCOME", outcome_id)

        if stage:
            stage_id = f"stage:{stage}"
            _add_node(nodes, node_index, stage_id, "CaseStage", stage, text=f"stage: {stage}", source="case_library")
            _add_relationship(relationships, case_node_id, "HAS_STAGE", stage_id)

        for tag in tags:
            tag_id = f"tag:{_slugify(tag)}"
            _add_node(nodes, node_index, tag_id, "CaseTag", tag, text=f"tag: {tag}", source="case_library")
            _add_relationship(relationships, case_node_id, "HAS_TAG", tag_id)

        for reason in failure_reasons:
            reason_id = f"failure:{case_id}:{_slugify(reason)}"
            _add_node(
                nodes,
                node_index,
                reason_id,
                "CaseFailure",
                reason,
                text=f"failure reason: {reason}",
                source="case_library",
            )
            _add_relationship(relationships, case_node_id, "HAS_FAILURE", reason_id)

        for lesson in lessons:
            lesson_id = f"lesson:{case_id}:{_slugify(lesson)}"
            _add_node(
                nodes,
                node_index,
                lesson_id,
                "CaseLesson",
                lesson,
                text=f"lesson: {lesson}",
                source="case_library",
            )
            _add_relationship(relationships, case_node_id, "TEACHES_LESSON", lesson_id)

        for metric_key, metric_value in metrics.items():
            metric_name = _safe_str(metric_key)
            if not metric_name:
                continue
            metric_id = f"metric:{_slugify(metric_name)}"
            metric_text = f"metric: {metric_name} value: {_safe_str(metric_value)}"
            _add_node(
                nodes,
                node_index,
                metric_id,
                "CaseMetric",
                metric_name,
                text=metric_text,
                source="case_library",
            )
            _add_relationship(
                relationships,
                case_node_id,
                "MENTIONS_METRIC",
                metric_id,
                value=_safe_str(metric_value),
            )

        case_surface = " ".join(
            [
                case_text,
                domain,
                outcome,
                stage,
                " ".join(tags),
                " ".join(failure_reasons),
                " ".join(lessons),
                " ".join(_safe_str(key) for key in metrics.keys()),
            ]
        )
        case_surface_tokens = _tokenize(case_surface)

        for sensitive_name in sensitive_domains:
            sensitive_terms = _field_terms(sensitive_name)
            if sensitive_name and sensitive_name in case_surface:
                _add_relationship(relationships, case_node_id, "SENSITIVE_TO", f"sensitive:{sensitive_name}")
            elif sensitive_terms & case_tokens:
                _add_relationship(relationships, case_node_id, "SENSITIVE_TO", f"sensitive:{sensitive_name}")

        for field_name in project_fields:
            if _field_terms(field_name) & case_surface_tokens:
                _add_relationship(relationships, case_node_id, "COVERS_FIELD", f"field:{field_name}")

    graph = {
        "graph_id": DEFAULT_GRAPH_ID,
        "description": "Knowledge graph derived from structured case library and ontology.",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
    }
    return graph


def export_knowledge_graph(
    output_path: Path | str = DEFAULT_GRAPH_PATH,
    *,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
) -> dict[str, Any]:
    graph = build_knowledge_graph(cases_path=cases_path, ontology_path=ontology_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def export_knowledge_graph_cypher(
    graph: dict[str, Any],
    output_path: Path | str = DEFAULT_CYPHER_PATH,
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    graph_id = str(graph.get("graph_id", DEFAULT_GRAPH_ID))
    lines = [
        "// Generated knowledge graph import for Neo4j",
        f"// graph_id={graph_id}",
        f"MATCH (n:KGNode {{graph_id: '{graph_id}'}}) DETACH DELETE n;",
    ]

    for node in graph.get("nodes", []):
        label = str(node.get("label", "GraphEntity")).replace("`", "")
        props = dict(node.get("properties", {}))
        props.update(
            {
                "node_id": node["node_id"],
                "name": node.get("name", ""),
                "text": node.get("text", ""),
                "source": node.get("source", ""),
                "graph_id": graph_id,
            }
        )
        serialized = json.dumps(props, ensure_ascii=False)
        lines.append(
            f"MERGE (n:KGNode:`{label}` {{node_id: '{node['node_id']}', graph_id: '{graph_id}'}}) "
            f"SET n += {serialized};"
        )

    for rel in graph.get("relationships", []):
        rel_type = str(rel.get("type", "RELATED_TO")).replace("`", "")
        props = dict(rel.get("properties", {}))
        props["graph_id"] = graph_id
        serialized = json.dumps(props, ensure_ascii=False)
        lines.append(
            f"MATCH (s:KGNode {{node_id: '{rel['start']}', graph_id: '{graph_id}'}}), "
            f"(e:KGNode {{node_id: '{rel['end']}', graph_id: '{graph_id}'}}) "
            f"MERGE (s)-[r:`{rel_type}` {{graph_id: '{graph_id}'}}]->(e) SET r += {serialized};"
        )

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _neo4j_config_from_env() -> dict[str, str] | None:
    uri = os.getenv("NEO4J_URI", "").strip()
    username = os.getenv("NEO4J_USER", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    database = os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    if not uri or not username or not password:
        return None
    return {
        "uri": uri,
        "username": username,
        "password": password,
        "database": database,
    }


def sync_knowledge_graph_to_neo4j(
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
        raise RuntimeError("Neo4j Python driver is not installed. Install optional dependency `graph`.") from exc

    graph_id = str(graph.get("graph_id", DEFAULT_GRAPH_ID))
    grouped_nodes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_relationships: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for node in graph.get("nodes", []):
        grouped_nodes[str(node.get("label", "GraphEntity"))].append(node)
    for rel in graph.get("relationships", []):
        grouped_relationships[str(rel.get("type", "RELATED_TO"))].append(rel)

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            session.run("MATCH (n:KGNode {graph_id: $graph_id}) DETACH DELETE n", graph_id=graph_id).consume()

            for label, rows in grouped_nodes.items():
                clean_label = label.replace("`", "")
                payload = []
                for row in rows:
                    props = dict(row.get("properties", {}))
                    props.update(
                        {
                            "node_id": row["node_id"],
                            "name": row.get("name", ""),
                            "text": row.get("text", ""),
                            "source": row.get("source", ""),
                            "graph_id": graph_id,
                        }
                    )
                    payload.append({"node_id": row["node_id"], "props": props})
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:KGNode:`{clean_label}` {{node_id: row.node_id, graph_id: $graph_id}})
                    SET n += row.props
                    """,
                    rows=payload,
                    graph_id=graph_id,
                ).consume()

            for rel_type, rows in grouped_relationships.items():
                clean_type = rel_type.replace("`", "")
                payload = []
                for row in rows:
                    props = dict(row.get("properties", {}))
                    props["graph_id"] = graph_id
                    payload.append(
                        {
                            "start": row["start"],
                            "end": row["end"],
                            "props": props,
                        }
                    )
                session.run(
                    f"""
                    UNWIND $rows AS row
                    MATCH (s:KGNode {{node_id: row.start, graph_id: $graph_id}})
                    MATCH (e:KGNode {{node_id: row.end, graph_id: $graph_id}})
                    MERGE (s)-[r:`{clean_type}` {{graph_id: $graph_id}}]->(e)
                    SET r += row.props
                    """,
                    rows=payload,
                    graph_id=graph_id,
                ).consume()
    finally:
        driver.close()

    return {
        "nodes": len(graph.get("nodes", [])),
        "relationships": len(graph.get("relationships", [])),
    }


def _load_graph_from_neo4j(
    *,
    uri: str,
    username: str,
    password: str,
    database: str = "neo4j",
    graph_id: str = DEFAULT_GRAPH_ID,
) -> dict[str, Any]:
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Neo4j Python driver is not installed. Install optional dependency `graph`.") from exc

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            node_rows = session.run(
                """
                MATCH (n:KGNode {graph_id: $graph_id})
                RETURN
                  n.node_id AS node_id,
                  head([label IN labels(n) WHERE label <> 'KGNode']) AS label,
                  n.name AS name,
                  n.text AS text,
                  n.source AS source,
                  properties(n) AS props
                ORDER BY n.node_id
                """,
                graph_id=graph_id,
            ).data()
            rel_rows = session.run(
                """
                MATCH (s:KGNode {graph_id: $graph_id})-[r {graph_id: $graph_id}]->(e:KGNode {graph_id: $graph_id})
                RETURN s.node_id AS start, type(r) AS type, e.node_id AS end, properties(r) AS props
                ORDER BY start, type, end
                """,
                graph_id=graph_id,
            ).data()
    finally:
        driver.close()

    nodes = []
    for row in node_rows:
        props = dict(row.get("props", {}) or {})
        for reserved in ("node_id", "name", "text", "source", "graph_id"):
            props.pop(reserved, None)
        nodes.append(
            {
                "node_id": row.get("node_id"),
                "label": row.get("label") or "GraphEntity",
                "name": row.get("name") or row.get("node_id"),
                "text": row.get("text") or "",
                "source": row.get("source") or "neo4j",
                "properties": props,
            }
        )

    relationships = []
    for row in rel_rows:
        props = dict(row.get("props", {}) or {})
        props.pop("graph_id", None)
        relationships.append(
            {
                "start": row.get("start"),
                "type": row.get("type"),
                "end": row.get("end"),
                "properties": props,
            }
        )

    return {
        "graph_id": graph_id,
        "description": "Knowledge graph loaded from Neo4j.",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "node_count": len(nodes),
        "relationship_count": len(relationships),
        "nodes": nodes,
        "relationships": relationships,
    }


@lru_cache(maxsize=4)
def _load_cached_graph_json(cache_key: str) -> dict[str, Any]:
    return json.loads(Path(cache_key).read_text(encoding="utf-8"))


def load_knowledge_graph_snapshot(
    graph_path: Path | str = DEFAULT_GRAPH_PATH,
    *,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
    prefer_neo4j: bool = True,
    write_cache: bool = False,
) -> dict[str, Any]:
    graph_target = Path(graph_path)
    neo4j_config = _neo4j_config_from_env()
    backend = "case_library"
    last_error = ""

    if prefer_neo4j and neo4j_config:
        try:
            graph = _load_graph_from_neo4j(**neo4j_config)
            return {
                "backend": "neo4j",
                "config_present": True,
                "error": "",
                "graph": graph,
            }
        except Exception as exc:  # pragma: no cover - network environment
            last_error = str(exc)

    if graph_target.exists():
        graph = _load_cached_graph_json(str(graph_target.resolve()))
        backend = "json_cache"
    else:
        graph = build_knowledge_graph(cases_path=cases_path, ontology_path=ontology_path)
        if write_cache:
            graph_target.parent.mkdir(parents=True, exist_ok=True)
            graph_target.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "backend": backend,
        "config_present": bool(neo4j_config),
        "error": last_error,
        "graph": graph,
    }


def load_kg_graph(
    graph_path: Path | str = DEFAULT_GRAPH_PATH,
    *,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
    write_cache: bool = False,
    prefer_neo4j: bool = True,
) -> dict[str, Any]:
    snapshot = load_knowledge_graph_snapshot(
        graph_path=graph_path,
        cases_path=cases_path,
        ontology_path=ontology_path,
        prefer_neo4j=prefer_neo4j,
        write_cache=write_cache,
    )
    return snapshot["graph"]


def reset_knowledge_graph_cache() -> None:
    _load_cached_graph_json.cache_clear()


def build_stage_knowledge_subgraph(
    graph: dict[str, Any],
    *,
    stage_key: str | None = None,
    cumulative: bool = True,
) -> dict[str, Any]:
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    if not nodes:
        return {
            "graph_id": f"{graph.get('graph_id', DEFAULT_GRAPH_ID)}::stage:empty",
            "description": "Stage knowledge subgraph.",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "node_count": 0,
            "relationship_count": 0,
            "stage_key": stage_key or "all",
            "stage_label": stage_display_name(stage_key or "idea") if stage_key else "全部阶段",
            "stage_scope": stage_scope(stage_key, cumulative=cumulative),
            "nodes": [],
            "relationships": [],
            "node_type_counts": {},
            "case_count": 0,
            "source_graph_id": graph.get("graph_id", DEFAULT_GRAPH_ID),
        }

    node_map = {node.get("node_id"): node for node in nodes if node.get("node_id")}
    allowed_stages = set(stage_scope(stage_key, cumulative=cumulative))
    selected_case_ids = {
        str(node.get("node_id"))
        for node in nodes
        if node.get("label") == "Case"
        and bucket_case_stage(_safe_str(node.get("properties", {}).get("stage"))) in allowed_stages
    }

    if not stage_key:
        selected_case_ids = {str(node.get("node_id")) for node in nodes if node.get("label") == "Case" and node.get("node_id")}

    selected_relationships = [
        rel
        for rel in relationships
        if rel.get("start") in selected_case_ids or rel.get("end") in selected_case_ids
    ]
    selected_node_ids = set(selected_case_ids)
    for rel in selected_relationships:
        selected_node_ids.add(str(rel.get("start")))
        selected_node_ids.add(str(rel.get("end")))

    selected_nodes = [node_map[node_id] for node_id in selected_node_ids if node_id in node_map]
    node_type_counts: dict[str, int] = defaultdict(int)
    for node in selected_nodes:
        node_type_counts[str(node.get("label", "Unknown"))] += 1

    label = "全部阶段" if not stage_key else stage_display_name(stage_key)
    return {
        "graph_id": f"{graph.get('graph_id', DEFAULT_GRAPH_ID)}::stage:{stage_key or 'all'}::{('cum' if cumulative else 'exact')}",
        "description": "Stage knowledge subgraph derived from the full knowledge graph.",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "node_count": len(selected_nodes),
        "relationship_count": len(selected_relationships),
        "stage_key": stage_key or "all",
        "stage_label": label,
        "stage_scope": stage_scope(stage_key, cumulative=cumulative) if stage_key else list(stage_scope(None)),
        "nodes": selected_nodes,
        "relationships": selected_relationships,
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "case_count": len(selected_case_ids),
        "source_graph_id": graph.get("graph_id", DEFAULT_GRAPH_ID),
    }


def load_kg_nodes(
    nodes_path: Path | str | None = None,
    *,
    cases_path: Path | str = DEFAULT_CASES_PATH,
    ontology_path: Path | str = DEFAULT_ONTOLOGY_PATH,
    write_cache: bool = False,
    prefer_neo4j: bool = True,
) -> list[dict[str, Any]]:
    snapshot = load_knowledge_graph_snapshot(
        cases_path=cases_path,
        ontology_path=ontology_path,
        prefer_neo4j=prefer_neo4j,
        write_cache=write_cache,
    )
    if snapshot["graph"].get("nodes"):
        return snapshot["graph"]["nodes"]

    if nodes_path is None:
        return []

    target = Path(nodes_path)
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "nodes" in payload:
            return payload.get("nodes", [])
        if isinstance(payload, list):
            return payload
    return []


def retrieve_kg_nodes(query: str, nodes: list[dict[str, Any]], top_k: int = 6) -> list[dict[str, Any]]:
    if not query or not nodes:
        return []
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for node in nodes:
        name = _safe_str(node.get("name"))
        text = _safe_str(node.get("text"))
        label = _safe_str(node.get("label"))
        node_tokens = _tokenize(" ".join([name, text, label]))
        if not node_tokens and not name and not text:
            continue
        overlap = query_tokens & node_tokens
        score = float(len(overlap))
        lower_query = query.lower()
        combined_text = " ".join([name, text, label]).lower()
        if lower_query and lower_query in combined_text:
            score += 2.5
        else:
            for token in query_tokens:
                if token and token in combined_text:
                    score += 1.0
        if score <= 0:
            continue
        if name and name.lower() in query.lower():
            score += 2.0
        if label in {"Case", "CaseLesson", "CaseFailure"}:
            score += 0.5
        scored.append((score, node))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored[:top_k]]
