from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from io import StringIO
from typing import Any


ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"
ROLE_ADMIN = "admin"

SECTION_STUDENT = "学生端"
SECTION_TEACHER = "教师端"
SECTION_CENTER = "功能中心"
SECTION_ADMIN = "管理端"

ALLOWED_REGISTER_ROLES = (ROLE_STUDENT, ROLE_TEACHER)
ALLOWED_IMPORT_ROLES = (ROLE_STUDENT, ROLE_TEACHER, ROLE_ADMIN)

IMPORT_FIELD_ALIASES = {
    "username": "username",
    "user_name": "username",
    "user": "username",
    "用户名": "username",
    "账号": "username",
    "password": "password",
    "pwd": "password",
    "密码": "password",
    "role": "role",
    "角色": "role",
    "display_name": "display_name",
    "displayname": "display_name",
    "name": "display_name",
    "显示名": "display_name",
    "显示名称": "display_name",
    "姓名": "display_name",
    "昵称": "display_name",
}


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
    ok, message, payload = _build_user_payload(
        username=username,
        password=password,
        role=role,
        display_name=display_name,
        allowed_roles=ALLOWED_REGISTER_ROLES,
        role_error_message="当前仅支持注册 student / teacher。",
    )
    if not ok or payload is None:
        return False, message, None

    users = session_state.get("auth_users", [])
    if any(user["username"] == payload["username"] for user in users):
        return False, "用户名已存在。", None

    users.append(payload)
    session_state["auth_users"] = users
    return True, "注册成功。", _public_user(payload)


def bulk_import_users(
    session_state: Any,
    raw_text: str,
    *,
    overwrite_existing: bool = False,
) -> dict[str, Any]:
    rows, parse_error = _parse_import_rows(raw_text)
    if parse_error:
        return {
            "ok": False,
            "message": parse_error,
            "created_count": 0,
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "created_users": [],
            "updated_users": [],
            "skipped_rows": [],
            "errors": [],
        }

    users = list(session_state.get("auth_users", []))
    indexed_users = {item["username"]: item for item in users}
    created_users: list[dict[str, str]] = []
    updated_users: list[dict[str, str]] = []
    skipped_rows: list[dict[str, str | int]] = []
    errors: list[dict[str, str | int]] = []

    for row in rows:
        ok, message, payload = _build_user_payload(
            username=row.get("username", ""),
            password=row.get("password", ""),
            role=row.get("role", ""),
            display_name=row.get("display_name", ""),
            allowed_roles=ALLOWED_IMPORT_ROLES,
            role_error_message="角色仅支持 student / teacher / admin。",
        )
        if not ok or payload is None:
            errors.append(
                {
                    "行号": int(row["line_number"]),
                    "用户名": str(row.get("username", "")).strip() or "-",
                    "原因": message,
                }
            )
            continue

        existing = indexed_users.get(payload["username"])
        if existing is None:
            users.append(payload)
            indexed_users[payload["username"]] = payload
            created_users.append(_public_user(payload))
            continue

        if not overwrite_existing:
            skipped_rows.append(
                {
                    "行号": int(row["line_number"]),
                    "用户名": payload["username"],
                    "原因": "用户名已存在，未覆盖。",
                }
            )
            continue

        existing.update(payload)
        updated_users.append(_public_user(existing))

    session_state["auth_users"] = users

    created_count = len(created_users)
    updated_count = len(updated_users)
    skipped_count = len(skipped_rows)
    error_count = len(errors)
    success_count = created_count + updated_count

    if success_count == 0:
        if skipped_count or error_count:
            message = f"未导入任何账号：跳过 {skipped_count} 条，失败 {error_count} 条。"
        else:
            message = "未解析出可导入的账号。"
    else:
        parts = [f"新增 {created_count} 个"]
        if updated_count:
            parts.append(f"覆盖 {updated_count} 个")
        if skipped_count:
            parts.append(f"跳过 {skipped_count} 个")
        if error_count:
            parts.append(f"失败 {error_count} 个")
        message = f"批量导入完成：{'，'.join(parts)}。"

    return {
        "ok": success_count > 0,
        "message": message,
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "created_users": created_users,
        "updated_users": updated_users,
        "skipped_rows": skipped_rows,
        "errors": errors,
    }


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


def _build_user_payload(
    *,
    username: str,
    password: str,
    role: str,
    display_name: str,
    allowed_roles: tuple[str, ...],
    role_error_message: str,
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
    if normalized_role not in allowed_roles:
        return False, role_error_message, None
    if not normalized_display_name:
        normalized_display_name = normalized_username

    return (
        True,
        "ok",
        {
            "username": normalized_username,
            "password": password,
            "role": normalized_role,
            "display_name": normalized_display_name,
        },
    )


def _parse_import_rows(raw_text: str) -> tuple[list[dict[str, str | int]], str | None]:
    cleaned = raw_text.lstrip("\ufeff").strip()
    if not cleaned:
        return [], "请先上传 CSV 文件或粘贴导入内容。"

    rows = _read_csv_rows(cleaned)
    if not rows:
        return [], "未解析出有效的导入内容。"

    header_state, field_indexes, missing_fields = _resolve_import_header(rows[0])
    if header_state == "invalid":
        missing_text = "、".join(missing_fields)
        return [], f"导入表头缺少必填字段：{missing_text}。"

    parsed_rows: list[dict[str, str | int]] = []
    if header_state == "header":
        for offset, row in enumerate(rows[1:], start=2):
            parsed_rows.append(_map_row_to_payload(row, line_number=offset, field_indexes=field_indexes))
    else:
        for offset, row in enumerate(rows, start=1):
            parsed_rows.append(_map_row_to_payload(row, line_number=offset, field_indexes={}))

    if not parsed_rows:
        return [], "导入内容中没有可处理的数据行。"
    return parsed_rows, None


def _read_csv_rows(raw_text: str) -> list[list[str]]:
    sample = raw_text[:1024]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    with StringIO(raw_text, newline="") as buffer:
        reader = csv.reader(buffer, dialect)
        return [
            [cell.strip() for cell in row]
            for row in reader
            if any(cell.strip() for cell in row)
        ]


def _resolve_import_header(header_row: list[str]) -> tuple[str, dict[str, int], list[str]]:
    field_indexes: dict[str, int] = {}
    for index, name in enumerate(header_row):
        canonical_name = IMPORT_FIELD_ALIASES.get(name.strip().lower()) or IMPORT_FIELD_ALIASES.get(name.strip())
        if canonical_name and canonical_name not in field_indexes:
            field_indexes[canonical_name] = index

    if not field_indexes:
        return "no_header", {}, []

    missing_fields = [field for field in ("username", "password", "role") if field not in field_indexes]
    if missing_fields:
        return "invalid", {}, missing_fields
    return "header", field_indexes, []


def _map_row_to_payload(
    row: list[str],
    *,
    line_number: int,
    field_indexes: dict[str, int],
) -> dict[str, str | int]:
    def pick(field: str, default_index: int | None = None) -> str:
        index = field_indexes.get(field, default_index if not field_indexes else None)
        if index is None or index >= len(row):
            return ""
        return row[index].strip()

    return {
        "line_number": line_number,
        "username": pick("username", 0),
        "password": pick("password", 1),
        "role": pick("role", 2),
        "display_name": pick("display_name", 3),
    }
