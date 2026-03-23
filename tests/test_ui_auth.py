from ui.auth import (
    SECTION_ADMIN,
    SECTION_CENTER,
    SECTION_STUDENT,
    authenticate,
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
