from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMIN = "admin"

SECTION_STUDENT = "学生端"
SECTION_TEACHER = "教师端"
SECTION_CENTER = "功能中心"
SECTION_ADMIN = "管理端"

ALLOWED_REGISTER_ROLES = (ROLE_STUDENT, ROLE_TEACHER)


@dataclass(frozen=True)
class MockUser:
    username: str
    password: str
    role: str
    display_name: str


DEFAULT_USERS: tuple[MockUser, ...] = (
    MockUser(username="student", password="student123", role=ROLE_STUDENT, display_name="学生示例账号"),
    MockUser(username="teacher", password="teacher123", role=ROLE_TEACHER, display_name="教师示例账号"),
    MockUser(username="admin", password="admin123", role=ROLE_ADMIN, display_name="管理员示例账号"),
)

ROLE_HOME = {
    ROLE_STUDENT: SECTION_STUDENT,
    ROLE_TEACHER: SECTION_TEACHER,
    ROLE_ADMIN: SECTION_ADMIN,
}

ROLE_SECTIONS = {
    ROLE_STUDENT: (SECTION_STUDENT,),
    ROLE_TEACHER: (SECTION_TEACHER, SECTION_CENTER),
    ROLE_ADMIN: (SECTION_ADMIN, SECTION_TEACHER, SECTION_CENTER),
}


def _seed_users() -> list[dict[str, str]]:
    return [asdict(user) for user in DEFAULT_USERS]


def init_auth_state(session_state: Any) -> None:
    session_state.setdefault("auth_user", None)
    session_state.setdefault("authenticated", False)
    session_state.setdefault("auth_users", _seed_users())


def authenticate(session_state: Any, username: str, password: str, role: str) -> dict[str, str] | None:
    normalized_username = username.strip().lower()
    normalized_role = role.strip().lower()
    for user in session_state.get("auth_users", []):
        if (
            user["username"] == normalized_username
            and user["password"] == password
            and user["role"] == normalized_role
        ):
            return _public_user(user)
    return None


def register_user(
    session_state: Any,
    *,
    username: str,
    password: str,
    role: str,
    display_name: str,
) -> tuple[bool, str, dict[str, str] | None]:
    normalized_username = username.strip().lower()
    normalized_role = role.strip().lower()
    normalized_display_name = display_name.strip()

    if not normalized_username:
        return False, "请输入用户名。", None
    if len(normalized_username) < 3:
        return False, "用户名至少 3 位。", None
    if not password or len(password) < 6:
        return False, "密码至少 6 位。", None
    if normalized_role not in ALLOWED_REGISTER_ROLES:
        return False, "当前仅支持注册 student / teacher。", None
    if not normalized_display_name:
        normalized_display_name = normalized_username

    users = session_state.get("auth_users", [])
    if any(user["username"] == normalized_username for user in users):
        return False, "用户名已存在。", None

    payload = {
        "username": normalized_username,
        "password": password,
        "role": normalized_role,
        "display_name": normalized_display_name,
    }
    users.append(payload)
    session_state["auth_users"] = users
    return True, "注册成功。", _public_user(payload)


def login_user(session_state: Any, user: dict[str, str]) -> None:
    session_state["auth_user"] = user
    session_state["authenticated"] = True
    session_state["active_section"] = ROLE_HOME[user["role"]]


def logout_user(session_state: Any) -> None:
    session_state["auth_user"] = None
    session_state["authenticated"] = False
    session_state["active_section"] = None


def current_user(session_state: Any) -> dict[str, str] | None:
    return session_state.get("auth_user")


def allowed_sections(role: str | None) -> tuple[str, ...]:
    if not role:
        return tuple()
    return ROLE_SECTIONS.get(role, tuple())


def default_section(role: str | None) -> str:
    return ROLE_HOME.get(role or "", SECTION_STUDENT)


def ensure_authorized_section(role: str | None, requested_section: str | None) -> str:
    allowed = allowed_sections(role)
    if requested_section in allowed:
        return requested_section  # type: ignore[return-value]
    return default_section(role)


def _public_user(user: dict[str, str]) -> dict[str, str]:
    return {
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"],
    }
