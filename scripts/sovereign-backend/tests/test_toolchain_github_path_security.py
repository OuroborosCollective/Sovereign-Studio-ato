from __future__ import annotations

import ast
import base64
import copy
from pathlib import Path
import urllib.parse

import pytest


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
APP_PATH = BACKEND / "app.py"
APP_SOURCE = APP_PATH.read_text("utf-8")


def _load_functions(*names: str, globals_: dict | None = None) -> dict:
    """Load selected app.py functions without importing the Flask runtime."""
    wanted = set(names)
    tree = ast.parse(APP_SOURCE)
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted:
            cloned = copy.deepcopy(node)
            cloned.decorator_list = []
            nodes.append(cloned)
    found = {node.name for node in nodes}
    assert found == wanted, f"missing functions: {sorted(wanted - found)}"
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "__name__": "toolchain_path_security_test",
        "urllib": urllib,
        "base64": base64,
        **(globals_ or {}),
    }
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


class _Request:
    session_user_id = "00000000-0000-0000-0000-000000000001"

    def __init__(self, payload: dict):
        self.payload = payload

    def get_json(self, force: bool = False):
        assert force is True
        return self.payload


def _jsonify(payload: dict) -> dict:
    return payload


def test_validator_decodes_once_and_reencoding_keeps_residual_delimiters_as_data() -> None:
    validate = _load_functions("_tc_validate_path")["_tc_validate_path"]

    traversal_candidate = validate("docs/%252e%252e/secret")
    assert traversal_candidate == "docs/%2e%2e/secret"
    assert urllib.parse.quote(traversal_candidate, safe="/") == "docs/%252e%252e/secret"

    delimiter_candidate = validate("docs/report%253Fv1%2523draft.md")
    assert delimiter_candidate == "docs/report%3Fv1%23draft.md"
    encoded = urllib.parse.quote(delimiter_candidate, safe="/")
    assert encoded == "docs/report%253Fv1%2523draft.md"
    assert "?" not in encoded
    assert "#" not in encoded


def test_validator_preserves_repository_whitespace_without_retargeting() -> None:
    validate = _load_functions("_tc_validate_path")["_tc_validate_path"]

    assert validate("%20README.md") == " README.md"
    assert validate("README.md%20") == "README.md "
    assert urllib.parse.quote(validate("%20README.md"), safe="/") == "%20README.md"
    assert urllib.parse.quote(validate("README.md%20"), safe="/") == "README.md%20"

    with pytest.raises(ValueError, match="Leerzeichen"):
        validate("   ")
    with pytest.raises(ValueError, match="Leerzeichen"):
        validate("%20")


def test_validator_still_blocks_real_traversal_absolute_and_invalid_types() -> None:
    validate = _load_functions("_tc_validate_path")["_tc_validate_path"]

    for unsafe in ("docs/../secret", "docs/%2e%2e/secret", "/etc/passwd", "docs\\..\\secret"):
        with pytest.raises(PermissionError):
            validate(unsafe)
    with pytest.raises(ValueError, match="String"):
        validate(123)
    assert validate("", allow_empty=True) == ""


def test_read_route_uses_one_normalized_path_for_url_response_and_audit() -> None:
    observed: dict = {}

    def gh_get(path: str) -> dict:
        observed["url"] = path
        return {
            "sha": "a" * 40,
            "html_url": "https://example.invalid/file",
            "content": base64.b64encode(b"content").decode("ascii"),
        }

    def audit(user_id: str, action: str, details: dict) -> None:
        observed["audit"] = {"user_id": user_id, "action": action, "details": details}

    namespace = _load_functions(
        "_tc_validate_path",
        "_tc_read_github_file",
        "tc_github_read_file",
        globals_={
            "_tc_allowed": lambda owner, repo: None,
            "_tc_gh_get": gh_get,
            "_tc_audit": audit,
            "jsonify": _jsonify,
            "request": _Request({
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "%20README.md",
            }),
        },
    )

    response = namespace["tc_github_read_file"]()

    assert response["path"] == " README.md"
    assert observed["url"].endswith("/contents/%20README.md")
    assert observed["audit"]["details"]["path"] == " README.md"


def test_read_route_reencodes_double_encoded_delimiters_before_github_url() -> None:
    observed: dict = {}

    def gh_get(path: str) -> dict:
        observed["url"] = path
        return {
            "sha": "b" * 40,
            "html_url": "https://example.invalid/file",
            "content": base64.b64encode(b"content").decode("ascii"),
        }

    namespace = _load_functions(
        "_tc_validate_path",
        "_tc_read_github_file",
        globals_={
            "_tc_allowed": lambda owner, repo: None,
            "_tc_gh_get": gh_get,
        },
    )
    result = namespace["_tc_read_github_file"](
        "OuroborosCollective",
        "Sovereign-Studio-ato",
        "docs/report%253Fv1%2523draft.md",
    )

    assert result["path"] == "docs/report%3Fv1%23draft.md"
    assert observed["url"].endswith("/contents/docs/report%253Fv1%2523draft.md")
    assert "?" not in observed["url"]
    assert "#" not in observed["url"]


def test_create_draft_preview_propagates_path_guard_as_403_safe_stop() -> None:
    namespace = _load_functions(
        "_tc_validate_path",
        "tc_create_draft_pr",
        globals_={
            "jsonify": _jsonify,
            "request": _Request({
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "docs/%2e%2e/secret",
                "message": "blocked",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": False,
            }),
        },
    )

    payload, status = namespace["tc_create_draft_pr"]()
    assert status == 403
    assert "Traversal" in payload["error"]


def test_confirmed_draft_uses_normalized_path_for_diff_and_audit() -> None:
    observed: dict = {}

    def read_file(owner: str, repo: str, path: str, ref=None) -> dict:
        observed["read_raw_path"] = path
        return {"path": " README.md", "sha": "c" * 40, "content": "before\n"}

    def unified_diff(before: str, after: str, path: str) -> str:
        observed["diff_path"] = path
        return f"a/{path}\n"

    def create_pr(**kwargs) -> dict:
        observed["create_raw_path"] = kwargs["path"]
        return {"pr_number": 1, "pr_url": "https://example.invalid/pr/1", "draft": True}

    def audit(user_id: str, action: str, details: dict) -> None:
        observed["audit_path"] = details["path"]

    namespace = _load_functions(
        "_tc_validate_path",
        "tc_create_draft_pr",
        globals_={
            "jsonify": _jsonify,
            "request": _Request({
                "owner": "OuroborosCollective",
                "repo": "Sovereign-Studio-ato",
                "path": "%20README.md",
                "message": "preserve target",
                "blocks": [{"search": "before", "replace": "after"}],
                "confirm": True,
            }),
            "_tc_read_github_file": read_file,
            "_tc_apply_blocks": lambda content, blocks: ("after\n", [{"index": 0}]),
            "_tc_unified_diff": unified_diff,
            "_tc_create_draft_pr": create_pr,
            "_tc_audit": audit,
            "query": lambda *args, **kwargs: {"role": "admin"},
        },
    )

    response = namespace["tc_create_draft_pr"]()

    assert response["created"] is True
    assert observed["read_raw_path"] == "%20README.md"
    assert observed["create_raw_path"] == "%20README.md"
    assert observed["diff_path"] == " README.md"
    assert observed["audit_path"] == " README.md"


@pytest.mark.parametrize(
    ("function_name", "payload", "expected_status"),
    [
        (
            "tc_github_read_file",
            {"owner": "O", "repo": "R", "path": 123},
            400,
        ),
        (
            "tc_github_list_directory",
            {"owner": "O", "repo": "R", "path": 123},
            400,
        ),
        (
            "tc_apply_patch_worker",
            {
                "owner": "O",
                "repo": "R",
                "path": 123,
                "message": "x",
                "blocks": [{"search": "a", "replace": "b"}],
                "confirm": False,
            },
            400,
        ),
    ],
)
def test_invalid_path_input_is_a_client_error(
    function_name: str,
    payload: dict,
    expected_status: int,
) -> None:
    globals_ = {
        "jsonify": _jsonify,
        "request": _Request(payload),
        "_TC_WORKER_URL": "https://worker.example.invalid/git/patch",
        "_tc_allowed": lambda owner, repo: None,
    }
    namespace = _load_functions("_tc_validate_path", function_name, globals_=globals_)

    body, status = namespace[function_name]()
    assert status == expected_status
    assert "Pfad" in body["error"]


def test_all_repository_content_urls_use_reencoded_paths() -> None:
    assert "contents/{path}" not in APP_SOURCE
    assert APP_SOURCE.count('encoded_path = urllib.parse.quote(path, safe="/")') >= 3
    assert 'contents/{encoded_path}' in APP_SOURCE


def test_app_only_changes_dispatch_the_backend_security_ci() -> None:
    coordinator = (
        ROOT / ".github" / "workflows" / "supplemental-check-coordinator.yml"
    ).read_text("utf-8")
    ci_workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    ci_spec = coordinator.split("workflow_id: 'ci.yml'", 1)[1].split("              },", 1)[0]
    assert "'scripts/sovereign-backend/app.py'" in ci_spec
    assert "scripts/sovereign-backend/app.py" in ci_workflow
