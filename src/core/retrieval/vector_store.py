from __future__ import annotations

import json
import math
import re
from collections import Counter
from hashlib import md5
from pathlib import Path
from typing import Iterable


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def embed_text(text: str, dimensions: int = 256) -> list[float]:
    counts = Counter(tokenize(text))
    vector = [0.0] * dimensions
    for token, count in counts.items():
        index = int(md5(token.encode("utf-8")).hexdigest(), 16) % dimensions
        vector[index] += float(count)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class SimpleVectorStore:
    def __init__(self, index_dir: Path | str) -> None:
        self.index_dir = Path(index_dir)
        self.records_path = self.index_dir / "records.json"

    def build(self, records: Iterable[dict]) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        payload = []
        for record in records:
            payload.append(
                {
                    "id": record["chunk_id"],
                    "text": record["text"],
                    "metadata": {key: value for key, value in record.items() if key != "text"},
                    "vector": embed_text(record["text"]),
                }
            )
        self.records_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if not self.records_path.exists():
            return []
        records = json.loads(self.records_path.read_text(encoding="utf-8"))
        query_vector = embed_text(query)
        scored = []
        for record in records:
            score = sum(left * right for left, right in zip(query_vector, record["vector"]))
            scored.append((score, record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for score, record in scored[:top_k] if score > 0]
