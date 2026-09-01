import ast
import asyncio
import hashlib
import hmac
import importlib
import os
import re
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
API_SERVER = ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "api_server.py"
EVIDENCE_APP = ROOT / "sovereign-toolchain" / "src" / "sovereign_toolchain" / "n8n_evidence_app.py"
MASTER = "a" * 64
CONTEXT = "sovereign.n8n-ci-evidence-capability.v1"
EVIDENCE_ROUTE = "/api/v1/n8n/ci-evidence"
MASTER_CREDENTIAL_NAME = "n8n-evidence-master.key"
SOVEREIGN = SimpleNamespace(
    owner="OuroborosCollective",
    repo="Sovereign-Studio-ato",
    workflow_id="sovereign-coordinated-release.yml",
    branch="main",
)
AURION = SimpleNamespace(
    owner="OuroborosCollective",
    repo="Echoes_of_Aurion",
    workflow_id=340269357,
    branch="main",
)
SUPPORTED_LANES = frozenset(
    {
        (
            SOVEREIGN.owner,
            SOVEREIGN.repo,
            str(SOVEREIGN.workflow_id),
            SOVEREIGN.branch,
        ),
        (
            AURION.owner,
            AURION.repo,
            str(AURION.workflow_id),
            AURION.branch,
        ),
    }
)


class FakeHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeResponse:
    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code

    async def __call__(self, scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": self.status_code, "headers": []})
        await send({"type": "http.response.body", "body": b""})


class FakeJSONResponse:
    def __init__(self, *, status_code: int, content: dict) -> None:
        self.status_code = status_code
        self.content = content


def parsed(path: Path) -> ast.Module:
    return ast.parse(path.read_text("utf-8"))


def function_node(path: Path, name: str):
    return next(
        node
        for node in parsed(path).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def compile_nodes(path: Path, names: tuple[str, ...], namespace: dict):
    nodes = [function_node(path, name) for name in names]
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(path), "exec"), namespace)
    return namespace


def capability_namespace() -> dict:
    return compile_nodes(
        EVIDENCE_APP,
        ("lane_identity", "capability_message", "derive_lane_capability"),
        {
            "CAPABILITY_CONTEXT": CONTEXT,
            "hmac": hmac,
            "hashlib": hashlib,
            "N8NCIEvidenceArgs": object,
        },
    )


def capability(payload, master: str = MASTER) -> str:
    namespace = capability_namespace()
    return namespace["derive_lane_capability"](master, payload)


def compiled_check_lane(master_reader=lambda: MASTER):
    namespace = capability_namespace()
    namespace.update(
        {
            "SUPPORTED_LANES": SUPPORTED_LANES,
            "read_master_key": master_reader,
            "HTTPException": FakeHTTPException,
        }
    )
    compile_nodes(EVIDENCE_APP, ("check_lane_capability",), namespace)
    return namespace["check_lane_capability"]


def compiled_master_reader():
    namespace = {
        "os": os,
        "stat": stat,
        "re": re,
        "Path": Path,
        "HTTPException": FakeHTTPException,
        "MASTER_CREDENTIAL_NAME": MASTER_CREDENTIAL_NAME,
    }
    compile_nodes(EVIDENCE_APP, ("read_master_key",), namespace)
    return namespace["read_master_key"]


def compiled_general_key_check():
    namespace = {
        "Header": lambda default=None: default,
        "HTTPException": FakeHTTPException,
        "hmac": hmac,
        "os": os,
    }
    compile_nodes(API_SERVER, ("check_api_key",), namespace)
    return namespace["check_api_key"]


def import_real_evidence_app(monkeypatch):
    pytest.importorskip("fastapi")
    pydantic = pytest.importorskip("pydantic")
    pytest.importorskip("httpx")
    if not hasattr(pydantic, "field_validator"):
        pytest.skip("real listener integration requires Pydantic 2")
    monkeypatch.syspath_prepend(str(ROOT / "sovereign-toolchain" / "src"))
    try:
        return importlib.import_module("sovereign_toolchain.n8n_evidence_app")
    except ImportError as error:
        pytest.skip(f"real listener integration dependencies unavailable: {error}")


def test_general_api_key_is_fail_closed_when_absent(monkeypatch) -> None:
    monkeypatch.delenv("TOOLCHAIN_API_KEY", raising=False)

    with pytest.raises(FakeHTTPException) as error:
        compiled_general_key_check()(None)

    assert error.value.status_code == 503


def test_general_api_key_rejects_wrong_and_accepts_exact(monkeypatch) -> None:
    monkeypatch.setenv("TOOLCHAIN_API_KEY", MASTER)
    check = compiled_general_key_check()

    for supplied in ("wrong", "nön-ascii"):
        with pytest.raises(FakeHTTPException) as error:
            check(supplied)
        assert error.value.status_code == 401

    assert check(MASTER) is None


def test_capability_derivation_matches_runtime_contract() -> None:
    namespace = capability_namespace()
    assert namespace["capability_message"](SOVEREIGN) == (
        b"sovereign.n8n-ci-evidence-capability.v1\n"
        b"OuroborosCollective/Sovereign-Studio-ato\n"
        b"sovereign-coordinated-release.yml\n"
        b"main"
    )
    expected = hmac.new(
        MASTER.encode("utf-8"),
        namespace["capability_message"](SOVEREIGN),
        hashlib.sha256,
    ).hexdigest()
    assert capability(SOVEREIGN) == expected
    assert len(expected) == 64
    assert capability(SOVEREIGN) != capability(AURION)


def test_lane_capabilities_are_not_interchangeable_or_master_usable() -> None:
    check = compiled_check_lane()

    for call, supplied in (
        (SOVEREIGN, capability(AURION)),
        (AURION, capability(SOVEREIGN)),
        (SOVEREIGN, MASTER),
        (SOVEREIGN, capability(SOVEREIGN, "0" * 64)),
        (SOVEREIGN, None),
    ):
        with pytest.raises(FakeHTTPException) as error:
            check(call, supplied)
        assert error.value.status_code == 401

    assert check(SOVEREIGN, capability(SOVEREIGN)) is None
    assert check(AURION, capability(AURION)) is None


def test_unsupported_lane_is_denied_even_with_matching_hmac() -> None:
    unsupported = SimpleNamespace(**vars(SOVEREIGN))
    unsupported.branch = "develop"

    with pytest.raises(FakeHTTPException) as error:
        compiled_check_lane()(unsupported, capability(unsupported))

    assert error.value.status_code == 403


def test_master_credential_is_fail_closed_and_symlink_safe(tmp_path, monkeypatch) -> None:
    reader = compiled_master_reader()
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    with pytest.raises(FakeHTTPException) as missing:
        reader()
    assert missing.value.status_code == 503

    target = tmp_path / "master"
    target.write_text(MASTER + "\n", encoding="utf-8")
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    (credentials / MASTER_CREDENTIAL_NAME).symlink_to(target)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))
    with pytest.raises(FakeHTTPException) as symlink:
        reader()
    assert symlink.value.status_code == 503

    credential = credentials / MASTER_CREDENTIAL_NAME
    credential.unlink()
    credential.write_text(MASTER + "\n", encoding="utf-8")
    credential.chmod(0o600)
    assert reader() == MASTER

    credential.chmod(0o640)
    with pytest.raises(FakeHTTPException) as permissive_mode:
        reader()
    assert permissive_mode.value.status_code == 503


def test_master_credential_fifo_is_rejected_without_blocking(tmp_path, monkeypatch) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO test requires os.mkfifo")

    reader = compiled_master_reader()
    credentials = tmp_path / "credentials"
    credentials.mkdir()
    fifo = credentials / MASTER_CREDENTIAL_NAME
    os.mkfifo(fifo, mode=0o600)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))

    outcome = {}

    def invoke_reader() -> None:
        try:
            outcome["value"] = reader()
        except FakeHTTPException as error:
            outcome["status_code"] = error.status_code

    worker = threading.Thread(target=invoke_reader, daemon=True)
    worker.start()
    worker.join(timeout=1.0)

    assert not worker.is_alive(), "credential reader blocked while opening a FIFO"
    assert outcome == {"status_code": 503}


def test_preparse_guard_rejects_header_and_content_length_before_inner_app() -> None:
    tree = parsed(EVIDENCE_APP)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in {"EvidenceBodyTooLarge", "EvidenceBoundaryMiddleware"}
    ]
    module = ast.Module(body=classes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Any": object,
        "Response": FakeResponse,
        "EVIDENCE_ROUTE": EVIDENCE_ROUTE,
        "MAX_REQUEST_BODY_BYTES": 4096,
        "re": re,
    }
    exec(compile(module, str(EVIDENCE_APP), "exec"), namespace)
    middleware_class = namespace["EvidenceBoundaryMiddleware"]

    async def exercise(headers, chunks):
        inner_called = False
        sent = []
        messages = [
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
            for index, chunk in enumerate(chunks)
        ]

        async def receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        async def inner(scope, bounded_receive, inner_send):
            nonlocal inner_called
            inner_called = True
            while True:
                message = await bounded_receive()
                if message.get("type") != "http.request" or not message.get("more_body"):
                    break
            await inner_send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await inner_send({"type": "http.response.body", "body": b""})

        scope = {
            "type": "http",
            "path": EVIDENCE_ROUTE,
            "method": "POST",
            "headers": headers,
        }
        await middleware_class(inner)(scope, receive, send)
        return sent[0]["status"], inner_called

    header = (b"x-sovereign-evidence-capability", b"b" * 64)
    assert asyncio.run(exercise([], [b"x" * 5000])) == (401, False)
    assert asyncio.run(
        exercise([(header[0], b"wrong")], [b"x" * 5000])
    ) == (401, False)
    assert asyncio.run(
        exercise([header, (b"content-length", b"4097")], [b""])
    ) == (413, False)
    assert asyncio.run(
        exercise([header, (b"content-length", b"9" * 10_000)], [b""])
    ) == (413, False)
    for malformed in (b"", b"-1", b"+1", b"1x", b" 1"):
        assert asyncio.run(
            exercise([header, (b"content-length", malformed)], [b""])
        ) == (400, False)
    assert asyncio.run(
        exercise(
            [
                header,
                (b"content-length", b"1"),
                (b"content-length", b"1"),
            ],
            [b""],
        )
    ) == (400, False)


def test_preparse_guard_caps_chunked_and_untrusted_length_streams() -> None:
    tree = parsed(EVIDENCE_APP)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name in {"EvidenceBodyTooLarge", "EvidenceBoundaryMiddleware"}
    ]
    module = ast.Module(body=classes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {
        "Any": object,
        "Response": FakeResponse,
        "EVIDENCE_ROUTE": EVIDENCE_ROUTE,
        "MAX_REQUEST_BODY_BYTES": 4096,
        "re": re,
    }
    exec(compile(module, str(EVIDENCE_APP), "exec"), namespace)
    middleware_class = namespace["EvidenceBoundaryMiddleware"]
    header = (b"x-sovereign-evidence-capability", b"b" * 64)

    async def exercise(chunks, content_length=None):
        sent = []
        messages = [
            {
                "type": "http.request",
                "body": chunk,
                "more_body": index < len(chunks) - 1,
            }
            for index, chunk in enumerate(chunks)
        ]
        headers = [header]
        if content_length is not None:
            headers.append((b"content-length", str(content_length).encode("ascii")))

        async def receive():
            if messages:
                return messages.pop(0)
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        async def inner(scope, bounded_receive, inner_send):
            while True:
                message = await bounded_receive()
                if message.get("type") != "http.request" or not message.get("more_body"):
                    break
            await inner_send(
                {"type": "http.response.start", "status": 204, "headers": []}
            )
            await inner_send({"type": "http.response.body", "body": b""})

        scope = {
            "type": "http",
            "path": EVIDENCE_ROUTE,
            "method": "POST",
            "headers": headers,
        }
        await middleware_class(inner)(scope, receive, send)
        return sent[0]["status"]

    assert asyncio.run(exercise([b"x" * 2048, b"y" * 2048])) == 204
    assert asyncio.run(exercise([b"x" * 2048, b"y" * 2049])) == 413
    assert asyncio.run(exercise([b"x" * 4097], content_length=1)) == 413
    assert asyncio.run(exercise([b"x" * 4096], content_length=4096)) == 204


def test_real_listener_exact_route_auth_and_stream_limits(tmp_path, monkeypatch) -> None:
    evidence_app = import_real_evidence_app(monkeypatch)
    testclient = pytest.importorskip("fastapi.testclient")

    credentials = tmp_path / "credentials"
    credentials.mkdir()
    credential = credentials / MASTER_CREDENTIAL_NAME
    credential.write_text(MASTER + "\n", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))

    def fake_dispatch(tool, args):
        return {
            "ok": True,
            "tool": tool,
            "result": {
                "repository": f"{args['owner']}/{args['repo']}",
                "workflowSelector": str(args["workflow_id"]),
                "branch": args["branch"],
            },
        }

    monkeypatch.setattr(evidence_app, "dispatch_tool", fake_dispatch)
    payload = {
        "owner": SOVEREIGN.owner,
        "repo": SOVEREIGN.repo,
        "workflow_id": SOVEREIGN.workflow_id,
        "branch": SOVEREIGN.branch,
    }
    call = evidence_app.N8NCIEvidenceArgs(**payload)
    valid_headers = {
        "X-Sovereign-Evidence-Capability": evidence_app.derive_lane_capability(
            MASTER, call
        )
    }

    with testclient.TestClient(
        evidence_app.app,
        follow_redirects=False,
        raise_server_exceptions=False,
    ) as client:
        response = client.post(EVIDENCE_ROUTE, json=payload, headers=valid_headers)
        assert response.status_code == 200
        assert response.json()["result"] == {
            "repository": "OuroborosCollective/Sovereign-Studio-ato",
            "workflowSelector": "sovereign-coordinated-release.yml",
            "branch": "main",
        }

        trailing = client.post(EVIDENCE_ROUTE + "/", json=payload, headers=valid_headers)
        assert trailing.status_code == 404
        assert "location" not in trailing.headers

        assert client.post(EVIDENCE_ROUTE, json=payload).status_code == 401
        assert client.post(
            EVIDENCE_ROUTE,
            json=payload,
            headers={"X-Sovereign-Evidence-Capability": "wrong"},
        ).status_code == 401
        assert client.post(
            EVIDENCE_ROUTE,
            content=b"{}",
            headers={**valid_headers, "Content-Length": "4097"},
        ).status_code == 413

        # Starlette's TestClient rejects generator-based chunked bodies before
        # the ASGI middleware receives them. The real streaming receive path is
        # exercised directly by test_streaming_body_larger_than_limit_is_rejected.
        assert client.post(
            EVIDENCE_ROUTE,
            content=b"x" * 4097,
            headers=valid_headers,
        ).status_code == 413


def test_dispatch_failure_contract_is_non_2xx_bounded_and_safe() -> None:
    namespace = {
        "Any": object,
        "JSONResponse": FakeJSONResponse,
        "N8NCIEvidenceArgs": object,
        "Header": lambda default=None, alias=None: default,
        "check_lane_capability": lambda call, supplied: None,
        "EVIDENCE_ROUTE": EVIDENCE_ROUTE,
        "app": SimpleNamespace(post=lambda *args, **kwargs: lambda function: function),
    }
    compile_nodes(
        EVIDENCE_APP,
        ("evidence_dispatch_failure_response", "n8n_ci_evidence"),
        namespace,
    )
    endpoint = namespace["n8n_ci_evidence"]
    call = SimpleNamespace(model_dump=lambda **kwargs: {"owner": SOVEREIGN.owner})
    private_detail = "private-upstream-detail-" + "x" * 8_000
    safe_failure = {
        "ok": False,
        "tool": "github_actions_run_evidence",
        "error": "CI evidence acquisition failed",
    }

    def failed_dispatch(tool, args):
        return {"ok": False, "tool": tool, "error": private_detail}

    def malformed_dispatch(tool, args):
        return ["unexpected-dispatch-shape"]

    def raising_dispatch(tool, args):
        raise RuntimeError(private_detail)

    for dispatcher in (failed_dispatch, malformed_dispatch, raising_dispatch):
        namespace["dispatch_tool"] = dispatcher
        response = endpoint(call, "b" * 64)

        assert response.status_code == 502
        assert response.content == safe_failure
        assert private_detail not in repr(response.content)
        assert len(repr(response.content)) < 256

    success = {"ok": True, "tool": "github_actions_run_evidence", "result": {}}
    namespace["dispatch_tool"] = lambda tool, args: success
    assert endpoint(call, "b" * 64) is success


def test_real_listener_dispatch_failures_are_non_2xx_and_safe(
    tmp_path, monkeypatch
) -> None:
    evidence_app = import_real_evidence_app(monkeypatch)
    testclient = pytest.importorskip("fastapi.testclient")

    credentials = tmp_path / "credentials"
    credentials.mkdir()
    credential = credentials / MASTER_CREDENTIAL_NAME
    credential.write_text(MASTER + "\n", encoding="utf-8")
    credential.chmod(0o600)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credentials))

    payload = {
        "owner": SOVEREIGN.owner,
        "repo": SOVEREIGN.repo,
        "workflow_id": SOVEREIGN.workflow_id,
        "branch": SOVEREIGN.branch,
    }
    call = evidence_app.N8NCIEvidenceArgs(**payload)
    valid_headers = {
        "X-Sovereign-Evidence-Capability": evidence_app.derive_lane_capability(
            MASTER, call
        )
    }
    safe_failure = {
        "ok": False,
        "tool": "github_actions_run_evidence",
        "error": "CI evidence acquisition failed",
    }
    private_detail = "private-upstream-detail-" + "x" * 8_000

    def failed_dispatch(tool, args):
        return {"ok": False, "tool": tool, "error": private_detail}

    def malformed_dispatch(tool, args):
        return "unexpected-dispatch-shape"

    def raising_dispatch(tool, args):
        raise RuntimeError(private_detail)

    with testclient.TestClient(
        evidence_app.app,
        follow_redirects=False,
        raise_server_exceptions=False,
    ) as client:
        for dispatcher in (failed_dispatch, malformed_dispatch, raising_dispatch):
            monkeypatch.setattr(evidence_app, "dispatch_tool", dispatcher)
            response = client.post(EVIDENCE_ROUTE, json=payload, headers=valid_headers)

            assert response.status_code == 502
            assert response.json() == safe_failure
            assert private_detail not in response.text
            assert len(response.content) < 256


def test_listener_has_no_docs_mcp_or_general_routes() -> None:
    tree = parsed(EVIDENCE_APP)
    app_assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
    )
    assert isinstance(app_assignment.value, ast.Call)
    keywords = {keyword.arg: keyword.value for keyword in app_assignment.value.keywords}
    for name in ("docs_url", "redoc_url", "openapi_url"):
        assert isinstance(keywords[name], ast.Constant)
        assert keywords[name].value is None
    assert isinstance(keywords["redirect_slashes"], ast.Constant)
    assert keywords["redirect_slashes"].value is False

    route_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in {"get", "post"}
            for decorator in node.decorator_list
        )
    }
    assert route_names == {"healthz", "n8n_ci_evidence"}

    source = EVIDENCE_APP.read_text("utf-8")
    assert 'EVIDENCE_ROUTE = "/api/v1/n8n/ci-evidence"' in source
    assert 'b"x-sovereign-evidence-capability"' in source
    assert "MAX_REQUEST_BODY_BYTES = 4096" in source
    assert '"/mcp"' not in source
    assert '"/v1/tools/' not in source
    assert '"github_actions_run_evidence"' in source

    full_source = API_SERVER.read_text("utf-8")
    assert "/v1/n8n/" not in full_source


def test_direct_schema_forbids_wrappers_and_unbound_fields() -> None:
    tree = parsed(EVIDENCE_APP)
    schema = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "N8NCIEvidenceArgs"
    )
    fields = {
        node.target.id
        for node in schema.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    assert fields == {
        "owner",
        "repo",
        "workflow_id",
        "branch",
        "previous_fingerprint",
    }
    model_config = next(
        node
        for node in schema.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "model_config" for target in node.targets)
    )
    extra = next(
        keyword.value
        for keyword in model_config.value.keywords
        if keyword.arg == "extra"
    )
    assert isinstance(extra, ast.Constant) and extra.value == "forbid"

    endpoint = function_node(EVIDENCE_APP, "n8n_ci_evidence")
    calls = [
        node.func.id
        for node in ast.walk(endpoint)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "check_lane_capability" in calls
    constants = {
        node.value
        for node in ast.walk(endpoint)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert "github_actions_run_evidence" in constants
