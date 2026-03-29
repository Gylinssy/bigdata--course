from __future__ import annotations

from collections import Counter
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

SEVERITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

SEVERITY_LABELS = {
    "high": "高风险",
    "medium": "中风险",
    "low": "低风险",
}

FIELD_LABELS = {
    "cac": "CAC",
    "channel": "Channel",
    "competitive_advantage": "Advantage",
    "compliance_notes": "Compliance",
    "cost_structure": "Cost",
    "customer_segment": "Customer",
    "execution_plan": "Execution",
    "ltv": "LTV",
    "pilot_plan": "Pilot",
    "problem": "Problem",
    "revenue_model": "Revenue",
    "sam": "SAM",
    "som": "SOM",
    "tam": "TAM",
    "validation_evidence": "Evidence",
    "value_proposition": "Value",
}


def _edge_kind_label(arity: int) -> str:
    if arity >= 3:
        return "多字段超边"
    if arity == 2:
        return "双字段超边"
    return "单字段守卫"


def _balance_fields(fields: list[str], field_counts: Counter[str]) -> tuple[list[str], list[str]]:
    left_fields: list[str] = []
    right_fields: list[str] = []
    left_weight = 0
    right_weight = 0
    for field in fields:
        weight = field_counts[field]
        if left_weight <= right_weight:
            left_fields.append(field)
            left_weight += weight
        else:
            right_fields.append(field)
            right_weight += weight
    return left_fields, right_fields


def _build_hypergraph_view_model(rule_specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    field_counts: Counter[str] = Counter()
    hyperedges: list[dict[str, Any]] = []

    for rule_id, spec in rule_specs.items():
        members = sorted({str(field) for field in spec.get("required_fields", []) if field})
        severity = str(spec.get("severity", "low")).lower()
        field_counts.update(members)
        hyperedges.append(
            {
                "rule_id": rule_id,
                "severity": severity,
                "severity_label": SEVERITY_LABELS.get(severity, severity),
                "members": members,
                "arity": len(members),
                "edge_kind": _edge_kind_label(len(members)),
            }
        )

    hyperedges.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 99), -item["arity"], item["rule_id"]))
    fields = sorted(field_counts.keys(), key=lambda field: (-field_counts[field], field))
    left_fields, right_fields = _balance_fields(fields, field_counts)

    return {
        "fields": fields,
        "left_fields": left_fields,
        "right_fields": right_fields,
        "field_counts": dict(field_counts),
        "hyperedges": hyperedges,
        "field_count": len(fields),
        "hyperedge_count": len(hyperedges),
        "max_arity": max((item["arity"] for item in hyperedges), default=0),
        "avg_arity": round(sum(item["arity"] for item in hyperedges) / len(hyperedges), 2) if hyperedges else 0.0,
    }


def _lane_positions(items: list[str], x: float, height: int, top: int = 88, bottom: int = 72) -> dict[str, tuple[float, float]]:
    if not items:
        return {}
    if len(items) == 1:
        return {items[0]: (x, height / 2)}
    usable = max(height - top - bottom, 1)
    step = usable / (len(items) - 1)
    return {item: (x, top + index * step) for index, item in enumerate(items)}


def _field_label(field: str) -> str:
    return FIELD_LABELS.get(field, field.replace("_", " ").title())


def _build_hypergraph_matrix_html(view_model: dict[str, Any]) -> str:
    fields = view_model["fields"]
    rows = view_model["hyperedges"]
    header_html = "".join(
        f'<th title="{html.escape(field)}"><span class="hg-col-title">{html.escape(_field_label(field))}</span><span class="hg-col-code">{html.escape(field)}</span></th>'
        for field in fields
    )

    row_html: list[str] = []
    for edge in rows:
        severity_color = SEVERITY_COLORS.get(edge["severity"], "#64748b")
        membership_cells = []
        member_set = set(edge["members"])
        for field in fields:
            dot_class = "filled" if field in member_set else "empty"
            cell_html = (
                f'<span class="hg-dot {dot_class}" '
                f'style="background:{severity_color if field in member_set else "#e2e8f0"}"></span>'
            )
            membership_cells.append(f"<td>{cell_html}</td>")

        row_html.append(
            "".join(
                [
                    "<tr>",
                    f'<td class="hg-sticky"><div class="hg-row-rule">{html.escape(edge["rule_id"])}</div><div class="hg-row-kind">{html.escape(edge["edge_kind"])}</div></td>',
                    f'<td><span class="hg-severity-chip" style="background:{severity_color}1A; color:{severity_color}; border-color:{severity_color}40;">{html.escape(edge["severity_label"])}</span></td>',
                    f"<td>{edge['arity']}</td>",
                    *membership_cells,
                    "</tr>",
                ]
            )
        )

    return (
        '<div class="hg-matrix-wrap">'
        '<div class="hg-matrix-title">超边关联矩阵</div>'
        '<div class="hg-matrix-note">每一行表示一条超边；有色圆点表示该字段属于这条超边。</div>'
        '<div class="hg-matrix-scroll"><table class="hg-matrix">'
        "<thead><tr><th class=\"hg-sticky\">超边</th><th>风险</th><th>成员数</th>"
        f"{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table></div></div>"
    )


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

    view_model = _build_hypergraph_view_model(rule_specs)
    fields = view_model["fields"]
    left_fields = view_model["left_fields"]
    right_fields = view_model["right_fields"]
    hyperedges = view_model["hyperedges"]
    field_counts = view_model["field_counts"]

    width = 1180
    field_width = 166
    field_height = 48
    edge_width = 188
    edge_height = 64
    center_x = width / 2
    left_x = 162
    right_x = width - 162
    graph_height = max(560, 38 * max(len(hyperedges), len(fields)) + 180)
    top_margin = 104

    left_positions = _lane_positions(left_fields, left_x, graph_height, top=top_margin, bottom=84)
    right_positions = _lane_positions(right_fields, right_x, graph_height, top=top_margin, bottom=84)
    edge_positions = _lane_positions([item["rule_id"] for item in hyperedges], center_x, graph_height, top=top_margin, bottom=84)

    svg_parts: list[str] = [
        f'<svg viewBox="0 0 {width} {graph_height}" width="100%" height="{graph_height}" role="img" aria-label="Hypergraph overview">',
        '<defs><filter id="hgShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#94a3b8" flood-opacity="0.15"/></filter></defs>',
        '<rect x="0" y="0" width="100%" height="100%" rx="28" fill="#ffffff"></rect>',
        '<text x="162" y="54" text-anchor="middle" font-size="14" fill="#475569" font-weight="700">字段节点</text>',
        '<text x="590" y="54" text-anchor="middle" font-size="14" fill="#475569" font-weight="700">超边</text>',
        '<text x="1018" y="54" text-anchor="middle" font-size="14" fill="#475569" font-weight="700">字段节点</text>',
        '<text x="590" y="78" text-anchor="middle" font-size="12" fill="#94a3b8">每条超边代表一条约束规则，连接多个字段成员</text>',
    ]

    for edge in hyperedges:
        rule_id = edge["rule_id"]
        ex, ey = edge_positions[rule_id]
        severity_color = SEVERITY_COLORS.get(edge["severity"], "#64748b")
        left_members = [field for field in edge["members"] if field in left_positions]
        right_members = [field for field in edge["members"] if field in right_positions]

        if left_members:
            bundle_x = ex - 122
            bundle_y = sum(left_positions[field][1] for field in left_members) / len(left_members)
            svg_parts.append(
                f'<path d="M {ex - edge_width / 2 + 10} {ey} C {ex - 70} {ey}, {bundle_x + 26} {bundle_y}, {bundle_x} {bundle_y}" '
                f'stroke="{severity_color}" stroke-width="2.6" opacity="0.82" fill="none"></path>'
            )
            svg_parts.append(f'<circle cx="{bundle_x}" cy="{bundle_y}" r="4.5" fill="{severity_color}" opacity="0.95"></circle>')
            for field in left_members:
                fx, fy = left_positions[field]
                svg_parts.append(
                    f'<path d="M {fx + field_width / 2 - 6} {fy} C {fx + 86} {fy}, {bundle_x - 34} {bundle_y}, {bundle_x} {bundle_y}" '
                    f'stroke="{severity_color}" stroke-width="1.7" opacity="0.42" fill="none"></path>'
                )

        if right_members:
            bundle_x = ex + 122
            bundle_y = sum(right_positions[field][1] for field in right_members) / len(right_members)
            svg_parts.append(
                f'<path d="M {ex + edge_width / 2 - 10} {ey} C {ex + 70} {ey}, {bundle_x - 26} {bundle_y}, {bundle_x} {bundle_y}" '
                f'stroke="{severity_color}" stroke-width="2.6" opacity="0.82" fill="none"></path>'
            )
            svg_parts.append(f'<circle cx="{bundle_x}" cy="{bundle_y}" r="4.5" fill="{severity_color}" opacity="0.95"></circle>')
            for field in right_members:
                fx, fy = right_positions[field]
                svg_parts.append(
                    f'<path d="M {bundle_x} {bundle_y} C {bundle_x + 34} {bundle_y}, {fx - 86} {fy}, {fx - field_width / 2 + 6} {fy}" '
                    f'stroke="{severity_color}" stroke-width="1.7" opacity="0.42" fill="none"></path>'
                )

    for field, (fx, fy) in {**left_positions, **right_positions}.items():
        safe_field = html.escape(field)
        safe_label = html.escape(_field_label(field))
        degree = int(field_counts.get(field, 0))
        rect_x = fx - field_width / 2
        rect_y = fy - field_height / 2
        bubble_x = rect_x + field_width - 17
        bubble_y = rect_y + 16
        svg_parts.append(
            f'<g filter="url(#hgShadow)">'
            f'<rect x="{rect_x}" y="{rect_y}" width="{field_width}" height="{field_height}" rx="16" fill="#ffffff" stroke="#dbe4ee" stroke-width="1.5"></rect>'
            f'<text x="{fx}" y="{fy - 3}" text-anchor="middle" font-size="13" fill="#0f172a" font-weight="700">{safe_label}</text>'
            f'<text x="{fx}" y="{fy + 14}" text-anchor="middle" font-size="10.5" fill="#64748b">{safe_field}</text>'
            f'<circle cx="{bubble_x}" cy="{bubble_y}" r="10" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1"></circle>'
            f'<text x="{bubble_x}" y="{bubble_y + 3.5}" text-anchor="middle" font-size="10" fill="#1d4ed8" font-weight="700">{degree}</text>'
            f"</g>"
        )

    for edge in hyperedges:
        ex, ey = edge_positions[edge["rule_id"]]
        severity_color = SEVERITY_COLORS.get(edge["severity"], "#64748b")
        safe_rule = html.escape(edge["rule_id"])
        safe_kind = html.escape(edge["edge_kind"])
        rect_x = ex - edge_width / 2
        rect_y = ey - edge_height / 2
        chip_width = 56
        chip_x = rect_x + edge_width - chip_width - 12
        chip_y = rect_y + 11
        svg_parts.append(
            f'<g filter="url(#hgShadow)">'
            f'<rect x="{rect_x}" y="{rect_y}" width="{edge_width}" height="{edge_height}" rx="20" fill="#ffffff" stroke="{severity_color}" stroke-width="2"></rect>'
            f'<rect x="{rect_x + 12}" y="{rect_y + 12}" width="48" height="22" rx="11" fill="{severity_color}" opacity="0.12"></rect>'
            f'<text x="{rect_x + 36}" y="{rect_y + 27}" text-anchor="middle" font-size="12" fill="{severity_color}" font-weight="700">{safe_rule}</text>'
            f'<rect x="{chip_x}" y="{chip_y}" width="{chip_width}" height="22" rx="11" fill="{severity_color}" opacity="0.12"></rect>'
            f'<text x="{chip_x + chip_width / 2}" y="{chip_y + 15}" text-anchor="middle" font-size="11" fill="{severity_color}" font-weight="700">{html.escape(edge["severity_label"])}</text>'
            f'<text x="{ex}" y="{ey + 4}" text-anchor="middle" font-size="12.5" fill="#0f172a" font-weight="700">{safe_kind}</text>'
            f'<text x="{ex}" y="{ey + 22}" text-anchor="middle" font-size="11" fill="#64748b">{edge["arity"]} 个成员字段</text>'
            f"</g>"
        )

    svg_parts.append("</svg>")

    stats_html = "".join(
        [
            f'<div class="hg-stat"><div class="hg-stat-label">字段节点</div><div class="hg-stat-value">{view_model["field_count"]}</div><div class="hg-stat-note">唯一字段数量</div></div>',
            f'<div class="hg-stat"><div class="hg-stat-label">超边数量</div><div class="hg-stat-value">{view_model["hyperedge_count"]}</div><div class="hg-stat-note">规则即超边</div></div>',
            f'<div class="hg-stat"><div class="hg-stat-label">最大成员数</div><div class="hg-stat-value">{view_model["max_arity"]}</div><div class="hg-stat-note">单条超边最多连接字段</div></div>',
            f'<div class="hg-stat"><div class="hg-stat-label">平均成员数</div><div class="hg-stat-value">{view_model["avg_arity"]}</div><div class="hg-stat-note">超边复杂度</div></div>',
        ]
    )

    legend_html = "".join(
        [
            '<div class="hg-legend-chip"><span class="hg-legend-node"></span> 字段节点</div>',
            '<div class="hg-legend-chip"><span class="hg-legend-edge"></span> 超边</div>',
            '<div class="hg-legend-chip"><span class="hg-legend-line high"></span> 高风险连线</div>',
            '<div class="hg-legend-chip"><span class="hg-legend-line medium"></span> 中风险连线</div>',
            '<div class="hg-legend-chip"><span class="hg-legend-line low"></span> 低风险连线</div>',
        ]
    )

    matrix_html = _build_hypergraph_matrix_html(view_model)
    html_block = f"""
    <div class="hg-wrap">
      <style>
        .hg-wrap {{
          font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
          color: #0f172a;
          background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
          border: 1px solid #e2e8f0;
          border-radius: 28px;
          padding: 18px;
          box-sizing: border-box;
        }}
        .hg-meta-grid {{
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 12px;
          margin-bottom: 14px;
        }}
        .hg-stat {{
          border: 1px solid #e2e8f0;
          border-radius: 18px;
          background: rgba(255,255,255,0.94);
          padding: 14px 16px;
        }}
        .hg-stat-label {{
          font-size: 12px;
          color: #64748b;
          font-weight: 700;
          letter-spacing: 0.04em;
          text-transform: uppercase;
        }}
        .hg-stat-value {{
          font-size: 28px;
          font-weight: 800;
          margin: 6px 0 2px 0;
          color: #0f172a;
        }}
        .hg-stat-note {{
          font-size: 12px;
          color: #94a3b8;
        }}
        .hg-legend {{
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin: 14px 0 14px 0;
        }}
        .hg-legend-chip {{
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border-radius: 999px;
          border: 1px solid #e2e8f0;
          background: rgba(255,255,255,0.94);
          padding: 8px 12px;
          font-size: 12px;
          color: #475569;
          font-weight: 600;
        }}
        .hg-legend-node {{
          width: 14px;
          height: 14px;
          border-radius: 5px;
          border: 1.5px solid #cbd5e1;
          background: #ffffff;
          display: inline-block;
        }}
        .hg-legend-edge {{
          width: 16px;
          height: 10px;
          border-radius: 999px;
          border: 2px solid #475569;
          background: rgba(255,255,255,0.94);
          display: inline-block;
        }}
        .hg-legend-line {{
          width: 22px;
          height: 3px;
          border-radius: 999px;
          display: inline-block;
        }}
        .hg-legend-line.high {{ background: #ef4444; }}
        .hg-legend-line.medium {{ background: #f59e0b; }}
        .hg-legend-line.low {{ background: #10b981; }}
        .hg-matrix-wrap {{
          margin-top: 16px;
          border: 1px solid #e2e8f0;
          border-radius: 20px;
          background: rgba(255,255,255,0.96);
          overflow: hidden;
        }}
        .hg-matrix-title {{
          font-size: 15px;
          font-weight: 800;
          padding: 16px 16px 4px 16px;
          color: #0f172a;
        }}
        .hg-matrix-note {{
          font-size: 12px;
          color: #64748b;
          padding: 0 16px 12px 16px;
        }}
        .hg-matrix-scroll {{
          overflow-x: auto;
          border-top: 1px solid #eef2f7;
        }}
        .hg-matrix {{
          width: max-content;
          min-width: 100%;
          border-collapse: collapse;
          font-size: 12px;
        }}
        .hg-matrix th, .hg-matrix td {{
          padding: 10px 10px;
          border-bottom: 1px solid #eef2f7;
          border-right: 1px solid #f1f5f9;
          text-align: center;
          vertical-align: middle;
          background: rgba(255,255,255,0.98);
        }}
        .hg-matrix th {{
          background: #f8fafc;
          color: #475569;
          font-weight: 700;
        }}
        .hg-sticky {{
          text-align: left !important;
          min-width: 132px;
        }}
        .hg-row-rule {{
          font-weight: 800;
          color: #0f172a;
        }}
        .hg-row-kind {{
          font-size: 11px;
          color: #64748b;
          margin-top: 2px;
        }}
        .hg-severity-chip {{
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-width: 54px;
          border-radius: 999px;
          border: 1px solid transparent;
          padding: 4px 8px;
          font-size: 11px;
          font-weight: 700;
        }}
        .hg-col-title {{
          display: block;
          font-weight: 700;
          color: #0f172a;
        }}
        .hg-col-code {{
          display: block;
          margin-top: 3px;
          font-size: 10px;
          color: #94a3b8;
          font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        }}
        .hg-dot {{
          display: inline-block;
          width: 12px;
          height: 12px;
          border-radius: 999px;
        }}
        @media (max-width: 980px) {{
          .hg-meta-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }}
        }}
      </style>
      <div class="hg-meta-grid">{stats_html}</div>
      {''.join(svg_parts)}
      <div class="hg-legend">{legend_html}</div>
      {matrix_html}
    </div>
    """

    component_height = graph_height + len(hyperedges) * 34 + 460
    components.html(html_block, height=component_height, scrolling=False)


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
