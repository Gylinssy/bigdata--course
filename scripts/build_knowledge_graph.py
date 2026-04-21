from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.knowledge_graph import (  # noqa: E402
    export_knowledge_graph,
    export_knowledge_graph_cypher,
    sync_knowledge_graph_to_neo4j,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build case-library knowledge graph and optionally sync it into Neo4j.")
    parser.add_argument("--output", default="outputs/graphs/knowledge_graph.json")
    parser.add_argument("--cypher-output", default="outputs/graphs/neo4j/knowledge_graph.cypher")
    parser.add_argument("--cases-path", default="data/case_library/structured_cases.jsonl")
    parser.add_argument("--ontology-path", default="data/ontology.yaml")
    parser.add_argument("--sync-neo4j", action="store_true")
    parser.add_argument("--neo4j-uri", default=os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=os.getenv("NEO4J_PASSWORD", "neo4j"))
    parser.add_argument("--neo4j-database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    graph = export_knowledge_graph(
        ROOT / args.output,
        cases_path=ROOT / args.cases_path,
        ontology_path=ROOT / args.ontology_path,
    )
    cypher_path = export_knowledge_graph_cypher(graph, ROOT / args.cypher_output)
    print(f"graph_json={ROOT / args.output}")
    print(f"graph_nodes={graph['node_count']}")
    print(f"graph_relationships={graph['relationship_count']}")
    print(f"neo4j_cypher={cypher_path}")
    if args.sync_neo4j:
        result = sync_knowledge_graph_to_neo4j(
            graph,
            uri=args.neo4j_uri,
            username=args.neo4j_user,
            password=args.neo4j_password,
            database=args.neo4j_database,
        )
        print(f"neo4j_synced_nodes={result['nodes']}")
        print(f"neo4j_synced_relationships={result['relationships']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
