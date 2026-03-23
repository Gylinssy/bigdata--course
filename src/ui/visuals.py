from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


SEVERITY_COLORS = {
    "high": "#ef4444",
    "medium": "#f59e0b",
    "low": "#10b981",
}

STATUS_COLORS = {
    "high_risk": "#b91c1c",
    "fail": "#dc2626",
    "warning": "#d97706",
    "pass": "#059669",
}


def render_summary_metrics(cards: list[dict[str, str]]) -> None:
    if not cards:
        return
    columns = st.columns(len(cards))
    for column, card in zip(columns, cards):
        column.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">{html.escape(card["label"])}</div>
              <div class="metric-value">{html.escape(card["value"])}</div>
              <div class="metric-footnote">{html.escape(card.get("footnote", ""))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_score_cards(scores: list[dict[str, Any]]) -> None:
    if not scores:
        st.markdown('<div class="placeholder-card">暂无评分数据。</div>', unsafe_allow_html=True)
        return

    columns = st.columns(min(3, len(scores)))
    for index, item in enumerate(scores):
        columns[index % len(columns)].markdown(
            f"""
            <div class="score-grid-card">
              <strong>{html.escape(item["name"])}</strong>
              <div class="metric-value" style="font-size:1.65rem; margin-top:0;">{item["score"]}/5</div>
              <span>{html.escape(item.get("rationale", ""))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_score_bar_chart(scores: list[dict[str, Any]], y_key: str = "score") -> None:
    if not scores:
        st.info("暂无评分图表数据。")
        return
    chart_data = pd.DataFrame(scores)
    st.bar_chart(chart_data.set_index("name")[[y_key]], use_container_width=True)


def render_rule_bar_chart(rule_rows: list[dict[str, Any]]) -> None:
    if not rule_rows:
        st.info("暂无规则触发数据。")
        return
    chart_data = pd.DataFrame(rule_rows)
    st.bar_chart(chart_data.set_index("rule_id")[["count"]], use_container_width=True)


def render_hypergraph_visualization(rule_specs: dict[str, dict[str, Any]]) -> None:
    if not rule_specs:
        st.markdown('<div class="placeholder-card">暂无超图规则配置。</div>', unsafe_allow_html=True)
        return

    all_fields = sorted({field for spec in rule_specs.values() for field in spec.get("required_fields", [])})
    fields = all_fields[:18]
    rule_ids = sorted(rule_specs.keys())

    width = 980
    row_count = max(len(rule_ids), len(fields), 6)
    height = max(430, 56 * row_count)
    top = 52
    left_x = 250
    right_x = 730

    def y_for(index: int, total: int) -> float:
        if total <= 1:
            return height / 2
        usable = height - top * 2
        return top + (usable * index / (total - 1))

    rule_positions = {rule_id: (left_x, y_for(i, len(rule_ids))) for i, rule_id in enumerate(rule_ids)}
    field_positions = {field: (right_x, y_for(i, len(fields))) for i, field in enumerate(fields)}

    svg_parts: list[str] = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">',
        '<rect x="0" y="0" width="100%" height="100%" fill="transparent"></rect>',
    ]

    for rule_id, spec in rule_specs.items():
        rx, ry = rule_positions[rule_id]
        color = SEVERITY_COLORS.get(str(spec.get("severity", "low")), "#10b981")
        for field in spec.get("required_fields", []):
            if field not in field_positions:
                continue
            fx, fy = field_positions[field]
            c1x = rx + 160
            c2x = fx - 160
            svg_parts.append(
                f'<path d="M {rx + 72} {ry} C {c1x} {ry}, {c2x} {fy}, {fx - 72} {fy}" '
                f'stroke="{color}" stroke-width="1.8" opacity="0.5" fill="none"></path>'
            )

    for rule_id, (rx, ry) in rule_positions.items():
        safe_rule = html.escape(rule_id)
        color = SEVERITY_COLORS.get(str(rule_specs[rule_id].get("severity", "low")), "#10b981")
        svg_parts.append(
            f'<g><rect x="{rx - 64}" y="{ry - 22}" width="128" height="44" rx="16" fill="{color}" opacity="0.95"></rect>'
            f'<text x="{rx}" y="{ry + 5}" text-anchor="middle" font-size="13" fill="#ffffff" font-weight="700">{safe_rule}</text></g>'
        )

    for field, (fx, fy) in field_positions.items():
        safe_field = html.escape(field)
        svg_parts.append(
            f'<g><rect x="{fx - 68}" y="{fy - 22}" width="136" height="44" rx="16" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.5"></rect>'
            f'<text x="{fx}" y="{fy + 5}" text-anchor="middle" font-size="12" fill="#0f172a" font-weight="600">{safe_field}</text></g>'
        )

    svg_parts.append(
        '<text x="250" y="28" text-anchor="middle" font-size="13" fill="#64748b" font-weight="700">规则节点</text>'
        '<text x="730" y="28" text-anchor="middle" font-size="13" fill="#64748b" font-weight="700">字段节点</text>'
    )
    svg_parts.append("</svg>")

    svg_html = f'<div class="hypergraph-shell">{"".join(svg_parts)}</div>'
    components.html(svg_html, height=height + 6, scrolling=False)

    if len(all_fields) > len(fields):
        st.caption(f"字段较多，当前仅展示前 {len(fields)} 个字段节点。")

    legend_columns = st.columns(3)
    legend_columns[0].markdown('<div class="status-chip">高风险 · 红色连边</div>', unsafe_allow_html=True)
    legend_columns[1].markdown('<div class="status-chip">中风险 · 橙色连边</div>', unsafe_allow_html=True)
    legend_columns[2].markdown('<div class="status-chip">低风险 · 绿色连边</div>', unsafe_allow_html=True)


def render_rule_status_cards(rule_rows: list[dict[str, Any]]) -> None:
    if not rule_rows:
        st.markdown('<div class="placeholder-card">暂无规则状态。</div>', unsafe_allow_html=True)
        return
    columns = st.columns(min(3, len(rule_rows)))
    for index, row in enumerate(rule_rows):
        status_color = STATUS_COLORS.get(row.get("status", "pass"), "#6b7280")
        columns[index % len(columns)].markdown(
            f"""
            <div class="score-grid-card">
              <strong>{html.escape(row["rule_id"])}</strong>
              <div style="margin:0.35rem 0 0.45rem 0; color:{status_color}; font-weight:800;">
                {html.escape(row["status"])}
              </div>
              <span>{html.escape(row.get("message", ""))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
