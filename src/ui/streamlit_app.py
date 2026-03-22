# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.env_utils import load_env_file  # noqa: E402
from core.chat_agent import ConversationAgent  # noqa: E402
from core.evidence import format_evidence  # noqa: E402
from core.models import ChatMessage, ProjectCoachRequest  # noqa: E402
from core.ocr.ingest import ingest_directory  # noqa: E402
from core.pipeline import ProjectCoachPipeline  # noqa: E402

load_env_file()

DATA_CASES_DIR = ROOT / "data" / "cases"
OUTPUT_CASES_DIR = ROOT / "outputs" / "cases"
EXAMPLES_PATH = ROOT / "data" / "examples" / "project_inputs.jsonl"
ICON_URLS = {
    "brand": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/chat-square-dots-fill.svg",
    "student": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/person-workspace.svg",
    "teacher": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/mortarboard-fill.svg",
    "tools": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/gear-wide-connected.svg",
    "settings": "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/icons/sliders.svg",
}


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=ZCOOL+XiaoWei&family=IBM+Plex+Sans+Condensed:wght@400;600&display=swap');
        :root {
          --ink: #0f1c1f;
          --muted: #5f7168;
          --accent: #69b58a;
          --accent-2: #2f5d44;
          --panel: rgba(255, 255, 255, 0.9);
          --panel-strong: rgba(255, 255, 255, 0.98);
          --line: rgba(74, 110, 86, 0.12);
          --sidebar-bg: #eef5ef;
          --sidebar-card: rgba(255, 255, 255, 0.94);
          --sidebar-line: rgba(74, 110, 86, 0.14);
          --sidebar-text: #111827;
          --sidebar-muted: #6e7f76;
          --surface-soft: #f1f7f2;
        }
        .stApp {
          background:
            radial-gradient(circle at 12% 14%, rgba(247, 243, 235, 0.95), transparent 30%),
            radial-gradient(circle at 82% 18%, rgba(228, 244, 233, 0.92), transparent 28%),
            linear-gradient(180deg, #fffefb 0%, #f7fbf7 100%);
          color: var(--ink);
        }
        [data-testid="stAppViewContainer"] {
          background: transparent;
        }
        [data-testid="stHeader"] {
          background: rgba(250, 249, 247, 0.85);
        }
        h1, h2, h3, h4 {
          font-family: 'ZCOOL XiaoWei', 'Noto Serif SC', 'STSong', serif !important;
          letter-spacing: 0.2px;
        }
        body, p, div, span, label, input, textarea, button {
          font-family: 'IBM Plex Sans Condensed', 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
        }
        .badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 8px 12px;
          border-radius: 999px;
          background: #ffffff;
          border: 1px solid var(--line);
          font-size: 12px;
          color: var(--muted);
        }
        .panel {
          padding: 16px 18px;
          border-radius: 14px;
          background: var(--panel);
          border: 1px solid var(--line);
          box-shadow: 0 8px 20px rgba(15, 28, 31, 0.06);
        }
        .panel-title {
          font-weight: 600;
          font-size: 13px;
          text-transform: uppercase;
          letter-spacing: 1.2px;
          color: var(--muted);
          margin-bottom: 6px;
        }
        .divider {
          height: 1px;
          background: var(--line);
          margin: 6px 0 12px 0;
        }
        .stTextArea textarea,
        .stTextInput input,
        .stSelectbox [data-baseweb="select"] > div,
        .stMultiSelect [data-baseweb="select"] > div {
          border-radius: 16px !important;
          border-color: rgba(74, 110, 86, 0.08) !important;
          background: rgba(255, 255, 255, 0.96) !important;
        }
        .stButton button {
          background: var(--accent) !important;
          color: white !important;
          border-radius: 14px !important;
          border: 1px solid rgba(105, 181, 138, 0.35) !important;
          padding: 0.55rem 1rem !important;
          box-shadow: none !important;
        }
        .stButton button:hover {
          background: #57a678 !important;
        }
        .stChatMessage {
          border-radius: 22px;
          padding: 0.25rem 0;
        }
        .streamlit-expanderHeader,
        [data-testid="stExpander"] summary {
          display: flex !important;
          align-items: center !important;
          gap: 0.55rem !important;
          font-family: 'IBM Plex Sans Condensed', 'Noto Sans SC', 'Microsoft YaHei', 'PingFang SC', sans-serif !important;
          font-size: 15px !important;
          font-weight: 600 !important;
          line-height: 1.35 !important;
          color: #23342b !important;
          background: rgba(255, 255, 255, 0.86);
          border-radius: 16px;
          padding: 0.8rem 1rem !important;
          border: 1px solid rgba(74, 110, 86, 0.12);
        }
        [data-testid="stExpander"] summary p {
          margin: 0 !important;
          line-height: 1.35 !important;
          font-size: 15px !important;
          font-weight: 600 !important;
        }
        [data-testid="stExpander"] details > div {
          border: 1px solid rgba(74, 110, 86, 0.1);
          border-top: none;
          border-radius: 0 0 16px 16px;
          background: rgba(255, 255, 255, 0.62);
          padding: 0.8rem 1rem 1rem 1rem;
        }
        [data-testid="stExpander"] summary::-webkit-details-marker {
          display: none;
        }
        [data-testid="stSidebar"] > div {
          background: var(--sidebar-bg);
          color: var(--sidebar-text);
          border-right: 1px solid rgba(74, 110, 86, 0.18);
          box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.45);
        }
        [data-testid="stSidebarNav"] {
          display: none;
        }
        [data-testid="stSidebar"] {
          max-height: 100vh;
          overflow-y: auto;
          overflow-x: hidden;
          scrollbar-width: thin;
          scrollbar-color: rgba(105, 181, 138, 0.9) rgba(255, 255, 255, 0.3);
        }
        [data-testid="stSidebar"]::-webkit-scrollbar {
          width: 10px;
        }
        [data-testid="stSidebar"]::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.35);
          border-radius: 999px;
        }
        [data-testid="stSidebar"]::-webkit-scrollbar-thumb {
          background: linear-gradient(180deg, #7bc595, #5ea67a);
          border-radius: 999px;
          border: 2px solid rgba(255, 255, 255, 0.55);
        }
        [data-testid="stSidebar"]::-webkit-scrollbar-thumb:hover {
          background: linear-gradient(180deg, #69b58a, #4f9469);
        }
        [data-testid="stSidebar"] .block-container {
          padding-top: 1.2rem;
          padding-left: 1rem;
          padding-right: 1rem;
          padding-bottom: 1rem;
        }
        [data-testid="stSidebar"] .stButton button {
          background: #ffffff !important;
          border: 1px solid var(--sidebar-line) !important;
          color: var(--sidebar-text) !important;
          border-radius: 16px !important;
          padding: 0.72rem 0.95rem !important;
          justify-content: flex-start !important;
          box-shadow: 0 2px 10px rgba(74, 110, 86, 0.04) !important;
        }
        [data-testid="stSidebar"] .stButton button:hover {
          background: #f2f4f7 !important;
        }
        [data-testid="stSidebar"] .stButton button p {
          font-size: 14px !important;
        }
        [data-testid="stSidebar"] div[data-testid="column"] .stButton button {
          min-height: 2rem !important;
        }
        [data-testid="stSidebar"] .stRadio > div {
          gap: 0.45rem;
        }
        .side-title {
          font-weight: 600;
          font-size: 12px;
          color: var(--sidebar-muted);
          letter-spacing: 0.4px;
          margin: 1rem 0 0.45rem 0;
        }
        .chat-list {
          margin-top: 0.3rem;
        }
        .chat-item {
          margin-bottom: 0.55rem;
        }
        .chat-subline {
          font-size: 12px;
          color: var(--sidebar-muted);
          margin: -0.22rem 0 0.35rem 0.8rem;
          line-height: 1.3;
        }
        .nav-row {
          display: flex;
          align-items: center;
          gap: 0.65rem;
          margin-bottom: 0.5rem;
        }
        .nav-icon-box {
          width: 36px;
          height: 36px;
          border-radius: 12px;
          background: #ffffff;
          border: 1px solid var(--sidebar-line);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          flex: 0 0 36px;
        }
        .nav-icon-box img {
          width: 18px;
          height: 18px;
          object-fit: contain;
        }
        [data-testid="stSidebar"] .chat-item [data-testid="column"]:first-child .stButton button {
          min-height: 72px !important;
          height: 72px !important;
          align-items: flex-start !important;
          padding-top: 0.85rem !important;
          padding-left: 0.95rem !important;
          background: #ffffff !important;
          border: 1px solid rgba(74, 110, 86, 0.14) !important;
          box-shadow: 0 4px 14px rgba(74, 110, 86, 0.04) !important;
        }
        [data-testid="stSidebar"] .chat-item.active [data-testid="column"]:first-child .stButton button {
          background: #e7f3ea !important;
          border-color: rgba(105, 181, 138, 0.42) !important;
        }
        [data-testid="stSidebar"] .chat-item [data-testid="column"]:first-child .stButton button p {
          white-space: nowrap !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
          line-height: 1.25 !important;
          font-size: 14px !important;
          font-weight: 600 !important;
          color: #111827 !important;
        }
        [data-testid="stSidebar"] .chat-item [data-testid="column"]:last-child .stButton button {
          width: 26px !important;
          min-width: 26px !important;
          min-height: 26px !important;
          height: 26px !important;
          border-radius: 999px !important;
          padding: 0 !important;
          background: rgba(255, 255, 255, 0.96) !important;
          border: 1px solid rgba(74, 110, 86, 0.1) !important;
          color: #5f7168 !important;
          justify-content: center !important;
        }
        [data-testid="stSidebar"] .chat-item [data-testid="column"]:last-child .stButton button p {
          font-size: 13px !important;
        }
        .sidebar-bottom {
          position: sticky;
          bottom: 0;
          padding-top: 0.75rem;
          margin-top: 1rem;
          background: linear-gradient(180deg, rgba(238, 245, 239, 0), rgba(238, 245, 239, 0.94) 28%, rgba(238, 245, 239, 1) 100%);
        }
        .settings-sheet {
          background: rgba(255, 255, 255, 0.72);
          border: 1px solid rgba(74, 110, 86, 0.08);
          border-radius: 22px;
          padding: 1rem 1.1rem;
          box-shadow: 0 12px 36px rgba(15, 23, 42, 0.04);
          margin-bottom: 1rem;
        }
        .topbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 0.1rem 0 0.9rem 0;
          border-radius: 0;
          background: transparent;
          border-bottom: 1px solid rgba(74, 110, 86, 0.1);
          margin-bottom: 1rem;
        }
        .topbar-left {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .session-title {
          font-size: 18px;
          font-weight: 600;
          color: #111827;
        }
        .session-subtitle {
          font-size: 12px;
          color: var(--muted);
        }
        .topbar-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: #7ecb98;
        }
        .main-wrap {
          max-width: 1100px;
          margin: 0 auto;
        }
        .chat-layout {
          display: block;
        }
        .chat-stage {
          min-height: 0;
          padding-top: 0.25rem;
          padding-bottom: 2rem;
        }
        .empty-state {
          padding: 1.25rem 0.2rem 0.5rem 0.2rem;
          text-align: center;
          color: var(--muted);
        }
        .empty-state h2 {
          font-size: 32px;
          margin: 0 0 0.25rem 0 !important;
        }
        .message-wrap {
          max-width: 920px;
          margin: 0 auto 1rem auto;
        }
        .message-user {
          margin: 0 0 1rem auto;
          max-width: 78%;
          background: rgba(255, 255, 255, 0.92);
          border: 1px solid rgba(74, 110, 86, 0.08);
          border-radius: 20px;
          padding: 0.95rem 1.1rem;
          box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
        }
        .message-assistant {
          display: grid;
          grid-template-columns: 44px 1fr;
          gap: 1rem;
          align-items: flex-start;
        }
        .assistant-avatar {
          width: 44px;
          height: 44px;
          border-radius: 999px;
          background: linear-gradient(145deg, #8fb4ff, #6b8ff5);
          color: white;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 22px;
          box-shadow: 0 10px 22px rgba(107, 143, 245, 0.18);
        }
        .assistant-shell {
          background: rgba(255, 255, 255, 0.78);
          border: 1px solid rgba(74, 110, 86, 0.08);
          border-radius: 28px;
          padding: 1.1rem 1.35rem;
          box-shadow: 0 16px 40px rgba(15, 23, 42, 0.05);
        }
        .assistant-thinking {
          color: #60746a;
          font-size: 15px;
        }
        .assistant-meta {
          font-size: 12px;
          color: var(--muted);
          margin-top: 0.85rem;
          padding-top: 0.85rem;
          border-top: 1px solid rgba(74, 110, 86, 0.08);
        }
        .input-shell {
          background: rgba(255, 255, 255, 0.92);
          border: 1px solid rgba(74, 110, 86, 0.08);
          border-radius: 28px;
          padding: 0.8rem;
          box-shadow: 0 18px 45px rgba(15, 23, 42, 0.06);
          margin: 0.2rem auto 0 auto;
          max-width: 920px;
          position: sticky;
          bottom: 14px;
          z-index: 20;
          backdrop-filter: blur(8px);
        }
        .input-shell textarea {
          min-height: 110px !important;
          border: none !important;
          box-shadow: none !important;
          background: transparent !important;
        }
        .input-shell .stTextArea,
        .input-shell .stTextArea > div,
        .input-shell .stTextArea > div > div {
          background: transparent !important;
          border: none !important;
          box-shadow: none !important;
          padding-top: 0 !important;
          margin-top: 0 !important;
        }
        .toolbar-note {
          font-size: 12px;
          color: var(--muted);
          padding-top: 0.35rem;
          text-align: right;
        }
        .section-frame {
          background: rgba(255, 255, 255, 0.76);
          border: 1px solid rgba(74, 110, 86, 0.06);
          border-radius: 24px;
          padding: 1.2rem 1.25rem;
          box-shadow: 0 12px 36px rgba(15, 23, 42, 0.04);
          margin-bottom: 1rem;
        }
        .topbar .title {
          font-family: 'ZCOOL XiaoWei', 'Noto Serif SC', 'STSong', serif !important;
          font-size: 18px;
          margin: 0;
        }
        .topbar .meta {
          font-size: 12px;
          color: var(--muted);
        }
        .icon-label {
          font-size: 18px;
          margin-right: 0.45rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_examples() -> list[dict]:
    if not EXAMPLES_PATH.exists():
        return []
    examples = []
    for line in EXAMPLES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            examples.append(json.loads(line))
    return examples


def build_pipeline() -> ProjectCoachPipeline:
    return ProjectCoachPipeline()


def build_conversation_agent() -> ConversationAgent:
    return ConversationAgent()


def load_project_archives() -> list[str]:
    archive_dir = ROOT / "outputs" / "projects"
    if not archive_dir.exists():
        return []
    archives = sorted(archive_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [archive.stem for archive in archives]


def ensure_chat_state() -> None:
    if "chat_sessions" not in st.session_state:
        st.session_state["chat_sessions"] = []
    if "active_chat_id" not in st.session_state:
        st.session_state["active_chat_id"] = None
    if "active_section" not in st.session_state:
        st.session_state["active_section"] = "学生端"
    if "pending_chat_request" not in st.session_state:
        st.session_state["pending_chat_request"] = None
    if not st.session_state["chat_sessions"]:
        create_chat_session()


def create_chat_session() -> str:
    session_id = f"c-{uuid4().hex[:8]}"
    st.session_state["chat_sessions"].insert(
        0,
        {"id": session_id, "title": "新建会话", "messages": []},
    )
    st.session_state["active_chat_id"] = session_id
    return session_id


def delete_chat_session(session_id: str) -> None:
    sessions = st.session_state["chat_sessions"]
    st.session_state["chat_sessions"] = [session for session in sessions if session["id"] != session_id]
    if not st.session_state["chat_sessions"]:
        create_chat_session()
        return
    if st.session_state["active_chat_id"] == session_id:
        st.session_state["active_chat_id"] = st.session_state["chat_sessions"][0]["id"]


def get_active_session() -> dict:
    ensure_chat_state()
    active_id = st.session_state["active_chat_id"]
    for session in st.session_state["chat_sessions"]:
        if session["id"] == active_id:
            return session
    st.session_state["active_chat_id"] = st.session_state["chat_sessions"][0]["id"]
    return st.session_state["chat_sessions"][0]


def update_session_title(session: dict) -> None:
    user_messages = [msg["content"].strip() for msg in session["messages"] if msg["role"] == "user" and msg["content"].strip()]
    if not user_messages:
        session["title"] = "新建会话"
        return
    title = user_messages[0].replace("\n", " ")
    session["title"] = title[:14] + ("..." if len(title) > 14 else "")


def toggle_ui_flag(name: str) -> None:
    st.session_state[name] = not st.session_state.get(name, False)


def split_assistant_reply(content: str) -> tuple[str, str | None]:
    marker = "\n\n`model="
    if marker not in content:
        return content, None
    main, meta = content.split(marker, 1)
    return main, f"`model={meta}"


def ensure_env_loaded() -> None:
    load_env_file(override=True)


def render_status_panel() -> None:
    ensure_env_loaded()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    status = "已配置" if api_key else "未配置"
    st.markdown(f"**API Key**: {status}")
    st.caption("API Key 读取自项目根目录的 `.env`。")
    if api_key:
        st.caption(f"当前 Key：`{api_key[:6]}...{api_key[-4:]}`")
    st.write(
        {
            "DEEPSEEK_BASE_URL": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            "DEEPSEEK_OCR_BASE_URL": os.getenv("DEEPSEEK_OCR_BASE_URL", "未配置"),
            "CASE_INDEX_DIR": os.getenv("CASE_INDEX_DIR", "outputs/cases/index"),
        }
    )


def render_topbar() -> None:
    active_session = get_active_session()
    active_section = st.session_state.get("active_section", "学生端")
    if active_section == "学生端":
        title = active_session["title"]
        subtitle = "当前会话 · Startup Edu Agent"
    else:
        title = active_section
        subtitle = "工作台视图 · Startup Edu Agent"
    st.markdown(
        f"""
        <div class="topbar">
          <div class="topbar-left">
            <div class="topbar-dot"></div>
            <div>
              <div class="session-title">{html.escape(title)}</div>
              <div class="session-subtitle">{html.escape(subtitle)}</div>
            </div>
          </div>
          <div class="badge">DeepSeek 在线</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_project_coach_tab() -> None:
    st.subheader("项目诊断")
    examples = load_examples()
    selected_example = st.selectbox(
        "示例",
        options=["手动输入"] + [f"{item.get('project_id') or item.get('user_id')} 示例" for item in examples],
        index=0,
    )

    default_text = ""
    default_user_id = "u1"
    default_project_id = f"p-{uuid4().hex[:8]}"
    if selected_example != "手动输入":
        example = examples[
            [f"{item.get('project_id') or item.get('user_id')} 示例" for item in examples].index(selected_example)
        ]
        default_text = example["project_text"]
        default_user_id = example.get("user_id", default_user_id)
        default_project_id = example.get("project_id", default_project_id)

    with st.form("project_coach_form"):
        col1, col2 = st.columns(2)
        user_id = col1.text_input("User ID", value=default_user_id)
        project_id = col2.text_input("Project ID", value=default_project_id)
        project_text = st.text_area("项目描述", value=default_text, height=260, placeholder="粘贴项目描述")
        submitted = st.form_submit_button("运行诊断", use_container_width=True)

    if not submitted:
        return
    if not project_text.strip():
        st.warning("请先输入项目描述。")
        return

    ensure_env_loaded()
    pipeline = build_pipeline()
    output = pipeline.run(ProjectCoachRequest(user_id=user_id, project_id=project_id, project_text=project_text))

    st.markdown("### Current Diagnosis")
    st.write(output.current_diagnosis)

    st.markdown("### Next Task")
    st.success(output.next_task)

    st.markdown("### Impact")
    st.write(output.impact)

    st.markdown("### Evidence Used")
    for item in output.evidence_used:
        st.write(f"- {format_evidence(item)}")

    st.markdown("### Triggered Rules")
    st.dataframe(
        [
            {
                "rule_id": rule.rule_id,
                "status": rule.status.value,
                "severity": rule.severity.value,
                "message": rule.message,
                "fix_task": rule.fix_task,
            }
            for rule in output.detected_rules
        ],
        use_container_width=True,
    )

    st.markdown("### Rubric Scores")
    st.dataframe(
        [
            {
                "rubric_id": score.rubric_id,
                "name": score.name,
                "score": score.score,
                "rationale": score.rationale,
            }
            for score in output.rubric_scores
        ],
        use_container_width=True,
    )

    if output.retrieved_case_evidence:
        st.markdown("### Retrieved Case Evidence")
        for item in output.retrieved_case_evidence:
            st.write(f"- {format_evidence(item)}")

    report_open = st.session_state.get("project_markdown_report_open", False)
    if st.button("隐藏 Markdown Report" if report_open else "显示 Markdown Report", key="project_markdown_report_toggle"):
        toggle_ui_flag("project_markdown_report_open")
        st.rerun()
    if st.session_state.get("project_markdown_report_open", False):
        st.markdown(output.markdown_report or "")


def render_chat_tab() -> None:
    active_session = get_active_session()
    pending_request = st.session_state.get("pending_chat_request")
    is_pending_for_active = bool(pending_request and pending_request.get("session_id") == active_session["id"])

    with st.container():
        st.markdown('<div class="main-wrap">', unsafe_allow_html=True)
        st.markdown('<div class="chat-layout">', unsafe_allow_html=True)

        ctrl_a, ctrl_b, ctrl_c = st.columns([1, 1, 1.1])
        mode = ctrl_a.selectbox("模式", options=["general", "reasoning"], index=0, label_visibility="collapsed")
        include_context = ctrl_b.checkbox("附带项目上下文", value=True)
        archive_options = ["自动（取最近）"] + load_project_archives()
        selected_archive = ctrl_c.selectbox(
            "上下文来源",
            options=archive_options,
            index=0,
            disabled=not include_context,
            label_visibility="collapsed",
        )
        user_id = st.text_input("User ID", value="u1", label_visibility="collapsed", placeholder="User ID")

        st.markdown('<div class="chat-stage">', unsafe_allow_html=True)
        if not active_session["messages"]:
            st.markdown(
                """
                <div class="empty-state">
                  <h2>从一个问题开始</h2>
                  <div>你可以直接提问项目诊断、路演梳理、课程辅导或教师评估相关问题。</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            for message in active_session["messages"]:
                if message["role"] == "user":
                    st.markdown('<div class="message-wrap">', unsafe_allow_html=True)
                    st.markdown(f'<div class="message-user">{html.escape(message["content"])}</div>', unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    continue

                if message["role"] == "assistant":
                    reply_text, reply_meta = split_assistant_reply(message["content"])
                    st.markdown('<div class="message-wrap">', unsafe_allow_html=True)
                    st.markdown(
                        """
                        <div class="message-assistant">
                          <div class="assistant-avatar">··</div>
                          <div class="assistant-shell">
                        """,
                        unsafe_allow_html=True,
                    )
                    st.markdown(reply_text)
                    if reply_meta:
                        st.markdown(f'<div class="assistant-meta">{html.escape(reply_meta)}</div>', unsafe_allow_html=True)
                    st.markdown("</div></div></div>", unsafe_allow_html=True)
            if is_pending_for_active:
                st.markdown('<div class="message-wrap">', unsafe_allow_html=True)
                st.markdown(
                    """
                    <div class="message-assistant">
                      <div class="assistant-avatar">··</div>
                      <div class="assistant-shell">
                        <div class="assistant-thinking">正在思考...</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        with st.form("chat_input_form", clear_on_submit=True):
            st.markdown('<div class="input-shell">', unsafe_allow_html=True)
            user_text = st.text_area(
                "输入框",
                height=120,
                placeholder="尽管问",
                label_visibility="collapsed",
            )
            send_col, note_col = st.columns([1, 3])
            submitted = send_col.form_submit_button("发送", use_container_width=True)
            note_col.markdown('<div class="toolbar-note">学生端对话区 · 支持项目上下文</div>', unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if not submitted or not user_text.strip():
        if not is_pending_for_active:
            return
    else:
        active_session["messages"].append({"role": "user", "content": user_text.strip()})
        update_session_title(active_session)
        st.session_state["pending_chat_request"] = {
            "session_id": active_session["id"],
            "mode": mode,
            "user_id": user_id,
            "include_context": include_context,
            "selected_archive": selected_archive,
        }
        st.rerun()

    ensure_env_loaded()
    agent = build_conversation_agent()
    with st.spinner("正在思考..."):
        response = agent.chat(
            [ChatMessage(role=item["role"], content=item["content"]) for item in active_session["messages"]],
            mode=pending_request["mode"],
            user_id=pending_request["user_id"],
            include_project_context=pending_request["include_context"],
            project_id=None if pending_request["selected_archive"] == "自动（取最近）" else pending_request["selected_archive"],
        )
    context_info = f"context_used={response.context_used}"
    if response.context_project_id:
        context_info += f" context_project_id={response.context_project_id}"
    assistant_text = response.reply + f"\n\n`model={response.model} used_llm={response.used_llm} {context_info}`"
    active_session["messages"].append({"role": "assistant", "content": assistant_text})
    st.session_state["pending_chat_request"] = None
    st.rerun()


def render_ingest_tab() -> None:
    st.subheader("案例 OCR")

    backend = st.selectbox(
        "OCR Backend",
        options=["auto", "deepseek_ocr", "tesseract", "pdf_text"],
        index=0,
    )
    uploaded_files = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=True)

    if st.button("保存并执行 Ingest", use_container_width=True):
        if not uploaded_files:
            st.warning("请至少上传一个 PDF。")
            return
        DATA_CASES_DIR.mkdir(parents=True, exist_ok=True)
        saved_files = []
        for file in uploaded_files:
            target = DATA_CASES_DIR / file.name
            target.write_bytes(file.getbuffer())
            saved_files.append(target.name)

        ensure_env_loaded()
        stats = ingest_directory(DATA_CASES_DIR, OUTPUT_CASES_DIR, backend_name=backend)
        st.success(
            f"Ingest 完成：{stats.documents} 个文档，{stats.pages} 页，{stats.chunks} 个 chunk，backend={stats.backend}"
        )
        st.write({"saved_files": saved_files})

    pages_path = OUTPUT_CASES_DIR / "pages.jsonl"
    chunks_path = OUTPUT_CASES_DIR / "chunks.jsonl"
    if pages_path.exists():
        st.markdown("### 生成文件")
        st.write(
            {
                "pages.jsonl": str(pages_path),
                "chunks.jsonl": str(chunks_path),
                "index_dir": os.getenv("CASE_INDEX_DIR", str(OUTPUT_CASES_DIR / "index")),
            }
        )
        preview_lines = pages_path.read_text(encoding="utf-8").splitlines()[:3]
        preview_open = st.session_state.get("pages_jsonl_preview_open", False)
        if st.button("隐藏 pages.jsonl 预览" if preview_open else "显示 pages.jsonl 预览", key="pages_jsonl_preview_toggle"):
            toggle_ui_flag("pages_jsonl_preview_open")
            st.rerun()
        if st.session_state.get("pages_jsonl_preview_open", False):
            for line in preview_lines:
                st.code(line, language="json")


def render_teacher_tab() -> None:
    st.subheader("教师看板")
    ensure_env_loaded()
    pipeline = build_pipeline()
    dashboard = pipeline.teacher_dashboard()

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("项目总数", dashboard.total_projects)
    metric2.metric("高风险项目数", len(dashboard.high_risk_projects))
    metric3.metric("规则触发种类", len(dashboard.top_rule_triggers))

    st.markdown("### Top Rule Triggers")
    st.dataframe(
        [{"rule_id": key, "count": value} for key, value in dashboard.top_rule_triggers.items()],
        use_container_width=True,
    )

    st.markdown("### High Risk Projects")
    if dashboard.high_risk_projects:
        st.write(dashboard.high_risk_projects)
    else:
        st.info("当前没有 high_risk 项目。")

    st.markdown("### Missing Field Hotspots")
    st.dataframe(
        [{"field": key, "missing_count": value} for key, value in dashboard.field_missing_hotspots.items()],
        use_container_width=True,
    )

    st.markdown("### Intervention Suggestions")
    for item in dashboard.intervention_suggestions:
        st.write(f"- {item}")


def render_overview() -> None:
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(
            """
            <div class="panel">
              <div class="panel-title">系统能力</div>
              <div class="divider"></div>
              <div>项目诊断 / 规则触发 / 证据引用</div>
              <div>对话辅导 / 项目上下文追踪</div>
              <div>案例 OCR / 教师看板</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            """
            <div class="panel">
              <div class="panel-title">当前状态</div>
              <div class="divider"></div>
              <div>模型：DeepSeek OpenAI-compatible</div>
              <div>本地索引：outputs/cases/index</div>
              <div>运行模式：MVP Prototype</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_settings_sheet() -> None:
    st.markdown('<div class="settings-sheet">', unsafe_allow_html=True)
    st.markdown("### 设置")
    render_overview()
    render_status_panel()
    st.markdown("</div>", unsafe_allow_html=True)


def render_global_sidebar() -> None:
    ensure_chat_state()

    if st.sidebar.button("⊕  新建会话", use_container_width=True):
        create_chat_session()
        st.rerun()

    nav_items = [
        ("学生端", "学生端", ICON_URLS["student"]),
        ("教师端", "教师端", ICON_URLS["teacher"]),
        ("功能中心", "功能中心", ICON_URLS["tools"]),
    ]
    st.sidebar.markdown("<div class='side-title'>导航</div>", unsafe_allow_html=True)
    for section_name, button_label, icon_url in nav_items:
        icon_col, button_col = st.sidebar.columns([1, 5])
        icon_col.markdown(
            f'<div class="nav-row"><div class="nav-icon-box"><img src="{icon_url}" alt="{button_label} icon"></div></div>',
            unsafe_allow_html=True,
        )
        if button_col.button(button_label, use_container_width=True, key=f"nav_{section_name}"):
            st.session_state["active_section"] = section_name
            st.rerun()

    st.sidebar.markdown("<div class='side-title'>历史会话</div>", unsafe_allow_html=True)
    sessions = st.session_state["chat_sessions"]
    for session in sessions:
        preview = ""
        if session["messages"]:
            preview = session["messages"][-1]["content"].replace("\n", " ")
            preview = preview[:26] + ("..." if len(preview) > 26 else "")
        active_class = " active" if session["id"] == st.session_state["active_chat_id"] else ""
        st.sidebar.markdown(f'<div class="chat-item{active_class}">', unsafe_allow_html=True)
        pick_col, del_col = st.sidebar.columns([6, 1])
        card_label = session["title"]
        if pick_col.button(card_label, use_container_width=True, key=f"chat_pick_{session['id']}"):
            st.session_state["active_chat_id"] = session["id"]
            st.session_state["active_section"] = "学生端"
            st.rerun()
        if del_col.button("×", use_container_width=True, key=f"chat_drop_{session['id']}"):
            delete_chat_session(session["id"])
            st.rerun()
        st.sidebar.markdown("</div>", unsafe_allow_html=True)

    st.sidebar.markdown('<div class="sidebar-bottom">', unsafe_allow_html=True)
    settings_icon_col, settings_btn_col = st.sidebar.columns([1, 5])
    settings_icon_col.markdown(
        f'<div class="nav-row"><div class="nav-icon-box"><img src="{ICON_URLS["settings"]}" alt="settings icon"></div></div>',
        unsafe_allow_html=True,
    )
    if settings_btn_col.button("设置", use_container_width=True, key="sidebar_settings_toggle"):
        st.session_state["active_section"] = "设置"
        st.rerun()
    st.sidebar.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Startup Edu Agent", page_icon="💬", layout="wide")
    inject_styles()
    ensure_env_loaded()
    ensure_chat_state()
    render_global_sidebar()
    render_topbar()
    section = st.session_state.get("active_section", "学生端")

    if section == "学生端":
        render_chat_tab()
        return
    if section == "教师端":
        st.markdown('<div class="section-frame">', unsafe_allow_html=True)
        render_teacher_tab()
        st.markdown("</div>", unsafe_allow_html=True)
        return
    if section == "设置":
        render_settings_sheet()
        return

    st.markdown('<div class="section-frame">', unsafe_allow_html=True)
    render_project_coach_tab()
    st.divider()
    render_ingest_tab()
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
