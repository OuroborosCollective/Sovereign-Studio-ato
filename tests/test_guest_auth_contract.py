from __future__ import annotations

import ast
from pathlib import Path

APP_PATH = Path(__file__).parents[1] / "scripts" / "sovereign-backend" / "app.py"


def _source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    tree = ast.parse(source, filename=str(APP_PATH))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
    )
    segment = ast.get_source_segment(source, node)
    assert segment is not None
    return segment


def test_backend_source_is_valid_python() -> None:
    ast.parse(_source(), filename=str(APP_PATH))


def test_guest_session_is_pseudonymous_rate_limited_and_zero_credit() -> None:
    source = _source()
    guest = _function_source("auth_guest")

    assert '@app.route("/api/auth/guest", methods=["POST"])' in source
    assert "_check_rate_limit" in guest
    assert "_GUEST_EMAIL_SUFFIX" in guest
    assert "initial_credits=0" in guest
    assert "_set_session_cookie" in guest


def test_github_oauth_can_attach_to_the_current_guest_without_exposing_token() -> None:
    github = _function_source("auth_github")
    serializer = _function_source("_user_row_to_dict")

    assert "_get_session_user_id()" in github
    assert "_is_guest_user_row(session_row)" in github
    assert "github_access_token = %s" in github
    assert "github_access_token" not in serializer.lower()
