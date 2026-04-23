from ui.auth import (
    SECTION_ADMIN,
    SECTION_CENTER,
    SECTION_STUDENT,
    authenticate,
    bulk_import_users,
    ensure_authorized_section,
    init_auth_state,
    register_user,
)


def build_session_state() -> dict:
    session_state: dict = {}
    init_auth_state(session_state)
    return session_state


def test_student_authenticate_success() -> None:
    session_state = build_session_state()
    user = authenticate(session_state, "student", "student123", "student")
    assert user is not None
    assert user["role"] == "student"


def test_teacher_authenticate_success() -> None:
    session_state = build_session_state()
    user = authenticate(session_state, "teacher", "teacher123", "teacher")
    assert user is not None
    assert user["role"] == "teacher"


def test_admin_authenticate_success() -> None:
    session_state = build_session_state()
    user = authenticate(session_state, "admin", "admin123", "admin")
    assert user is not None
    assert user["role"] == "admin"


def test_authenticate_rejects_wrong_role() -> None:
    session_state = build_session_state()
    assert authenticate(session_state, "student", "student123", "teacher") is None


def test_student_route_guard_forces_student_home() -> None:
    assert ensure_authorized_section("student", SECTION_CENTER) == SECTION_STUDENT


def test_teacher_route_guard_allows_function_center() -> None:
    assert ensure_authorized_section("teacher", SECTION_CENTER) == SECTION_CENTER


def test_admin_route_guard_defaults_to_admin_home() -> None:
    assert ensure_authorized_section("admin", "不存在页面") == SECTION_ADMIN


def test_register_user_then_authenticate() -> None:
    session_state = build_session_state()
    ok, message, user = register_user(
        session_state,
        username="newstudent",
        password="secret123",
        role="student",
        display_name="新同学",
    )
    assert ok is True
    assert message == "注册成功。"
    assert user is not None

    authenticated = authenticate(session_state, "newstudent", "secret123", "student")
    assert authenticated is not None
    assert authenticated["display_name"] == "新同学"


def test_register_user_rejects_duplicate_username() -> None:
    session_state = build_session_state()
    ok, message, user = register_user(
        session_state,
        username="student",
        password="secret123",
        role="student",
        display_name="重复账号",
    )
    assert ok is False
    assert message == "用户名已存在。"
    assert user is None


def test_register_user_rejects_admin_role() -> None:
    session_state = build_session_state()
    ok, message, user = register_user(
        session_state,
        username="fakeadmin",
        password="secret123",
        role="admin",
        display_name="管理员候选",
    )
    assert ok is False
    assert message == "当前仅支持注册 student / teacher。"
    assert user is None


def test_bulk_import_users_creates_accounts_from_csv_header() -> None:
    session_state = build_session_state()
    payload = """
username,password,role,display_name
student_a,secret123,student,张同学
teacher_a,secret123,teacher,李老师
admin_a,secret123,admin,王管理员
"""

    result = bulk_import_users(session_state, payload)

    assert result["ok"] is True
    assert result["created_count"] == 3
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0
    assert result["error_count"] == 0
    assert authenticate(session_state, "student_a", "secret123", "student") is not None
    assert authenticate(session_state, "teacher_a", "secret123", "teacher") is not None
    assert authenticate(session_state, "admin_a", "secret123", "admin") is not None


def test_bulk_import_users_supports_chinese_headers() -> None:
    session_state = build_session_state()
    payload = """
用户名,密码,角色,显示名称
student_b,secret123,student,赵同学
teacher_b,secret123,teacher,周老师
"""

    result = bulk_import_users(session_state, payload)

    assert result["ok"] is True
    assert result["created_count"] == 2
    assert authenticate(session_state, "student_b", "secret123", "student") is not None
    assert authenticate(session_state, "teacher_b", "secret123", "teacher") is not None


def test_bulk_import_users_supports_headerless_text_input() -> None:
    session_state = build_session_state()
    payload = """
student_c,secret123,student,孙同学
teacher_c,secret123,teacher,吴老师
"""

    result = bulk_import_users(session_state, payload)

    assert result["ok"] is True
    assert result["created_count"] == 2
    assert authenticate(session_state, "student_c", "secret123", "student") is not None
    assert authenticate(session_state, "teacher_c", "secret123", "teacher") is not None


def test_bulk_import_users_skips_existing_user_by_default() -> None:
    session_state = build_session_state()
    payload = """
username,password,role,display_name
student,newpass123,teacher,新角色
"""

    result = bulk_import_users(session_state, payload)

    assert result["ok"] is False
    assert result["created_count"] == 0
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
    assert authenticate(session_state, "student", "student123", "student") is not None
    assert authenticate(session_state, "student", "newpass123", "teacher") is None


def test_bulk_import_users_can_overwrite_existing_user() -> None:
    session_state = build_session_state()
    payload = """
username,password,role,display_name
student,newpass123,teacher,新角色
"""

    result = bulk_import_users(session_state, payload, overwrite_existing=True)

    assert result["ok"] is True
    assert result["created_count"] == 0
    assert result["updated_count"] == 1
    assert authenticate(session_state, "student", "student123", "student") is None
    authenticated = authenticate(session_state, "student", "newpass123", "teacher")
    assert authenticated is not None
    assert authenticated["display_name"] == "新角色"
