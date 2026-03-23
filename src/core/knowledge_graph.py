from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,}")


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text)}


def _build_default_nodes() -> list[dict[str, Any]]:
    seed_map: dict[str, list[str]] = {
        "concept": [
            "TAM",
            "SAM",
            "SOM",
            "MVP",
            "价值主张",
            "客户细分",
            "单位经济",
            "留存",
            "复购",
            "用户访谈",
            "需求验证",
            "产品市场匹配",
            "竞品分析",
            "护城河",
            "增长模型",
            "商业闭环",
            "现金流",
            "毛利率",
            "净利率",
            "运营杠杆",
        ],
        "method": [
            "AARRR 模型",
            "精益画布",
            "商业模式画布",
            "五力分析",
            "SWOT",
            "访谈提纲设计",
            "问卷抽样",
            "MVP 验证实验",
            "AB 测试",
            "漏斗分析",
            "同类竞品拆解",
            "风险清单法",
            "试点路线图",
            "里程碑排期",
            "成本测算表",
            "收入测算表",
            "路演答辩框架",
            "评分维度映射",
            "证据链标注",
            "复盘模板",
        ],
        "metric": [
            "CAC",
            "LTV",
            "LTV/CAC",
            "转化率",
            "留存率",
            "复购率",
            "客单价",
            "ARPU",
            "获客成本",
            "渠道ROI",
            "月活",
            "周活",
            "GMV",
            "回本周期",
            "盈亏平衡点",
            "试点通过率",
            "满意度",
            "NPS",
            "投诉率",
            "交付周期",
        ],
        "competition": [
            "互联网+",
            "挑战杯",
            "创新创业训练计划",
            "数学建模竞赛",
            "路演评分标准",
            "商业价值维度",
            "技术创新维度",
            "社会价值维度",
            "团队能力维度",
            "答辩逻辑维度",
            "可行性维度",
            "风险控制维度",
            "证据充分性维度",
            "项目落地维度",
            "用户价值维度",
            "市场前景维度",
            "财务合理性维度",
            "合规伦理维度",
            "执行进度维度",
            "迭代能力维度",
        ],
    }

    nodes: list[dict[str, Any]] = []
    for category, seeds in seed_map.items():
        for seed in seeds:
            for variant in ("定义", "案例", "方法"):
                name = f"{seed}-{variant}"
                nodes.append(
                    {
                        "node_id": f"{category}-{len(nodes)+1:03d}",
                        "name": name,
                        "category": category,
                        "aliases": [seed, seed.lower()],
                        "description": f"{seed} 的{variant}节点，用于学习辅导和路演准备。",
                    }
                )
    return nodes


def load_kg_nodes(path: Path | str = Path("data/kg_nodes.json")) -> list[dict[str, Any]]:
    target = Path(path)
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(payload, list) and payload:
                return payload
        except Exception:
            pass
    return _build_default_nodes()


def retrieve_kg_nodes(query: str, nodes: list[dict[str, Any]], top_k: int = 8) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    scored: list[tuple[int, dict[str, Any]]] = []
    for node in nodes:
        text = " ".join(
            [
                str(node.get("name", "")),
                " ".join(node.get("aliases", []) if isinstance(node.get("aliases"), list) else []),
                str(node.get("description", "")),
            ]
        )
        node_tokens = _tokenize(text)
        score = len(query_tokens & node_tokens)
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda item: (item[0], item[1].get("node_id", "")), reverse=True)
    if scored:
        return [item[1] for item in scored[:top_k]]
    return nodes[:top_k]
