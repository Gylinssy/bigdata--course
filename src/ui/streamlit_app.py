# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.chat_agent import ConversationAgent  # noqa: E402
from core.case_library import export_structured_chunks  # noqa: E402
from core.env_utils import load_env_file  # noqa: E402
from core.evidence import format_evidence  # noqa: E402
from core.idea_agent import IdeaCoachAgent  # noqa: E402
from core.learning_agent import LearningTutorAgent  # noqa: E402
from core.models import ChatMessage, IdeaWorkspace, ProjectCoachRequest  # noqa: E402
from core.ocr.ingest import ingest_directory  # noqa: E402
from core.pipeline import ProjectCoachPipeline  # noqa: E402
from core.runtime_log import RuntimeLogger  # noqa: E402
from core.rule_engine import RuleEngine  # noqa: E402
from ui.auth import (  # noqa: E402
    ROLE_ADMIN,
    ROLE_STUDENT,
    SECTION_ADMIN,
    SECTION_CENTER,
    SECTION_STUDENT,
    SECTION_TEACHER,
    authenticate,
    current_user,
    ensure_authorized_section,
    init_auth_state,
    login_user,
    logout_user,
    register_user,
)
from ui.asset_precheck import build_asset_scale_report  # noqa: E402
from ui.dashboard_data import (  # noqa: E402
    average_rubric_scores,
    average_score_value,
    build_admin_metrics,
    high_risk_projects,
    load_records_or_mock,
    top_rule_counts,
)
from ui.styles import inject_styles  # noqa: E402
from ui.visuals import (  # noqa: E402
    render_hypergraph_visualization,
    render_rule_bar_chart,
    render_rule_status_cards,
    render_score_bar_chart,
    render_score_cards,
    render_summary_metrics,
)

DATA_CASES_DIR = ROOT / "data" / "cases"
OUTPUT_CASES_DIR = ROOT / "outputs" / "cases"
PROJECT_ARCHIVE_DIR = ROOT / "outputs" / "projects"
EXAMPLES_PATH = ROOT / "data" / "examples" / "project_inputs.jsonl"

COMPETITION_TEMPLATES: dict[str, dict[str, object]] = {
    "创新创业通用": {
        "weights": {"R1": 0.12, "R2": 0.10, "R3": 0.10, "R4": 0.08, "R5": 0.12, "R6": 0.12, "R7": 0.10, "R8": 0.10, "R9": 0.08, "R10": 0.08},
        "notes": "强调问题定义与价值闭环，适用于日常课程路演。",
    },
    "互联网+": {
        "weights": {"R1": 0.10, "R2": 0.12, "R3": 0.10, "R4": 0.10, "R5": 0.14, "R6": 0.14, "R7": 0.10, "R8": 0.08, "R9": 0.06, "R10": 0.06},
        "notes": "更看重市场与商业闭环，同时保持风险可控。",
    },
    "挑战杯": {
        "weights": {"R1": 0.10, "R2": 0.08, "R3": 0.10, "R4": 0.14, "R5": 0.10, "R6": 0.10, "R7": 0.10, "R8": 0.14, "R9": 0.08, "R10": 0.06},
        "notes": "更重视可落地性、社会价值与合规边界。",
    },
    "数学建模导向": {
        "weights": {"R1": 0.08, "R2": 0.08, "R3": 0.10, "R4": 0.08, "R5": 0.08, "R6": 0.16, "R7": 0.10, "R8": 0.10, "R9": 0.10, "R10": 0.12},
        "notes": "更关注指标定义、约束严谨性与财务一致性。",
    },
}

GHOSTWRITING_MARKERS = (
    "代写",
    "直接写",
    "帮我写完",
    "写一篇",
    "可直接提交",
    "不用我改",
    "1000字",
    "2000字",
)

OFF_TOPIC_MARKERS = (
    "忽略以上",
    "爬虫",
    "抓取电商数据",
    "写一段python",
    "只要代码",
)

EMOTIONAL_MARKERS = (
    "太难",
    "不想思考",
    "随便",
    "交差",
    "帮我直接写完",
)


@st.cache_resource
def build_pipeline() -> ProjectCoachPipeline:
    return ProjectCoachPipeline()


@st.cache_resource
def build_conversation_agent() -> ConversationAgent:
    return ConversationAgent()


@st.cache_resource
def build_learning_agent() -> LearningTutorAgent:
    return LearningTutorAgent()


@st.cache_resource
def build_idea_agent() -> IdeaCoachAgent:
    return IdeaCoachAgent()


@st.cache_resource
def build_rule_engine() -> RuleEngine:
    return RuleEngine()


def ensure_env_loaded() -> None:
    load_env_file(override=True)


def ensure_app_state() -> None:
    init_auth_state(st.session_state)
    st.session_state.setdefault("active_section", SECTION_STUDENT)
    st.session_state.setdefault("auth_view", "login")
    st.session_state.setdefault("student_result", None)
    st.session_state.setdefault("student_last_project_id", None)
    st.session_state.setdefault("student_draft_project_id", f"p-{uuid4().hex[:8]}")
    st.session_state.setdefault("idea_project_id", None)
    st.session_state.setdefault("idea_workspace", None)
    st.session_state.setdefault("idea_messages", [])
    st.session_state.setdefault("idea_output", None)
    st.session_state.setdefault("idea_debug", None)
    st.session_state.setdefault("chat_sessions", [])
    st.session_state.setdefault("active_chat_id", None)
    st.session_state.setdefault("learning_reply", "")
    st.session_state.setdefault("learning_debug", None)
    st.session_state.setdefault("competition_template", list(COMPETITION_TEMPLATES.keys())[0])
    st.session_state.setdefault(
        "teacher_intervention",
        {"enabled": False, "style": "严谨提问", "required_case": "", "note": ""},
    )
    st.session_state.setdefault("unauthorized_attempts", [])
    if not st.session_state["chat_sessions"]:
        create_chat_session()


def load_examples() -> list[dict]:
    if not EXAMPLES_PATH.exists():
        return []
    rows = []
    for line in EXAMPLES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_project_archives() -> list[str]:
    if not PROJECT_ARCHIVE_DIR.exists():
        return []
    files = sorted(PROJECT_ARCHIVE_DIR.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [path.stem for path in files]


def load_project_payload(project_id: str) -> dict:
    path = PROJECT_ARCHIVE_DIR / f"{project_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def create_chat_session() -> str:
    session_id = f"c-{uuid4().hex[:8]}"
    st.session_state["chat_sessions"].insert(0, {"id": session_id, "title": "新会话", "messages": []})
    st.session_state["active_chat_id"] = session_id
    return session_id


def get_active_chat_session() -> dict:
    for session in st.session_state["chat_sessions"]:
        if session["id"] == st.session_state["active_chat_id"]:
            return session
    st.session_state["active_chat_id"] = st.session_state["chat_sessions"][0]["id"]
    return st.session_state["chat_sessions"][0]


def delete_chat_session(session_id: str) -> None:
    st.session_state["chat_sessions"] = [item for item in st.session_state["chat_sessions"] if item["id"] != session_id]
    if not st.session_state["chat_sessions"]:
        create_chat_session()
    st.session_state["active_chat_id"] = st.session_state["chat_sessions"][0]["id"]


def update_chat_title(session: dict) -> None:
    user_messages = [item["content"] for item in session["messages"] if item["role"] == "user" and item["content"].strip()]
    if not user_messages:
        session["title"] = "新会话"
        return
    title = user_messages[0].replace("\n", " ").strip()
    session["title"] = title[:18] + ("..." if len(title) > 18 else "")


def split_assistant_reply(content: str) -> tuple[str, str | None]:
    marker = "\n\n`model="
    if marker not in content:
        return content, None
    main, meta = content.split(marker, 1)
    return main, f"`model={meta}"


def should_block_ghostwriting(question: str) -> bool:
    normalized = question.strip().lower()
    return any(marker in normalized for marker in GHOSTWRITING_MARKERS)


def build_ghostwriting_reply() -> str:
    return (
        "我不能直接代写可提交内容，但可以用启发式方式帮你快速完成。\\n\\n"
        "请先回答这三个问题：\\n"
        "1. 你要交付的版本（路演稿/BP/问卷）是哪一种？\\n"
        "2. 你最缺的是哪一块：用户证据、商业模式还是财务测算？\\n"
        "3. 你希望本轮先产出哪一个最小成果（只选一个）？"
    )


def build_emotional_redirect_reply() -> str:
    return (
        "先不追求完整 BP，我们把任务缩到最小步。\\n\\n"
        "你现在只做一件事：写 3 句话。\\n"
        "1. 你的目标用户是谁。\\n"
        "2. 用户最痛的问题是什么。\\n"
        "3. 你下一周准备验证的唯一假设是什么。\\n\\n"
        "完成这三句后，我再帮你继续拆下一步。"
    )


def detect_invalid_project_text(text: str) -> str | None:
    cleaned = text.strip()
    if len(cleaned) < 12 or len(re.findall(r"[\u4e00-\u9fffA-Za-z]", cleaned)) < 8:
        return "未检测到有效的项目信息，请补充“目标用户、核心问题、解决方案、获客渠道”后再提交。"
    if any(marker in cleaned.lower() for marker in OFF_TOPIC_MARKERS):
        return "检测到偏离双创场景的请求。请回到创业项目诊断：先描述你的用户、问题和方案。"
    if any(marker in cleaned for marker in EMOTIONAL_MARKERS):
        return "先别着急交完整稿。请先提交最小信息：目标用户、核心问题、一个可验证假设。"
    return None


def log_unauthorized_attempt(role: str | None, requested: str | None, redirected: str | None) -> None:
    if not requested or not redirected or requested == redirected:
        return
    attempts: list[dict] = st.session_state.setdefault("unauthorized_attempts", [])
    attempts.insert(
        0,
        {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "role": role or "anonymous",
            "requested": requested,
            "redirected_to": redirected,
        },
    )
    st.session_state["unauthorized_attempts"] = attempts[:100]


def infer_project_stage(detected_rules: list[dict]) -> str:
    status_map = {item.get("rule_id"): item.get("status") for item in detected_rules if isinstance(item, dict)}
    if status_map.get("H9") in {"fail", "warning"}:
        return "想法期"
    if status_map.get("H10") in {"fail", "warning"} or status_map.get("H15") in {"fail", "warning"}:
        return "原型期"
    return "验证期"


def build_learning_tutor_structured_output(question: str, project_hint: str, kg_nodes: list[dict]) -> str:
    normalized = question.lower()
    concept = "通用创业概念"
    definition = "把抽象概念转成可验证的项目动作：有对象、有指标、有时间边界。"
    example = f"结合你的项目（{project_hint}），先把“谁痛、痛多深、如何验证”写成三列表。"
    mistakes = [
        "只写概念定义，不落到你的项目场景。",
        "只写结论，不给可验证证据。",
        "一次塞入多个任务，导致执行失败。",
    ]
    task = "请只完成一件事：写一版“问题-证据-指标”单页。"
    artifact = "一页表格（问题、目标用户、证据来源、验证指标、截止时间）。"
    criteria = [
        "至少包含 1 个明确用户群体与 1 个可量化指标。",
        "证据来源可追溯（访谈/问卷/行为数据至少一类）。",
        "任务边界清楚，24 小时内可完成。"
    ]

    if "tam" in normalized or "sam" in normalized or "som" in normalized:
        concept = "TAM / SAM / SOM"
        definition = "TAM 是总市场，SAM 是可服务市场，SOM 是你当前阶段可拿到的市场。"
        example = f"{project_hint} 可以先按“全国-本省-首批试点”三层估算 TAM/SAM/SOM。"
        mistakes = [
            "把 TAM 直接当可拿到市场。",
            "没有说明口径和时间边界。",
            "SOM 与团队资源规模不匹配。"
        ]
        task = "只做一张 TAM/SAM/SOM 口径表，并写清每个数字来源。"
        artifact = "一页市场口径表（定义、数值、来源链接、计算过程）。"
    elif "mvp" in normalized:
        concept = "MVP"
        definition = "MVP 是最小可行产品，目标是最快验证关键假设，而不是做完整功能。"
        example = f"{project_hint} 的 MVP 可先验证“用户是否愿意持续使用”而非一次性做全功能。"
        mistakes = [
            "把 MVP 做成完整版产品。",
            "没有定义验证指标。",
            "验证周期过长，反馈闭环太慢。"
        ]
        task = "只定义 1 个 MVP 假设和 1 轮 7 天验证计划。"
        artifact = "MVP 假设卡（假设、验证动作、样本量、判定阈值、复盘时间）。"

    kg_names = [node.get("name", "unknown") for node in kg_nodes[:3]]
    return (
        f"Definition:\n{definition}\n\n"
        f"Example:\n{example}\n\n"
        f"Common Mistakes:\n- {mistakes[0]}\n- {mistakes[1]}\n- {mistakes[2]}\n\n"
        f"Practice Task:\n- {task}\n\n"
        f"Expected Artifact:\n- {artifact}\n\n"
        f"Evaluation Criteria:\n- {criteria[0]}\n- {criteria[1]}\n- {criteria[2]}\n\n"
        f"参考 KG 节点：{', '.join(kg_names)}（概念：{concept}）"
    )


def build_competition_item_reports(
    rubric_scores: list[dict],
    rubric_meta_map: dict[str, dict],
) -> list[dict[str, str]]:
    reports: list[dict[str, str]] = []
    for item in rubric_scores:
        rubric_id = item.get("rubric_id", "unknown")
        score = int(item.get("score", 0))
        meta = rubric_meta_map.get(rubric_id, {})
        required_fields: list[str] = meta.get("required_evidence", []) if isinstance(meta.get("required_evidence"), list) else []
        common_mistakes: list[str] = meta.get("common_mistakes", []) if isinstance(meta.get("common_mistakes"), list) else []

        evidence_fields = {
            ev.get("field")
            for ev in item.get("evidence", [])
            if isinstance(ev, dict) and ev.get("field")
        }
        missing = [field for field in required_fields if field not in evidence_fields]
        if score <= 2 and not missing:
            missing = common_mistakes[:1] or ["证据链未覆盖该维度的关键字段"]

        if not missing:
            missing_text = "当前维度证据基本齐全。"
            fix_24h = "补充 1 条最新验证数据并复核该维度评分依据。"
            fix_72h = "完成一次小范围迭代验证并更新证据链。"
        else:
            missing_text = "；".join(missing)
            fix_24h = f"补齐最关键缺口：{missing[0]}，并提交对应证据。"
            fix_72h = "按缺口完成扩展验证：补样本、补对照、补复盘，并更新评分。"

        reports.append(
            {
                "name": item.get("name", rubric_id),
                "estimated_score": f"{score}/5",
                "missing_evidence": missing_text,
                "fix_24h": fix_24h,
                "fix_72h": fix_72h,
            }
        )
    return reports


def compute_capability_profile(messages: list[dict]) -> dict:
    user_turns = [item.get("content", "") for item in messages if item.get("role") == "user"]
    joined = "\n".join(user_turns).lower()
    depth_score = min(5, max(1, len(user_turns)))
    empathy = 2 + (1 if any(token in joined for token in ["用户", "痛点", "需求"]) else 0) + (1 if "访谈" in joined else 0)
    ideation = 2 + (1 if any(token in joined for token in ["方案", "功能", "原型"]) else 0) + (1 if "mvp" in joined else 0)
    business = 2 + (1 if any(token in joined for token in ["定价", "收入", "成本", "ltv", "cac"]) else 0) + (1 if "盈利" in joined else 0)
    execution = 2 + (1 if any(token in joined for token in ["里程碑", "试点", "计划"]) else 0) + (1 if "时间" in joined else 0)
    logic = 2 + (1 if any(token in joined for token in ["因为", "所以", "如果"]) else 0) + (1 if depth_score >= 3 else 0)
    return {
        "痛点发现(Empathy)": min(5, empathy),
        "方案策划(Ideation)": min(5, ideation),
        "商业建模(Business)": min(5, business),
        "资源执行(Execution)": min(5, execution),
        "逻辑表达(Logic)": min(5, logic),
    }


def store_idea_response(response, *, seed_text: str | None = None, user_text: str | None = None, reset_messages: bool = False) -> None:
    if reset_messages:
        st.session_state["idea_messages"] = []
        if seed_text and seed_text.strip():
            st.session_state["idea_messages"].append({"role": "user", "content": seed_text.strip()})
    elif user_text and user_text.strip():
        st.session_state.setdefault("idea_messages", []).append({"role": "user", "content": user_text.strip()})
    st.session_state.setdefault("idea_messages", []).append({"role": "assistant", "content": response.reply})
    st.session_state["idea_workspace"] = response.workspace.model_dump(mode="json")
    st.session_state["idea_output"] = response.structured_output.model_dump(mode="json")
    st.session_state["idea_debug"] = {
        "agent_name": "idea_coach_agent",
        "model": response.model,
        "used_llm": response.used_llm,
        "workspace": response.workspace.model_dump(mode="json"),
        "structured_output": response.structured_output.model_dump(mode="json"),
    }


def reset_idea_session(seed_text: str = "") -> None:
    response = build_idea_agent().bootstrap(seed_text)
    st.session_state["idea_project_id"] = st.session_state.get("student_draft_project_id") or f"p-{uuid4().hex[:8]}"
    store_idea_response(response, seed_text=seed_text, reset_messages=True)


def get_idea_workspace() -> IdeaWorkspace | None:
    payload = st.session_state.get("idea_workspace")
    if not payload:
        return None
    try:
        return IdeaWorkspace.model_validate(payload)
    except Exception:
        return None


def run_diagnosis_from_text(project_text: str, project_id: str) -> None:
    user = current_user(st.session_state) or {"username": "student"}
    st.session_state["student_draft_project_id"] = project_id
    output = build_pipeline().run(
        ProjectCoachRequest(
            user_id=user["username"],
            project_id=project_id,
            project_text=project_text.strip(),
        )
    )
    st.session_state["student_result"] = {
        "request": {
            "user_id": user["username"],
            "project_id": project_id,
            "project_text": project_text.strip(),
        },
        "output": output.model_dump(mode="json"),
    }
    st.session_state["student_last_project_id"] = project_id


def render_login_page() -> None:
    st.markdown('<div class="login-shell">', unsafe_allow_html=True)
    hero_col, panel_col = st.columns([1.34, 0.9], gap="large")

    with hero_col:
        st.markdown(
            """
            <div class="auth-copy">
              <div class="auth-kicker">Unified Workflow</div>
              <h1 class="auth-title">把诊断、追问与评分<br/>放进同一条<br/>工作流里。</h1>
              <div class="auth-subtitle">
                学生先提交项目草案，系统完成初步诊断、规则校验与路演评分；教师再基于同一条证据链查看班级风险、批改结果和干预策略。
              </div>
              <div class="auth-visual">
                <div class="auth-visual-content">
                  <div class="auth-ribbon">学生诊断 → 教师洞察 → 管理配置</div>
                  <div class="auth-scene-line">初步诊断：渠道与目标用户存在错位，建议先补第一批真实访谈与转化证据。</div>
                  <div class="auth-scene-line alt">教师端已同步看到规则命中、评分缺口和下一步唯一任务。</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with panel_col:
        st.markdown('<div class="login-panel-scope"></div>', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="login-title">登录或注册</div>
            <div class="login-copy">
              未登录用户不能访问核心页面。当前先使用本地 mock 认证，后续可直接替换为正式鉴权。
            </div>
            """,
            unsafe_allow_html=True,
        )

        login_col, register_col = st.columns(2)
        if login_col.button("登录", key="auth_view_login", use_container_width=True, type="primary"):
            st.session_state["auth_view"] = "login"
            st.rerun()
        if register_col.button("注册", key="auth_view_register", use_container_width=True, type="secondary"):
            st.session_state["auth_view"] = "register"
            st.rerun()

        if st.session_state.get("auth_view") == "register":
            register_role = st.selectbox("注册角色", ["student", "teacher"], format_func=lambda item: "学生" if item == "student" else "教师")
            display_name = st.text_input("显示名称", placeholder="例如：张同学 / 李老师", key="register_display_name")
            username = st.text_input("新用户名", placeholder="至少 3 位", key="register_username")
            password = st.text_input("新密码", type="password", placeholder="至少 6 位", key="register_password")
            confirm_password = st.text_input("确认密码", type="password", key="register_confirm_password")
            submitted = st.button("注册并登录", use_container_width=True, type="primary", key="register_submit")
            if submitted:
                if password != confirm_password:
                    st.error("两次输入的密码不一致。")
                else:
                    ok, message, user = register_user(
                        st.session_state,
                        username=username,
                        password=password,
                        role=register_role,
                        display_name=display_name,
                    )
                    if ok and user:
                        login_user(st.session_state, user)
                        st.rerun()
                    st.error(message)
        else:
            role = st.selectbox(
                "角色",
                ["student", "teacher", "admin"],
                format_func=lambda item: {"student": "学生", "teacher": "教师", "admin": "管理员"}[item],
            )
            default_user = {"student": "student", "teacher": "teacher", "admin": "admin"}[role]
            default_pwd = {"student": "student123", "teacher": "teacher123", "admin": "admin123"}[role]
            username = st.text_input("用户名", value=default_user, key="login_username")
            password = st.text_input("密码", value=default_pwd, type="password", key="login_password")
            submitted = st.button("进入系统", use_container_width=True, type="primary", key="login_submit")
            st.markdown(
                """
                <div class="login-note">
                  默认账号：<br/>
                  student / student123<br/>
                  teacher / teacher123<br/>
                  admin / admin123
                </div>
                """,
                unsafe_allow_html=True,
            )
            if submitted:
                user = authenticate(st.session_state, username=username, password=password, role=role)
                if user:
                    login_user(st.session_state, user)
                    st.rerun()
                st.error("用户名、密码或角色不匹配。")

    st.markdown("</div>", unsafe_allow_html=True)


def render_sidebar() -> None:
    user = current_user(st.session_state)
    if not user:
        return

    role = user["role"]
    if role == ROLE_STUDENT:
        allowed_sections = (SECTION_STUDENT,)
    elif role == ROLE_ADMIN:
        allowed_sections = (SECTION_ADMIN, SECTION_TEACHER, SECTION_CENTER)
    else:
        allowed_sections = (SECTION_TEACHER, SECTION_CENTER)

    st.sidebar.markdown('<div class="sidebar-brand">Startup Edu Agent</div>', unsafe_allow_html=True)
    st.sidebar.markdown(
        '<div class="sidebar-copy">统一学生端、教师端与功能中心交互，管理端负责账号与全局看板。</div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown('<div class="sidebar-section">工作区</div>', unsafe_allow_html=True)
    for section in allowed_sections:
        if st.sidebar.button(section, use_container_width=True, key=f"nav_{section}", type="secondary"):
            st.session_state["active_section"] = section
            st.rerun()

    if role == ROLE_STUDENT:
        st.sidebar.markdown('<div class="sidebar-section">会话</div>', unsafe_allow_html=True)
        if st.sidebar.button("新建会话", use_container_width=True, key="new_chat_sidebar", type="secondary"):
            create_chat_session()
            st.rerun()

        for session in st.session_state["chat_sessions"]:
            active_prefix = "● " if session["id"] == st.session_state.get("active_chat_id") else ""
            label = f"{active_prefix}{session['title']}"
            if st.sidebar.button(label, use_container_width=True, key=f"pick_{session['id']}", type="secondary"):
                st.session_state["active_chat_id"] = session["id"]
                st.rerun()

    st.sidebar.markdown(
        f"""
        <div class="sidebar-card">
          <div class="metric-label">当前账号</div>
          <div class="metric-value" style="font-size:1.03rem;">{html.escape(user["display_name"])}</div>
          <div class="mini-note">
            用户名：{html.escape(user["username"])}<br/>
            角色：{html.escape(user["role"])}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.sidebar.button("退出登录", use_container_width=True, key="logout", type="secondary"):
        logout_user(st.session_state)
        st.rerun()


def render_status_panel() -> None:
    ensure_env_loaded()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    st.markdown(
        f"""
        <div class="surface-card">
          <div class="surface-title">环境状态</div>
          <div class="surface-copy">
            API Key：{"已配置" if api_key else "未配置"}<br/>
            Chat Base URL：{html.escape(os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))}<br/>
            OCR Base URL：{html.escape(os.getenv("DEEPSEEK_OCR_BASE_URL", "未配置"))}<br/>
            案例索引目录：{html.escape(os.getenv("CASE_INDEX_DIR", "outputs/cases/index"))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    recent_events = list(reversed(RuntimeLogger().read_recent(limit=12)))
    with st.expander("最近运行日志", expanded=False):
        if recent_events:
            rows = [
                {
                    "time": item.get("timestamp"),
                    "agent": item.get("agent_name"),
                    "event": item.get("event"),
                    "level": item.get("level"),
                    "run_id": item.get("run_id"),
                }
                for item in recent_events
            ]
            st.dataframe(rows, use_container_width=True, hide_index=True)
            st.json(recent_events[0])
        else:
            st.write("暂无运行日志。")


def render_student_diagnosis_panel() -> None:
    user = current_user(st.session_state) or {"username": "student"}
    examples = load_examples()
    example_labels = ["手动输入"] + [f"{item.get('project_id') or item.get('user_id')} 示例" for item in examples]

    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A2/A3/A4</div>
          <div class="hero-title">项目诊断与超图一致性检查</div>
          <div class="hero-copy">
            先提交项目文本，系统会返回当前诊断、规则命中和下一步唯一任务，再用于后续追问优化。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([1.42, 0.88])
    with left_col:
        st.markdown('<div class="surface-title">项目输入</div>', unsafe_allow_html=True)
        selected_example = st.selectbox("载入示例", example_labels, index=0, key="student_example")
        default_text = ""
        default_project_id = st.session_state.get("student_draft_project_id")
        if selected_example != "手动输入":
            example = examples[example_labels.index(selected_example) - 1]
            default_text = example["project_text"]
            default_project_id = example.get("project_id") or default_project_id

        with st.form("student_diagnosis_form"):
            project_id = st.text_input("项目编号", value=default_project_id)
            project_text = st.text_area("项目文本", value=default_text, height=260, placeholder="粘贴项目描述")
            submitted = st.form_submit_button("生成初步诊断", use_container_width=True, type="primary")

        if submitted:
            blocked_message = detect_invalid_project_text(project_text)
            if blocked_message:
                st.warning(blocked_message)
            else:
                with st.spinner("正在生成诊断..."):
                    output = build_pipeline().run(
                        ProjectCoachRequest(
                            user_id=user["username"],
                            project_id=project_id,
                            project_text=project_text.strip(),
                        )
                    )
                st.session_state["student_result"] = {
                    "request": {
                        "user_id": user["username"],
                        "project_id": project_id,
                        "project_text": project_text.strip(),
                    },
                    "output": output.model_dump(mode="json"),
                }
                st.session_state["student_last_project_id"] = project_id
                st.session_state["student_draft_project_id"] = f"p-{uuid4().hex[:8]}"
                st.success("初步诊断已生成。")

    with right_col:
        st.markdown(
            """
            <div class="surface-card">
              <div class="surface-title">交互方式</div>
              <div class="surface-copy">
                1. 填写项目草案并生成诊断<br/>
                2. 查看规则命中与评分<br/>
                3. 在对话区继续追问并修正
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        render_status_panel()

    payload = st.session_state.get("student_result")
    if not payload:
        st.markdown('<div class="placeholder-card">还没有诊断结果，请先生成一次。</div>', unsafe_allow_html=True)
        return

    output = payload["output"]
    rubric_scores = output.get("rubric_scores", [])
    detected_rules = output.get("detected_rules", [])
    evidence_used = output.get("evidence_used", [])
    project_stage = infer_project_stage(detected_rules)
    avg_score = round(sum(item["score"] for item in rubric_scores) / len(rubric_scores), 2) if rubric_scores else 0.0
    non_pass_count = len([item for item in detected_rules if item.get("status") != "pass"])

    render_summary_metrics(
        [
            {"label": "项目阶段", "value": project_stage, "footnote": "用于 A2 阶段判断"},
            {"label": "当前诊断", "value": output.get("current_diagnosis", "暂无"), "footnote": "最优先处理的核心问题"},
            {"label": "下一步唯一任务", "value": output.get("next_task", "暂无"), "footnote": "严格保持单任务输出"},
            {"label": "综合概览", "value": f"平均评分 {avg_score}/5", "footnote": f"非通过规则 {non_pass_count} 条 · 证据 {len(evidence_used)} 条"},
        ]
    )

    result_tab, detail_tab, markdown_tab = st.tabs(["结果总览", "规则与评分", "Markdown 报告"])
    with result_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">影响说明</div>', unsafe_allow_html=True)
        st.write(output.get("impact", "暂无影响说明。"))
        st.markdown('<div class="surface-title" style="margin-top:1rem;">引用证据</div>', unsafe_allow_html=True)
        if evidence_used:
            for item in evidence_used:
                st.write(f"- {format_evidence(item)}")
        else:
            st.info("暂无证据引用。")
        st.markdown("</div>", unsafe_allow_html=True)

    with detail_tab:
        score_col, rule_col = st.columns([1, 1])
        with score_col:
            st.markdown('<div class="surface-card">', unsafe_allow_html=True)
            st.markdown('<div class="surface-title">Rubric 评分</div>', unsafe_allow_html=True)
            render_score_cards(rubric_scores)
            render_score_bar_chart(rubric_scores)
            st.markdown("</div>", unsafe_allow_html=True)
        with rule_col:
            st.markdown('<div class="surface-card">', unsafe_allow_html=True)
            st.markdown('<div class="surface-title">规则状态</div>', unsafe_allow_html=True)
            render_rule_status_cards(
                [
                    {"rule_id": item.get("rule_id", "unknown"), "status": item.get("status", "pass"), "message": item.get("message", "")}
                    for item in detected_rules
                ]
            )
            st.markdown("</div>", unsafe_allow_html=True)

    with markdown_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown(output.get("markdown_report", "暂无 Markdown 报告。"))
        st.markdown("</div>", unsafe_allow_html=True)

    debug_text = ((output.get("rendered_views") or {}) if isinstance(output, dict) else {}).get("debug")
    if debug_text:
        with st.expander("调试日志（A3/A4 链路）", expanded=False):
            try:
                st.json(json.loads(debug_text))
            except Exception:
                st.code(debug_text)


def render_student_idea_panel() -> None:
    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A0</div>
          <div class="hero-title">Idea 孵化与苏格拉底式追问</div>
          <div class="hero-copy">
            从模糊想法出发，按超图规则逐轮追问问题、用户、方案、证据与落地路径，信息足够后自动收束成可诊断草案。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    action_col, info_col = st.columns([1.05, 0.95])
    with action_col:
        with st.form("idea_bootstrap_form"):
            seed_text = st.text_area(
                "一句话描述你的 idea",
                height=120,
                placeholder="例如：我想做一个帮考研学生自动整理资料并生成复习卡片的工具。",
            )
            submitted = st.form_submit_button("启动 A0 追问", use_container_width=True, type="primary")
        if submitted:
            reset_idea_session(seed_text.strip())
            st.rerun()

    with info_col:
        st.markdown(
            """
            <div class="surface-card">
              <div class="surface-title">A0 工作方式</div>
              <div class="surface-copy">
                1. 每轮追问都绑定当前高优先级规则<br/>
                2. 回答尽量按模板字段填写，便于系统收束成草案<br/>
                3. 当核心字段齐备后，可一键送入 A2-A4 诊断
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not st.session_state.get("idea_workspace"):
        st.markdown('<div class="placeholder-card">先输入一句话 idea，A0 会从问题、用户与最小方案开始追问。</div>', unsafe_allow_html=True)
        return

    output = st.session_state.get("idea_output") or {}
    messages = st.session_state.get("idea_messages") or []
    focus_rule = output.get("focus_rule_id") or "已通过基础约束"
    completion_ratio = float(output.get("completion_ratio", 0.0) or 0.0)
    project_id = st.session_state.get("idea_project_id") or st.session_state.get("student_draft_project_id")
    generated_project_text = output.get("generated_project_text", "")

    render_summary_metrics(
        [
            {"label": "阶段", "value": output.get("stage_label", "Idea 火花"), "footnote": "A0 当前收束阶段"},
            {"label": "完成度", "value": f"{round(completion_ratio * 100)}%", "footnote": "基于关键字段覆盖率估算"},
            {"label": "当前规则焦点", "value": focus_rule, "footnote": "本轮追问绑定的超边规则"},
            {"label": "项目编号", "value": project_id or "未生成", "footnote": "A0 到 A2-A4 的共享草案编号"},
        ]
    )

    thread_col, draft_col = st.columns([1.18, 0.82], gap="large")
    with thread_col:
        if st.button("重新开始 A0", key="idea_reset_button", use_container_width=True, type="secondary"):
            st.session_state["idea_workspace"] = None
            st.session_state["idea_messages"] = []
            st.session_state["idea_output"] = None
            st.session_state["idea_debug"] = None
            st.session_state["idea_project_id"] = None
            st.rerun()

        st.markdown('<div class="chat-thread">', unsafe_allow_html=True)
        for message in messages:
            if message["role"] == "user":
                st.markdown(f'<div class="chat-bubble-user">你：{html.escape(message["content"])}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="chat-bubble-assistant">{html.escape(message["content"]).replace(chr(10), "<br/>")}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        with st.form("idea_turn_form", clear_on_submit=True):
            answer_placeholder = output.get("answer_template") or "继续补充这一轮最关键的信息。"
            user_text = st.text_area("本轮回答", height=150, placeholder=answer_placeholder)
            turn_submitted = st.form_submit_button("提交这一轮回答", use_container_width=True, type="primary")
        if turn_submitted:
            if not user_text.strip():
                st.warning("请先输入这一轮回答。")
            else:
                workspace = get_idea_workspace()
                if workspace is None:
                    st.warning("A0 会话状态已失效，请重新启动。")
                else:
                    response = build_idea_agent().step(workspace, user_text.strip())
                    store_idea_response(response, user_text=user_text.strip())
                    st.rerun()

    with draft_col:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">当前草案</div>', unsafe_allow_html=True)
        if generated_project_text:
            st.code(generated_project_text, language="text")
        else:
            st.info("当前信息还不足以收束出草案。")
        diagnose_disabled = not bool(output.get("ready_for_generation")) or not generated_project_text.strip()
        if st.button("送入 A2-A4 诊断", key="idea_to_diagnosis", use_container_width=True, type="primary", disabled=diagnose_disabled):
            with st.spinner("正在把 A0 草案送入诊断链路..."):
                run_diagnosis_from_text(generated_project_text, project_id or f"p-{uuid4().hex[:8]}")
            st.success("A0 草案已送入 A2-A4 诊断。现在可以切到“项目诊断”或“A1”继续看结果。")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">超图焦点</div>', unsafe_allow_html=True)
        hypergraph_focus = output.get("hypergraph_focus") or {}
        st.write(output.get("overview", "暂无概览。"))
        if hypergraph_focus.get("retrieved_context_nodes"):
            st.write(f"本轮上下文字段：{', '.join(hypergraph_focus['retrieved_context_nodes'])}")
        if hypergraph_focus.get("retrieved_heterogeneous_subgraph"):
            for item in hypergraph_focus["retrieved_heterogeneous_subgraph"]:
                st.write(
                    f"- {item.get('rule_id', 'unknown')} / {item.get('edge_type', 'Hypergraph_Edge')} / "
                    f"{', '.join(item.get('required_fields', [])) or '无字段'}"
                )
        st.markdown("</div>", unsafe_allow_html=True)

        idea_debug = st.session_state.get("idea_debug")
        if idea_debug:
            with st.expander("调试日志（A0 规则追问）", expanded=False):
                st.json(idea_debug)


def render_student_learning_panel() -> None:
    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A1</div>
          <div class="hero-title">学习辅导与反代写护栏</div>
          <div class="hero-copy">
            支持概念讲解、常见错误提示与练习建议。若检测到代写请求，将自动切换到启发式追问模式。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("learning_form"):
        question = st.text_area("学习问题", height=150, placeholder="例如：什么是 TAM/SAM/SOM，应该如何落到我的项目里？")
        submitted = st.form_submit_button("生成辅导建议", use_container_width=True, type="primary")

    if submitted:
        if not question.strip():
            st.warning("请先输入问题。")
        else:
            user = current_user(st.session_state) or {}
            payload = st.session_state.get("student_result") or {}
            request = payload.get("request") if isinstance(payload, dict) else {}
            response = build_learning_agent().respond(
                question.strip(),
                user_id=user.get("username"),
                project_id=(request or {}).get("project_id") or st.session_state.get("student_last_project_id"),
                include_project_context=True,
            )
            st.session_state["learning_reply"] = response.reply
            st.session_state["learning_debug"] = {
                "agent_name": "learning_tutor_agent",
                "organizer_agent": "learning_response_organizer",
                "strategy_selected": response.structured_output.mode.value,
                "topic": response.structured_output.topic,
                "context_used": response.context_used,
                "context_project_id": response.context_project_id,
                "used_llm": response.used_llm,
                "model": response.model,
                "retrieved_kg_nodes": response.structured_output.retrieved_kg_nodes,
                "validation": response.validation.model_dump(mode="json"),
                "structured_output": response.structured_output.model_dump(mode="json"),
            }

    if st.session_state.get("learning_reply"):
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">辅导输出</div>', unsafe_allow_html=True)
        st.write(st.session_state["learning_reply"])
        st.markdown("</div>", unsafe_allow_html=True)
    learning_debug = st.session_state.get("learning_debug")
    if learning_debug:
        with st.expander("调试日志（A1 Agent + 约束）", expanded=False):
            st.json(learning_debug)


def render_student_competition_panel() -> None:
    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A5</div>
          <div class="hero-title">路演评分与动态 Rubric</div>
          <div class="hero-copy">切换赛事模板后，系统会按不同维度权重重新计算加权得分。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    payload = st.session_state.get("student_result")
    if not payload:
        st.markdown('<div class="placeholder-card">请先在“项目诊断”中生成一次结果，再进行路演评分。</div>', unsafe_allow_html=True)
        return

    template_names = list(COMPETITION_TEMPLATES.keys())
    current_template = st.session_state.get("competition_template", template_names[0])
    default_index = template_names.index(current_template) if current_template in template_names else 0
    template_name = st.selectbox("赛事模板", template_names, index=default_index)
    st.session_state["competition_template"] = template_name

    config = COMPETITION_TEMPLATES[template_name]
    weights: dict[str, float] = config["weights"]  # type: ignore[assignment]
    st.markdown(f'<div class="status-chip">{html.escape(str(config["notes"]))}</div>', unsafe_allow_html=True)

    rubric_scores = payload["output"].get("rubric_scores", [])
    rubric_meta_map = {item["rubric_id"]: item for item in build_pipeline().rubric_scorer.rubrics}
    weighted_sum = 0.0
    weight_total = 0.0
    weighted_rows = []
    for item in rubric_scores:
        rubric_id = item.get("rubric_id")
        weight = weights.get(rubric_id, 0.0)
        score = float(item.get("score", 0))
        weighted = round(score * weight, 3)
        weighted_rows.append({"name": f"{item.get('name')} (w={weight:.2f})", "score": weighted})
        weighted_sum += weighted
        weight_total += weight
    final_score = round((weighted_sum / weight_total), 2) if weight_total > 0 else 0.0
    item_reports = build_competition_item_reports(rubric_scores, rubric_meta_map)

    render_summary_metrics(
        [
            {"label": "模板", "value": template_name, "footnote": "动态切换评分口径"},
            {"label": "加权总分", "value": f"{final_score}/5", "footnote": "依据模板权重计算"},
            {"label": "维度覆盖率", "value": "100%", "footnote": "按当前 Rubric 完整覆盖"},
        ]
    )
    st.markdown('<div class="surface-card">', unsafe_allow_html=True)
    st.markdown('<div class="surface-title">加权维度得分</div>', unsafe_allow_html=True)
    render_score_bar_chart(weighted_rows, y_key="score")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="surface-card">', unsafe_allow_html=True)
    st.markdown('<div class="surface-title">A5 逐项评分报告</div>', unsafe_allow_html=True)
    for row in item_reports:
        st.markdown(
            f"""
            <div class="score-grid-card">
              <strong>{html.escape(row["name"])}</strong>
              <span><b>Estimated Score:</b> {html.escape(row["estimated_score"])}</span><br/>
              <span><b>Missing Evidence:</b> {html.escape(row["missing_evidence"])}</span><br/>
              <span><b>Minimal Fix (24h):</b> {html.escape(row["fix_24h"])}</span><br/>
              <span><b>Minimal Fix (72h):</b> {html.escape(row["fix_72h"])}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_student_page() -> None:
    idea_tab, diagnose_tab, learning_tab, competition_tab, chat_tab = st.tabs(
        ["Idea 孵化（A0）", "项目诊断（A2-A4）", "学习辅导（A1）", "路演评分（A5）", "追问对话"]
    )
    with idea_tab:
        render_student_idea_panel()
    with diagnose_tab:
        render_student_diagnosis_panel()
    with learning_tab:
        render_student_learning_panel()
    with competition_tab:
        render_student_competition_panel()
    with chat_tab:
        render_student_chat_panel()


def render_student_chat_panel() -> None:
    active_session = get_active_chat_session()
    archives = load_project_archives()
    last_project_id = st.session_state.get("student_last_project_id")
    archive_options = ["自动（最近）"] + archives
    default_index = archive_options.index(last_project_id) if last_project_id in archive_options else 0

    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">追问区</div>
          <div class="hero-title">围绕诊断结果继续优化</div>
          <div class="hero-copy">在同一会话里持续追问，便于形成版本迭代轨迹。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mode_col, context_col, source_col = st.columns([1, 1, 1.2])
    mode = mode_col.selectbox("模式", ["general", "reasoning"], index=0)
    include_context = context_col.checkbox("附带项目上下文", value=bool(last_project_id or archives))
    selected_archive = source_col.selectbox("上下文来源", archive_options, index=default_index, disabled=not include_context)
    intervention = st.session_state.get("teacher_intervention", {})
    if intervention.get("enabled"):
        st.markdown('<div class="status-chip">已应用教师干预策略</div>', unsafe_allow_html=True)

    st.markdown('<div class="chat-thread">', unsafe_allow_html=True)
    for message in active_session["messages"]:
        if message["role"] == "user":
            st.markdown(f'<div class="chat-bubble-user">你：{html.escape(message["content"])}</div>', unsafe_allow_html=True)
            continue
        reply_text, reply_meta = split_assistant_reply(message["content"])
        st.markdown(
            f"""
            <div class="chat-bubble-assistant">
              {reply_text}
              {f'<div class="assistant-meta">{html.escape(reply_meta)}</div>' if reply_meta else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    with st.form("student_chat_form", clear_on_submit=True):
        user_text = st.text_area("继续提问", height=120, placeholder="例如：基于刚才诊断，我下一步先补哪一个字段最有价值？")
        submitted = st.form_submit_button("发送消息", use_container_width=True, type="primary")

    if submitted and user_text.strip():
        active_session["messages"].append({"role": "user", "content": user_text.strip()})
        update_chat_title(active_session)
        model_messages = [ChatMessage(role=item["role"], content=item["content"]) for item in active_session["messages"]]
        if intervention.get("enabled"):
            system_note = (
                f"教师干预策略：{intervention.get('style', '严谨提问')}。"
                f" 必须引用教学案例：{intervention.get('required_case', '无强制案例')}。"
                f" 附加备注：{intervention.get('note', '无')}。"
            )
            model_messages = [ChatMessage(role="system", content=system_note)] + model_messages
        with st.spinner("正在生成回复..."):
            response = build_conversation_agent().chat(
                model_messages,
                mode=mode,
                user_id=(current_user(st.session_state) or {}).get("username"),
                include_project_context=include_context,
                project_id=None if selected_archive == "自动（最近）" else selected_archive,
            )
        context_info = f"context_used={response.context_used}"
        if response.context_project_id:
            context_info += f" context_project_id={response.context_project_id}"
        assistant_text = response.reply + f"\n\n`model={response.model} used_llm={response.used_llm} {context_info}`"
        active_session["messages"].append({"role": "assistant", "content": assistant_text})
        st.rerun()

    if len(st.session_state["chat_sessions"]) > 1:
        action_col, _ = st.columns([1, 5])
        if action_col.button("删除当前会话", key="delete_active_chat", type="tertiary"):
            delete_chat_session(active_session["id"])
            st.rerun()


def render_teacher_page() -> None:
    records, using_mock = load_records_or_mock(PROJECT_ARCHIVE_DIR)
    avg_scores = average_rubric_scores(records)
    rule_rows = top_rule_counts(records)
    risky_projects = high_risk_projects(records)
    selected_project_id = st.selectbox("选择项目", [record["project_id"] for record in records], index=0)
    selected_record = next(record for record in records if record["project_id"] == selected_project_id)

    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A6</div>
          <div class="hero-title">教师端评分、证据溯源与干预建议</div>
          <div class="hero-copy">聚合学生项目结果，支持单项目批改与班级层级风险洞察。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if using_mock:
        st.markdown('<div class="status-chip">当前使用 mock 数据占位；写入 outputs/projects/*.json 后会自动切换为真实数据。</div>', unsafe_allow_html=True)

    render_summary_metrics(
        [
            {"label": "项目总数", "value": str(len(records)), "footnote": "已归档可评估项目"},
            {"label": "高风险项目", "value": str(len(risky_projects)), "footnote": "命中 high_risk 规则"},
            {"label": "平均评分", "value": f"{average_score_value(records)}/5", "footnote": "全班 Rubric 综合均值"},
        ]
    )

    overview_tab, score_tab, assess_tab, intervention_tab, profile_tab, trace_tab = st.tabs(
        ["班级概览", "评分可视化", "批改报告(A6-1)", "干预配置(A6-3)", "能力画像(A6-4)", "证据溯源"]
    )
    with overview_tab:
        left_col, right_col = st.columns(2)
        with left_col:
            st.markdown('<div class="surface-title">平均 Rubric 评分</div>', unsafe_allow_html=True)
            render_score_bar_chart(avg_scores, y_key="average_score")
        with right_col:
            st.markdown('<div class="surface-title">规则触发分布</div>', unsafe_allow_html=True)
            render_rule_bar_chart(rule_rows)

        st.markdown('<div class="surface-title">A6-2 班级洞察</div>', unsafe_allow_html=True)
        top5 = rule_rows[:5]
        coverage = {
            "规则覆盖率(非 pass 命中)": f"{round((len(top5) / max(1, len(build_rule_engine().rule_specs))) * 100, 2)}%",
            "高风险项目占比": f"{round((len(risky_projects) / max(1, len(records))) * 100, 2)}%",
        }
        st.markdown("**Coverage Summary**")
        st.json(coverage)
        st.markdown("**Top 5 Common Mistakes**")
        if top5:
            for row in top5:
                st.write(f"- {row['rule_id']}: {row['count']} 次")
        else:
            st.write("- 暂无高频错误")
        st.markdown("**High-risk Projects**")
        if risky_projects:
            for project_id in risky_projects:
                st.write(f"- {project_id}")
        else:
            st.write("- 暂无 high_risk 项目")
        st.markdown("**Suggested Teaching Interventions**")
        if top5:
            st.write(f"- 下周先讲解 `{top5[0]['rule_id']}`，并布置对应修订模板练习。")
            st.write("- 课堂加入“证据链补全”环节，要求每队提交可追溯证据。")
        else:
            st.write("- 保持当前节奏，重点检查证据质量与执行计划。")
        rule_frequency = {row["rule_id"]: row["count"] for row in rule_rows}
        st.markdown("**统计信息(JSON)**")
        st.json(
            {
                "total_projects": len(records),
                "average_rubric_score": average_score_value(records),
                "rule_trigger_frequency": rule_frequency,
            }
        )

    with score_tab:
        chart_col, info_col = st.columns([1.15, 0.85])
        with chart_col:
            st.markdown('<div class="surface-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="surface-title">项目评分 · {html.escape(selected_project_id)}</div>', unsafe_allow_html=True)
            render_score_cards(selected_record.get("rubric_scores", []))
            render_score_bar_chart(selected_record.get("rubric_scores", []))
            st.markdown("</div>", unsafe_allow_html=True)
        with info_col:
            st.markdown('<div class="surface-card">', unsafe_allow_html=True)
            st.markdown('<div class="surface-title">诊断摘要</div>', unsafe_allow_html=True)
            st.write(selected_record.get("current_diagnosis"))
            st.markdown("**下一步建议**")
            st.write(selected_record.get("next_task"))
            st.markdown("**规则状态**")
            render_rule_status_cards(
                [{"rule_id": rule_id, "status": status, "message": ""} for rule_id, status in selected_record.get("rule_statuses", {}).items()]
            )
            st.markdown("</div>", unsafe_allow_html=True)

    with assess_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">A6-1 批改报告</div>', unsafe_allow_html=True)
        st.markdown("**Rubric Table**")
        st.dataframe(
            [
                {"Rubric": item.get("name"), "Score": item.get("score"), "Rationale": item.get("rationale")}
                for item in selected_record.get("rubric_scores", [])
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("**Evidence Trace**")
        payload = load_project_payload(selected_project_id)
        evidence_items = (payload.get("output") or {}).get("evidence_used", []) if payload else []
        if evidence_items:
            for item in evidence_items[:6]:
                st.write(f"- {format_evidence(item)}")
        else:
            st.write("- 暂无证据链（mock 数据可能无原文映射）")
        st.markdown("**Revision Suggestions**")
        st.write(f"- 优先修复：{selected_record.get('current_diagnosis', '暂无')}")
        st.write(f"- 下一步：{selected_record.get('next_task', '暂无')}")
        st.markdown("**Instructor Review Notes**")
        st.write("- 复核评分与证据一致性，确认低分维度已给出可执行修复路径。")
        st.markdown("</div>", unsafe_allow_html=True)

    with intervention_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">A6-3 教师反向干预配置</div>', unsafe_allow_html=True)
        intervention = st.session_state.get("teacher_intervention", {})
        enabled = st.checkbox("启用干预策略", value=bool(intervention.get("enabled")), key="teacher_intervention_enabled")
        style = st.selectbox("对话风格", ["严谨提问", "鼓励式引导", "证据优先"], index=0)
        required_case = st.text_input("强制引用案例/材料", value=str(intervention.get("required_case", "")))
        note = st.text_area("教师备注", value=str(intervention.get("note", "")), height=90)
        if st.button("保存干预策略", use_container_width=True, type="primary", key="save_intervention"):
            st.session_state["teacher_intervention"] = {
                "enabled": enabled,
                "style": style,
                "required_case": required_case.strip(),
                "note": note.strip(),
            }
            st.success("干预策略已保存，学生端新会话将实时生效。")
        st.write("当前策略：")
        st.json(st.session_state.get("teacher_intervention", {}))
        st.markdown("</div>", unsafe_allow_html=True)

    with profile_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">A6-4 三轮对话能力画像</div>', unsafe_allow_html=True)
        all_messages: list[dict] = []
        for session in st.session_state.get("chat_sessions", []):
            all_messages.extend(session.get("messages", []))
        user_turns = [item for item in all_messages if item.get("role") == "user"]
        if len(user_turns) < 3:
            st.info("当前有效对话轮次不足 3 轮，先在学生端完成多轮追问后再评估。")
        else:
            profile = compute_capability_profile(all_messages)
            st.markdown("**核心能力量化（0-5）**")
            st.json(profile)
            st.markdown("**三轮行为诊断**")
            st.write(f"- 第一轮（核心价值探测）：{user_turns[0].get('content', '')[:120]}")
            st.write(f"- 第二轮（逻辑压力测试）：{user_turns[1].get('content', '')[:120]}")
            st.write(f"- 第三轮（落地可行性）：{user_turns[2].get('content', '')[:120]}")
            st.markdown("**证据引用**")
            for item in user_turns[:3]:
                st.write(f'- "{item.get("content", "")[:120]}"')
        st.markdown("</div>", unsafe_allow_html=True)

    with trace_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">证据链（按项目）</div>', unsafe_allow_html=True)
        payload = load_project_payload(selected_project_id)
        evidence_items = (payload.get("output") or {}).get("evidence_used", []) if payload else []
        if evidence_items:
            for item in evidence_items:
                st.write(f"- {format_evidence(item)}")
        else:
            st.info("该项目暂无可展示证据链（可能来自 mock 数据）。")
        st.markdown("</div>", unsafe_allow_html=True)


def render_admin_page() -> None:
    records, _ = load_records_or_mock(PROJECT_ARCHIVE_DIR)
    users = st.session_state.get("auth_users", [])
    metrics = build_admin_metrics(records, users)

    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">A6-5</div>
          <div class="hero-title">管理端 · 全局看板与权限控制</div>
          <div class="hero-copy">支持用户角色管理、全局风险监控和越权拦截策略检查。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_summary_metrics(
        [
            {"label": "用户总数", "value": str(metrics["total_users"]), "footnote": "系统账号数量"},
            {"label": "项目总数", "value": str(metrics["total_projects"]), "footnote": "可统计项目数量"},
            {"label": "高风险项目", "value": str(metrics["high_risk_count"]), "footnote": "全局 high_risk 命中数"},
        ]
    )

    user_tab, monitor_tab, guard_tab = st.tabs(["用户与角色", "全局监控", "越权拦截"])
    with user_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">账号列表</div>', unsafe_allow_html=True)
        st.dataframe(
            [
                {"用户名": item["username"], "角色": item["role"], "显示名": item["display_name"]}
                for item in users
            ],
            use_container_width=True,
            hide_index=True,
        )

        usernames = [item["username"] for item in users]
        if usernames:
            pick_col, role_col, action_col = st.columns([1.4, 1.2, 1])
            selected_username = pick_col.selectbox("选择用户", usernames, key="admin_pick_user")
            selected_role = role_col.selectbox("目标角色", ["student", "teacher", "admin"], key="admin_pick_role")
            if action_col.button("更新角色", use_container_width=True, key="admin_update_role", type="primary"):
                for item in users:
                    if item["username"] == selected_username:
                        item["role"] = selected_role
                st.session_state["auth_users"] = users
                current = current_user(st.session_state)
                if current and current["username"] == selected_username:
                    current["role"] = selected_role
                    st.session_state["auth_user"] = current
                    st.session_state["active_section"] = ensure_authorized_section(current["role"], st.session_state.get("active_section"))
                st.success("角色已更新。")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    with monitor_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">角色分布</div>', unsafe_allow_html=True)
        st.json(metrics["role_counts"])
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">Top 规则风险</div>', unsafe_allow_html=True)
        if metrics["top_rules"]:
            render_rule_bar_chart(metrics["top_rules"])
        else:
            st.info("暂无规则触发数据。")
        st.markdown("</div>", unsafe_allow_html=True)

    with guard_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        st.markdown('<div class="surface-title">越权拦截状态</div>', unsafe_allow_html=True)
        st.write("- student 仅可访问学生端")
        st.write("- teacher 可访问教师端和功能中心")
        st.write("- admin 可访问管理端、教师端和功能中心")
        st.write("路由守卫已启用：未授权访问会自动跳回角色默认页面。")
        attempts = st.session_state.get("unauthorized_attempts", [])
        st.markdown("**Unauthorized Access Attempt 日志**")
        if attempts:
            st.dataframe(attempts, use_container_width=True, hide_index=True)
        else:
            st.write("- 暂无越权访问记录。")
        st.markdown("</div>", unsafe_allow_html=True)


def render_ingest_panel() -> None:
    st.markdown('<div class="surface-card">', unsafe_allow_html=True)
    st.markdown('<div class="surface-title">案例 OCR 与索引更新</div>', unsafe_allow_html=True)
    backend = st.selectbox("OCR Backend", options=["auto", "deepseek_ocr", "tesseract", "pdf_text"], index=0)
    uploaded_files = st.file_uploader("上传 PDF", type=["pdf"], accept_multiple_files=True)
    if st.button("保存并执行 Ingest", use_container_width=True, type="primary"):
        if not uploaded_files:
            st.warning("请至少上传一个 PDF。")
        else:
            DATA_CASES_DIR.mkdir(parents=True, exist_ok=True)
            saved_files = []
            for file in uploaded_files:
                target = DATA_CASES_DIR / file.name
                target.write_bytes(file.getbuffer())
                saved_files.append(target.name)
            stats = ingest_directory(DATA_CASES_DIR, OUTPUT_CASES_DIR, backend_name=backend)
            st.success(f"Ingest 完成：{stats.documents} 个文档，{stats.pages} 页，{stats.chunks} 个 chunk，backend={stats.backend}")
            st.write({"saved_files": saved_files})
    if st.button("重建索引（含结构化案例库）", use_container_width=True, key="rebuild_case_index", type="secondary"):
        structured_count = export_structured_chunks()
        stats = ingest_directory(DATA_CASES_DIR, OUTPUT_CASES_DIR, backend_name=backend)
        st.success(
            f"索引已重建：PDF 文档 {stats.documents} 个，索引 chunk {stats.chunks} 个，结构化案例 chunk {structured_count} 个。"
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_asset_precheck_panel(rule_engine: RuleEngine) -> None:
    report = build_asset_scale_report(
        rule_specs=rule_engine.rule_specs,
        competition_templates=COMPETITION_TEMPLATES,
    )
    rows = report["rows"]
    pass_count = report["pass_count"]
    total_count = report["total_count"]

    render_summary_metrics(
        [
            {"label": "预检通过项", "value": f"{pass_count}/{total_count}", "footnote": "对照 2.2 资产规模最低要求"},
            {"label": "案例 PDF 数量", "value": str(report["case_pdf_count"]), "footnote": "data/cases 中 PDF 文件数"},
            {"label": "结构化案例有效数", "value": str(next((row["当前值"] for row in rows if row["指标"] == "结构化案例数量"), 0)), "footnote": "data/case_library/structured_cases.jsonl"},
        ]
    )

    st.markdown('<div class="surface-card">', unsafe_allow_html=True)
    st.markdown('<div class="surface-title">资产规模预检（Schema & Asset Minimum Scale）</div>', unsafe_allow_html=True)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    invalid_case_ids: list[str] = report.get("invalid_case_ids", [])
    if invalid_case_ids:
        st.warning(f"发现 {len(invalid_case_ids)} 条结构化案例不合规：{', '.join(invalid_case_ids[:8])}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_function_center() -> None:
    rule_engine = build_rule_engine()
    st.markdown(
        """
        <div class="hero-card">
          <div class="hero-kicker">Function Center</div>
          <div class="hero-title">约束可视化、案例 OCR 与系统配置</div>
          <div class="hero-copy">功能中心不承载学生主交互，只保留规则、约束、资产预检、索引和环境配置能力。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    hyper_tab, ingest_tab, precheck_tab, config_tab = st.tabs(["超图约束可视化", "案例 OCR", "资产预检", "系统配置"])
    with hyper_tab:
        st.markdown('<div class="surface-card">', unsafe_allow_html=True)
        render_hypergraph_visualization(rule_engine.rule_specs)
        st.caption("仅展示超图视图，规则详情默认隐藏。")
        st.markdown("</div>", unsafe_allow_html=True)
    with ingest_tab:
        render_ingest_panel()
    with precheck_tab:
        render_asset_precheck_panel(rule_engine)
    with config_tab:
        render_status_panel()


def main() -> None:
    st.set_page_config(page_title="Startup Edu Agent", page_icon="📘", layout="wide")
    inject_styles()
    ensure_env_loaded()
    ensure_app_state()

    st.markdown('<div class="page-shell">', unsafe_allow_html=True)
    if not st.session_state.get("authenticated"):
        render_login_page()
        st.markdown("</div>", unsafe_allow_html=True)
        return

    user = current_user(st.session_state)
    role = user["role"] if user else None
    requested_section = st.session_state.get("active_section")
    resolved_section = ensure_authorized_section(role, requested_section)
    if requested_section != resolved_section:
        log_unauthorized_attempt(role, requested_section, resolved_section)
    st.session_state["active_section"] = resolved_section
    render_sidebar()

    section = st.session_state["active_section"]
    if section == SECTION_STUDENT:
        render_student_page()
    elif section == SECTION_TEACHER:
        render_teacher_page()
    elif section == SECTION_ADMIN:
        render_admin_page()
    else:
        render_function_center()
    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
