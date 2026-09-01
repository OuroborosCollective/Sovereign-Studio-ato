from __future__ import annotations

import copy
import hashlib
import hmac
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import Any

import pytest
import requests
from pydantic import ValidationError

from n8n_workflow_runtime import (
    API_ROOT,
    CIEvidenceWatchSpec,
    EVIDENCE_CAPABILITY_CONTEXT,
    EVIDENCE_CREDENTIAL_TYPE,
    EVIDENCE_HEADER_NAME,
    N8NWorkflowAutomationRuntime,
    TOOLCHAIN_EVIDENCE_URL,
    _LANES,
    _canonical_sha256,
    _definition_projection,
)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = json.dumps(payload).encode("utf-8")

    def json(self) -> Any:
        return copy.deepcopy(self._payload)


class StatefulN8N:
    def __init__(self, lane_id: str, *, credential_present: bool = True) -> None:
        self.lane = _LANES[lane_id]
        self.project = {
            "id": f"project-{lane_id}",
            "name": self.lane.project_name,
        }
        self.credentials: list[dict[str, Any]] = []
        if credential_present:
            self.credentials.append(
                {
                    "id": f"credential-{lane_id}",
                    "name": self.lane.evidence_credential_name,
                    "type": EVIDENCE_CREDENTIAL_TYPE,
                    "projectId": self.project["id"],
                }
            )
        self.workflows: dict[str, dict[str, Any]] = {}
        self.outside_project_workflow_ids: set[str] = set()
        self.calls: list[dict[str, Any]] = []
        self.lock_root = Path(tempfile.mkdtemp(prefix="n8n-workflow-locks-"))
        self.next_id = 1

    def add_workflow(
        self,
        runtime: N8NWorkflowAutomationRuntime,
        *,
        workflow_id: str = "workflow-1",
        active: bool = False,
        name: str = "Evidence Watch",
    ) -> dict[str, Any]:
        credential_id = (
            str(self.credentials[0]["id"])
            if self.credentials
            else "__missing__"
        )
        definition = runtime._definition(
            self.lane,
            credential_id,
            CIEvidenceWatchSpec(name=name, schedule_minutes=15),
        )
        workflow = {
            **definition,
            "id": workflow_id,
            "active": active,
            "versionId": "version-1",
            "updatedAt": "2026-09-01T00:00:00Z",
        }
        self.workflows[workflow_id] = workflow
        return workflow

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any],
        json: dict[str, Any] | None,
        timeout: tuple[float, int],
        allow_redirects: bool,
    ) -> FakeResponse:
        assert allow_redirects is False
        assert url.startswith(API_ROOT)
        path = url[len(API_ROOT) :]
        self.calls.append(
            {
                "method": method,
                "path": path,
                "headers": dict(headers),
                "params": dict(params),
                "json": copy.deepcopy(json),
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        if method == "GET" and path == "/projects":
            return FakeResponse({"data": [self.project]})
        if method == "GET" and path == "/credentials":
            return FakeResponse({"data": self.credentials})
        if method == "POST" and path == "/credentials":
            assert json is not None
            created = {
                "id": f"credential-{self.lane.lane_id}",
                "name": json["name"],
                "type": json["type"],
                "projectId": json["projectId"],
            }
            self.credentials.append(created)
            return FakeResponse(created, 201)
        if method == "GET" and path == "/workflows":
            assert params["projectId"] == self.project["id"]
            return FakeResponse(
                {
                    "data": [
                        workflow
                        for workflow_id, workflow in self.workflows.items()
                        if workflow_id not in self.outside_project_workflow_ids
                    ]
                }
            )
        if method == "POST" and path == "/workflows":
            assert json is not None
            workflow_id = f"workflow-new-{self.next_id}"
            self.next_id += 1
            workflow = {
                **copy.deepcopy(json),
                "id": workflow_id,
                "active": False,
                "versionId": "version-created",
                "updatedAt": "2026-09-01T00:01:00Z",
            }
            workflow["settings"] = {
                **workflow.get("settings", {}),
                "saveManualExecutions": False,
                "callerPolicy": "workflowsFromSameOwner",
            }
            self.workflows[workflow_id] = workflow
            return FakeResponse({"id": workflow_id}, 201)
        if path.startswith("/workflows/"):
            suffix = path[len("/workflows/") :]
            parts = suffix.split("/")
            workflow_id = parts[0]
            if workflow_id not in self.workflows:
                return FakeResponse({"message": "not found"}, 404)
            workflow = self.workflows[workflow_id]
            if method == "GET" and len(parts) == 1:
                return FakeResponse(workflow)
            if method == "PUT" and len(parts) == 1:
                assert json is not None
                assert params == {"publishIfActive": "false"}
                active = bool(workflow.get("active"))
                workflow.update(copy.deepcopy(json))
                workflow["active"] = active
                workflow["versionId"] = "version-updated"
                workflow["settings"] = {
                    **workflow.get("settings", {}),
                    "saveManualExecutions": False,
                }
                return FakeResponse(workflow)
            if method == "POST" and parts[1:] == ["publish"]:
                workflow["active"] = True
                workflow["versionId"] = "version-published"
                return FakeResponse(workflow)
            if method == "POST" and parts[1:] == ["unpublish"]:
                workflow["active"] = False
                workflow["versionId"] = "version-unpublished"
                return FakeResponse(workflow)
        return FakeResponse({"message": "unexpected"}, 500)


class AmbiguousWriteSession(StatefulN8N):
    def __init__(
        self,
        lane_id: str,
        *,
        target_path: str,
        commit_before_error: bool,
        response_status: int | None = None,
        credential_present: bool = True,
    ) -> None:
        super().__init__(lane_id, credential_present=credential_present)
        self.target_path = target_path
        self.commit_before_error = commit_before_error
        self.response_status = response_status
        self.write_fault_raised = False

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        path = url[len(API_ROOT) :]
        if (
            method in {"POST", "PUT"}
            and path == self.target_path
            and not self.write_fault_raised
        ):
            self.write_fault_raised = True
            if self.commit_before_error:
                super().request(method, url, **kwargs)
            else:
                self.calls.append(
                    {
                        "method": method,
                        "path": path,
                        "headers": dict(kwargs.get("headers") or {}),
                        "params": dict(kwargs.get("params") or {}),
                        "json": copy.deepcopy(kwargs.get("json")),
                        "timeout": kwargs.get("timeout"),
                        "allow_redirects": kwargs.get("allow_redirects"),
                    }
                )
            if self.response_status is not None:
                return FakeResponse(
                    {"message": "simulated bounded write rejection"},
                    self.response_status,
                )
            raise requests.ConnectionError(
                "simulated lost response after bounded write attempt"
            )
        return super().request(method, url, **kwargs)


class CreateInventoryRaceSession(StatefulN8N):
    def __init__(self) -> None:
        super().__init__("sovereign")
        self.workflow_list_reads = 0
        self.pending_external_workflow: dict[str, Any] | None = None

    def arm_external_create(
        self,
        runtime: N8NWorkflowAutomationRuntime,
    ) -> None:
        definition = runtime._definition(
            self.lane,
            str(self.credentials[0]["id"]),
            CIEvidenceWatchSpec(
                name="External Race Evidence",
                schedule_minutes=15,
            ),
        )
        self.pending_external_workflow = {
            **definition,
            "id": "external-race-workflow",
            "active": False,
            "versionId": "external-race-version",
            "updatedAt": "2026-09-01T00:00:30Z",
        }

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        path = url[len(API_ROOT) :]
        if method == "GET" and path == "/workflows":
            self.workflow_list_reads += 1
            if self.workflow_list_reads == 3:
                assert self.pending_external_workflow is not None
                self.workflows["external-race-workflow"] = copy.deepcopy(
                    self.pending_external_workflow
                )
        return super().request(method, url, **kwargs)


class RuntimeUnderTest(N8NWorkflowAutomationRuntime):
    def _api_key(self, lane: Any) -> str:
        return "lane-api-key-for-tests"

    @staticmethod
    def _read_root_secret(path: Path, *, purpose: str) -> str:
        return "evidence-capability-value-for-tests"


def runtime_for(session: StatefulN8N, *, write: bool = True) -> RuntimeUnderTest:
    return RuntimeUnderTest(
        session=session,
        environ={
            "SOVEREIGN_MCP_ENABLE_N8N_WORKFLOW_WRITE": "1" if write else "0"
        },
        lock_root=session.lock_root,
    )


def test_spec_rejects_untyped_or_legacy_surfaces() -> None:
    spec = CIEvidenceWatchSpec(name="Bounded Evidence", schedule_minutes=15)
    assert spec.model_dump(mode="json") == {
        "schema_version": "sovereign.n8n-ci-evidence-watch-spec.v1",
        "kind": "ci_evidence_watch",
        "name": "Bounded Evidence",
        "schedule_minutes": 15,
    }

    for extra in (
        {"url": "https://example.invalid"},
        {"credentials": {"id": "free"}},
        {"code": "return 1"},
        {"webhook": "/free"},
        {"shell": "id"},
        {"recent_runs": 10},
        {"expected_head_sha": "a" * 40},
    ):
        with pytest.raises(ValidationError):
            CIEvidenceWatchSpec(
                name="Bounded Evidence",
                schedule_minutes=15,
                **extra,
            )
    with pytest.raises(ValidationError):
        CIEvidenceWatchSpec(name="Too Fast", schedule_minutes=14)


@pytest.mark.parametrize(
    ("lane_id", "repo", "selector", "schedule_id", "receipt_id"),
    [
        (
            "sovereign",
            "Sovereign-Studio-ato",
            "sovereign-coordinated-release.yml",
            "8921583f-01db-5471-a1fd-a4896ec84ded",
            "5e1a0ea3-eeda-59a8-a3f2-22bfa28eaeb6",
        ),
        (
            "aurion",
            "Echoes_of_Aurion",
            "340269357",
            "361c4c40-6335-5206-96d6-e1dc09be8256",
            "60737b3b-dd59-513f-8c68-808dc2366ddb",
        ),
    ],
)
def test_definition_is_exact_two_node_fixed_adapter(
    lane_id: str,
    repo: str,
    selector: str,
    schedule_id: str,
    receipt_id: str,
) -> None:
    session = StatefulN8N(lane_id)
    runtime = runtime_for(session)
    definition = runtime._definition(
        session.lane,
        "server-resolved-credential",
        CIEvidenceWatchSpec(
            name=f"{lane_id.title()} Evidence",
            schedule_minutes=30,
        ),
    )

    assert len(definition["nodes"]) == 2
    assert {node["id"] for node in definition["nodes"]} == {
        schedule_id,
        receipt_id,
    }
    assert {node["type"] for node in definition["nodes"]} == {
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
    }
    schedule = next(
        node
        for node in definition["nodes"]
        if node["type"] == "n8n-nodes-base.scheduleTrigger"
    )
    receipt = next(
        node
        for node in definition["nodes"]
        if node["type"] == "n8n-nodes-base.httpRequest"
    )
    assert schedule["id"] == schedule_id
    assert receipt["id"] == receipt_id
    assert TOOLCHAIN_EVIDENCE_URL == (
        "http://host.docker.internal:8002/api/v1/n8n/ci-evidence"
    )
    assert receipt["parameters"]["url"] == TOOLCHAIN_EVIDENCE_URL
    assert receipt["parameters"]["method"] == "POST"
    assert json.loads(receipt["parameters"]["jsonBody"]) == {
        "owner": "OuroborosCollective",
        "repo": repo,
        "branch": "main",
        "workflow_id": selector,
        "previous_fingerprint": None,
    }
    assert receipt["credentials"] == {
        "httpHeaderAuth": {
            "id": "server-resolved-credential",
            "name": session.lane.evidence_credential_name,
        }
    }
    serialized = json.dumps(definition)
    for forbidden in (
        "api.github.com",
        "splitOut",
        '"args"',
        "expected_head_sha",
        "recent_runs",
        "n8n-nodes-base.code",
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.executeCommand",
    ):
        assert forbidden not in serialized


def test_definition_projection_ignores_n8n_read_only_settings() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    desired = runtime._definition(
        session.lane,
        "credential-sovereign",
        CIEvidenceWatchSpec(name="Projection Evidence"),
    )
    readback = copy.deepcopy(desired)
    readback["settings"]["saveManualExecutions"] = False
    readback["settings"]["callerPolicy"] = "workflowsFromSameOwner"
    readback["createdAt"] = "2026-09-01T00:00:00Z"
    readback["nodes"][0]["createdByApi"] = True

    assert _canonical_sha256(_definition_projection(desired)) == _canonical_sha256(
        _definition_projection(readback)
    )


def test_plan_binds_exact_project_credential_and_state() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime)

    first = runtime.plan(
        lane_id="sovereign",
        operation="update_draft",
        workflow_id="workflow-1",
        spec={
            "name": "Evidence Watch",
            "schedule_minutes": 15,
        },
    )
    assert first["ok"] is True
    assert first["projectId"] == "project-sovereign"
    assert first["projectName"] == "Personal"
    assert first["credentialPresent"] is True
    assert first["currentState"]["versionId"] == "version-1"

    session.workflows["workflow-1"]["versionId"] = "version-2"
    changed = runtime.plan(
        lane_id="sovereign",
        operation="update_draft",
        workflow_id="workflow-1",
        spec={
            "name": "Evidence Watch",
            "schedule_minutes": 15,
        },
    )
    assert changed["confirmationSha256"] != first["confirmationSha256"]

    session.workflows["workflow-1"]["active"] = True
    blocked = runtime.plan(
        lane_id="sovereign",
        operation="update_draft",
        workflow_id="workflow-1",
        spec={
            "name": "Evidence Watch",
            "schedule_minutes": 15,
        },
    )
    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_ACTIVE_WORKFLOW_UPDATE_BLOCKED"


def test_create_is_draft_and_bootstraps_only_fixed_credential() -> None:
    session = StatefulN8N("aurion", credential_present=False)
    runtime = runtime_for(session)
    spec = {"name": "Aurion Evidence", "schedule_minutes": 30}
    plan = runtime.plan(
        lane_id="aurion",
        operation="create_draft",
        spec=spec,
    )
    assert plan["ok"] is True
    assert plan["credentialPresent"] is False

    applied = runtime.apply(
        lane_id="aurion",
        operation="create_draft",
        spec=spec,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )
    assert applied["ok"] is True
    assert applied["readbackVerified"] is True
    assert applied["readback"]["active"] is False
    assert applied["credentialBootstrapped"] is True
    assert "lane-api-key-for-tests" not in json.dumps(applied)
    assert "evidence-capability-value-for-tests" not in json.dumps(applied)

    credential_posts = [
        call
        for call in session.calls
        if call["method"] == "POST" and call["path"] == "/credentials"
    ]
    assert len(credential_posts) == 1
    assert credential_posts[0]["json"] == {
        "name": "Aurion Toolchain Evidence",
        "type": "httpHeaderAuth",
        "projectId": "project-aurion",
        "data": {
            "name": EVIDENCE_HEADER_NAME,
            "value": runtime._evidence_capability(session.lane),
        },
    }
    workflow_post = next(
        call
        for call in session.calls
        if call["method"] == "POST" and call["path"] == "/workflows"
    )
    assert "active" not in workflow_post["json"]


def test_update_uses_publish_if_active_false_and_normalized_readback() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    spec = {"name": "Evidence Watch Updated", "schedule_minutes": 60}
    plan = runtime.plan(
        lane_id="sovereign",
        operation="update_draft",
        workflow_id="workflow-1",
        spec=spec,
    )
    applied = runtime.apply(
        lane_id="sovereign",
        operation="update_draft",
        workflow_id="workflow-1",
        spec=spec,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is True
    update = next(call for call in session.calls if call["method"] == "PUT")
    assert update["path"] == "/workflows/workflow-1"
    assert update["params"] == {"publishIfActive": "false"}


@pytest.mark.parametrize(
    ("operation", "initial_active", "endpoint", "expected_active"),
    [
        ("activate", False, "/workflows/workflow-1/publish", True),
        ("pause", True, "/workflows/workflow-1/unpublish", False),
    ],
)
def test_publish_and_unpublish_use_n8n_2369_endpoints(
    operation: str,
    initial_active: bool,
    endpoint: str,
    expected_active: bool,
) -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime, active=initial_active)
    plan = runtime.plan(
        lane_id="sovereign",
        operation=operation,
        workflow_id="workflow-1",
    )
    applied = runtime.apply(
        lane_id="sovereign",
        operation=operation,
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["readback"]["active"] is expected_active
    assert any(
        call["method"] == "POST" and call["path"] == endpoint
        for call in session.calls
    )
    if operation == "activate":
        assert applied["ok"] is False
        assert applied["status"] == (
            "N8N_WORKFLOW_ACTIVATION_PENDING_EXECUTION_EVIDENCE"
        )
        assert applied["failureFamily"] == (
            "N8N_ACTIVATION_EXECUTION_EVIDENCE_PENDING"
        )
        assert applied["readbackVerified"] is False
        assert applied["mutationPerformed"] is True
        assert applied["mutationAttempted"] is True
        assert applied["mutationPossible"] is False
        assert applied["evidence"]["structuralReadbackVerified"] is True
        assert applied["evidence"]["executionEvidenceVerified"] is False
        assert applied["nextAction"] == (
            "run_and_verify_exact_lane_execution_canary"
        )
    else:
        assert applied["ok"] is True
        assert applied["readbackVerified"] is True
    assert not any(
        call["path"].endswith("/activate")
        or call["path"].endswith("/deactivate")
        for call in session.calls
    )
    if operation == "activate":
        publish_call = next(
            call
            for call in session.calls
            if call["method"] == "POST" and call["path"] == endpoint
        )
        assert publish_call["json"] == {"versionId": "version-1"}


def test_apply_requires_owner_gate_and_fresh_hash() -> None:
    session = StatefulN8N("sovereign")
    disabled = runtime_for(session, write=False)
    no_owner = disabled.apply(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Evidence Watch"},
        confirmation_sha256="a" * 64,
        owner_approved=False,
    )
    assert no_owner["failureFamily"] == "N8N_OWNER_APPROVAL_REQUIRED"
    assert session.calls == []

    no_write = disabled.apply(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Evidence Watch"},
        confirmation_sha256="a" * 64,
        owner_approved=True,
    )
    assert no_write["failureFamily"] == "N8N_WORKFLOW_WRITE_DISABLED"
    assert session.calls == []

    runtime = runtime_for(session)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Evidence Watch"},
    )
    stale = runtime.apply(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Changed Evidence"},
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )
    assert stale["failureFamily"] == "N8N_WORKFLOW_PLAN_STALE"
    assert not any(call["method"] != "GET" for call in session.calls)


@pytest.mark.parametrize(
    ("operation", "active"),
    [("activate", True), ("pause", False)],
)
def test_already_reached_publish_state_is_verified_noop(
    operation: str,
    active: bool,
) -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime, active=active)
    plan = runtime.plan(
        lane_id="sovereign",
        operation=operation,
        workflow_id="workflow-1",
    )
    calls_before_apply = len(session.calls)
    applied = runtime.apply(
        lane_id="sovereign",
        operation=operation,
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    if operation == "activate":
        assert applied["ok"] is False
        assert applied["status"] == (
            "N8N_WORKFLOW_ACTIVATION_PENDING_EXECUTION_EVIDENCE"
        )
        assert applied["failureFamily"] == (
            "N8N_ACTIVATION_EXECUTION_EVIDENCE_PENDING"
        )
        assert applied["readbackVerified"] is False
        assert applied["evidence"]["structuralReadbackVerified"] is True
        assert applied["evidence"]["executionEvidenceVerified"] is False
    else:
        assert applied["ok"] is True
        assert applied["status"] == "N8N_WORKFLOW_ALREADY_IN_DESIRED_STATE"
        assert applied["readbackVerified"] is True
    assert applied["mutationPerformed"] is False
    assert not any(
        call["method"] != "GET"
        for call in session.calls[calls_before_apply:]
    )


@pytest.mark.parametrize("status_code", [302, 307])
def test_redirect_response_is_not_followed_or_given_the_lane_key(
    tmp_path: Path,
    status_code: int,
) -> None:
    class RedirectSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
            self.calls.append(
                {
                    "method": method,
                    "url": url,
                    "allow_redirects": kwargs.get("allow_redirects"),
                    "headers": dict(kwargs.get("headers") or {}),
                }
            )
            return FakeResponse(
                {"location": "https://attacker.invalid/collect"},
                status_code=status_code,
            )

    session = RedirectSession()
    runtime = RuntimeUnderTest(
        session=session,
        environ={},
        lock_root=tmp_path / "locks",
    )
    result = runtime.plan(
        lane_id="sovereign",
        operation="inventory",
    )

    assert result["ok"] is False
    assert result["failureFamily"] == f"N8N_API_HTTP_{status_code}"
    assert len(session.calls) == 1
    assert session.calls[0]["url"] == API_ROOT + "/projects"
    assert session.calls[0]["allow_redirects"] is False
    assert session.calls[0]["headers"]["X-N8N-API-KEY"] == (
        "lane-api-key-for-tests"
    )


def test_parallel_create_confirmation_can_mutate_only_once() -> None:
    session = StatefulN8N("sovereign")
    first_runtime = runtime_for(session)
    second_runtime = runtime_for(session)
    spec = {"name": "Serialized Evidence", "schedule_minutes": 15}
    plan = first_runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
    )
    barrier = Barrier(2)

    def invoke(runtime: RuntimeUnderTest) -> dict[str, Any]:
        barrier.wait()
        return runtime.apply(
            lane_id="sovereign",
            operation="create_draft",
            spec=spec,
            confirmation_sha256=plan["confirmationSha256"],
            owner_approved=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(invoke, first_runtime),
            executor.submit(invoke, second_runtime),
        ]
        results = [future.result(timeout=5) for future in futures]

    assert sum(result["ok"] is True for result in results) == 1
    stale = next(result for result in results if result["ok"] is False)
    assert stale["failureFamily"] == "N8N_WORKFLOW_ALREADY_EXISTS"
    assert len(
        [
            call
            for call in session.calls
            if call["method"] == "POST"
            and call["path"] == "/workflows"
        ]
    ) == 1


def test_second_create_plan_is_blocked_for_an_existing_lane_workflow() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime)

    blocked = runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Duplicate Evidence", "schedule_minutes": 15},
    )

    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_WORKFLOW_ALREADY_EXISTS"


def test_evidence_capabilities_are_lane_derived_and_domain_bound() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    master = "evidence-capability-value-for-tests"

    def expected(lane_id: str) -> str:
        lane = _LANES[lane_id]
        message = "\n".join(
            (
                EVIDENCE_CAPABILITY_CONTEXT,
                lane.repository,
                lane.workflow_selector,
                "main",
            )
        ).encode("utf-8")
        return hmac.new(
            master.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

    sovereign = runtime._evidence_capability(_LANES["sovereign"])
    aurion = runtime._evidence_capability(_LANES["aurion"])
    assert sovereign == expected("sovereign")
    assert aurion == expected("aurion")
    assert sovereign != aurion
    assert master not in {sovereign, aurion}


def test_community_personal_project_hides_foreign_and_cross_lane_workflows() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    assert _LANES["sovereign"].project_name == "Personal"
    assert _LANES["aurion"].project_name == "Personal"

    owned = session.add_workflow(runtime, workflow_id="sovereign-owned")
    foreign = copy.deepcopy(owned)
    foreign["id"] = "foreign-manual"
    foreign["nodes"][0]["id"] = "manual-node-id"
    session.workflows["foreign-manual"] = foreign

    aurion_definition = runtime._definition(
        _LANES["aurion"],
        "credential-aurion",
        CIEvidenceWatchSpec(name="Aurion Evidence"),
    )
    session.workflows["aurion-owned"] = {
        **aurion_definition,
        "id": "aurion-owned",
        "active": False,
        "versionId": "version-aurion",
        "updatedAt": "2026-09-01T00:00:00Z",
    }

    inventory = runtime.plan(lane_id="sovereign", operation="inventory")
    assert inventory["ok"] is True
    assert [workflow["id"] for workflow in inventory["workflows"]] == [
        "sovereign-owned"
    ]
    assert inventory["workflows"][0]["compilerOwned"] is True
    assert inventory["workflows"][0]["lane"] == "sovereign"

    wrong_credential = copy.deepcopy(owned)
    wrong_credential["id"] = "foreign-credential"
    receipt = next(
        node
        for node in wrong_credential["nodes"]
        if node["type"] == "n8n-nodes-base.httpRequest"
    )
    receipt["credentials"]["httpHeaderAuth"]["id"] = "credential-foreign"
    session.workflows["foreign-credential"] = wrong_credential

    blocked_foreign = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="foreign-manual",
    )
    assert blocked_foreign["ok"] is False
    assert blocked_foreign["failureFamily"] == "N8N_WORKFLOW_NOT_COMPILER_OWNED"

    blocked_cross_lane = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="aurion-owned",
    )
    assert blocked_cross_lane["ok"] is False
    assert blocked_cross_lane["failureFamily"] == "N8N_WORKFLOW_NOT_COMPILER_OWNED"

    blocked_credential = runtime.plan(
        lane_id="sovereign",
        operation="pause",
        workflow_id="foreign-credential",
    )
    assert blocked_credential["ok"] is False
    assert blocked_credential["failureFamily"] == "N8N_WORKFLOW_CREDENTIAL_MISMATCH"


def test_missing_current_credential_blocks_duplicate_lane_create() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    session.credentials.clear()

    blocked = runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec={"name": "Replacement Evidence", "schedule_minutes": 15},
    )

    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_WORKFLOW_CREDENTIAL_MISMATCH"


@pytest.mark.parametrize(
    "semantic_mutation",
    ("error_workflow", "disabled_node", "pin_data"),
)
def test_execution_semantic_extras_are_not_compiler_owned(
    semantic_mutation: str,
) -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    workflow = session.add_workflow(runtime)
    if semantic_mutation == "error_workflow":
        workflow["settings"]["errorWorkflow"] = "foreign-workflow"
    elif semantic_mutation == "disabled_node":
        workflow["nodes"][1]["disabled"] = True
    else:
        workflow["pinData"] = {"Submit Evidence Receipt": [{"json": {"ok": True}}]}

    blocked = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_WORKFLOW_NOT_COMPILER_OWNED"


def test_pre_effect_readback_blocks_a_raced_publish() -> None:
    class MutatingSession(StatefulN8N):
        def __init__(self) -> None:
            super().__init__("sovereign")
            self.credential_reads = 0

        def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
            response = super().request(method, url, **kwargs)
            if method == "GET" and url.endswith("/credentials"):
                self.credential_reads += 1
                if self.credential_reads == 3:
                    self.workflows["workflow-1"]["versionId"] = "raced-version"
            return response

    session = MutatingSession()
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    blocked = runtime.apply(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_WORKFLOW_PLAN_STALE"
    assert not any(
        call["method"] == "POST" and call["path"].endswith("/publish")
        for call in session.calls
    )


def test_direct_workflow_lookup_requires_exact_project_membership() -> None:
    session = StatefulN8N("sovereign")
    runtime = runtime_for(session)
    session.add_workflow(runtime, workflow_id="outside-project")
    session.outside_project_workflow_ids.add("outside-project")

    blocked = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="outside-project",
    )

    assert blocked["ok"] is False
    assert blocked["failureFamily"] == "N8N_WORKFLOW_PROJECT_MISMATCH"


def test_generated_stage1_compose_has_host_gateway_without_n8n_keys() -> None:
    from n8n_host_maintenance import N8NHostMaintenanceRuntime

    runtime = N8NHostMaintenanceRuntime()
    compose = runtime._stage1_compose(
        {
            "n8n": "n8nio/n8n@sha256:" + "a" * 64,
            "sandboxApi": "n8nio/runners@sha256:" + "b" * 64,
            "sandboxRunner": "n8nio/runners@sha256:" + "c" * 64,
            "innerSandbox": "n8nio/sandbox@sha256:" + "d" * 64,
        }
    )
    assert 'host.docker.internal:host-gateway' in compose
    assert "N8N_API_KEY" not in compose
    assert "n8n_sovereign_api_key" not in compose
    assert "n8n_aurion_api_key" not in compose


def test_production_session_ignores_environment_proxies_but_injected_session_is_unchanged(
    tmp_path: Path,
) -> None:
    production = N8NWorkflowAutomationRuntime(
        environ={},
        lock_root=tmp_path / "production-locks",
    )
    try:
        assert isinstance(production._session, requests.Session)
        assert production._session.trust_env is False
    finally:
        production._session.close()

    injected = StatefulN8N("sovereign")
    injected.trust_env = "injected-session-setting"  # type: ignore[attr-defined]
    runtime = N8NWorkflowAutomationRuntime(
        session=injected,  # type: ignore[arg-type]
        environ={},
        lock_root=tmp_path / "injected-locks",
    )
    assert runtime._session is injected
    assert runtime._session.trust_env == "injected-session-setting"
    assert EVIDENCE_HEADER_NAME == "X-Sovereign-Evidence-Capability"


def test_create_commit_then_transport_error_is_reconciled_by_exact_lane_inventory() -> None:
    session = AmbiguousWriteSession(
        "sovereign",
        target_path="/workflows",
        commit_before_error=True,
    )
    runtime = runtime_for(session)
    spec = {"name": "Recovered Create", "schedule_minutes": 15}
    plan = runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
    )

    applied = runtime.apply(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is True
    assert applied["status"] == (
        "N8N_WORKFLOW_APPLIED_VERIFIED_AFTER_AMBIGUOUS_RESPONSE"
    )
    assert applied["reconciledAfterAmbiguousResponse"] is True
    assert applied["readbackVerified"] is True
    assert applied["readback"]["active"] is False
    assert applied["workflowId"] == "workflow-new-1"
    assert applied["workflowWriteAttempted"] is True
    assert applied["mutationPerformed"] is True
    assert applied["mutationPossible"] is False
    assert len(
        [
            call
            for call in session.calls
            if call["method"] == "POST" and call["path"] == "/workflows"
        ]
    ) == 1


def test_activate_commit_then_transport_error_stays_pending_canary() -> None:
    session = AmbiguousWriteSession(
        "sovereign",
        target_path="/workflows/workflow-1/publish",
        commit_before_error=True,
    )
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    applied = runtime.apply(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is False
    assert applied["status"] == (
        "N8N_WORKFLOW_ACTIVATION_PENDING_EXECUTION_EVIDENCE"
    )
    assert applied["failureFamily"] == (
        "N8N_ACTIVATION_EXECUTION_EVIDENCE_PENDING"
    )
    assert applied["readback"]["active"] is True
    assert applied["readbackVerified"] is False
    assert applied["mutationPerformed"] is True
    assert applied["mutationAttempted"] is True
    assert applied["mutationPossible"] is False
    assert applied["reconciledAfterAmbiguousResponse"] is True
    assert applied["evidence"]["definitionVerified"] is True
    assert applied["evidence"]["projectBound"] is True
    assert applied["evidence"]["structuralReadbackVerified"] is True
    assert applied["evidence"]["executionEvidenceVerified"] is False


def test_unverified_transport_write_is_reported_as_outcome_uncertain() -> None:
    session = AmbiguousWriteSession(
        "sovereign",
        target_path="/workflows/workflow-1/publish",
        commit_before_error=False,
    )
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    applied = runtime.apply(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is False
    assert applied["status"] == "N8N_WORKFLOW_APPLY_OUTCOME_UNCERTAIN"
    assert applied["failureFamily"] == "OUTCOME_UNCERTAIN"
    assert applied["observedEffect"] == "outcome-uncertain"
    assert applied["mutationPerformed"] is False
    assert applied["mutationAttempted"] is True
    assert applied["mutationPossible"] is True
    assert applied["workflowWriteAttempted"] is True
    assert applied["readbackVerified"] is False


def test_committed_activation_http_503_is_reconciled_but_pending_canary() -> None:
    session = AmbiguousWriteSession(
        "sovereign",
        target_path="/workflows/workflow-1/publish",
        commit_before_error=True,
        response_status=503,
    )
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    applied = runtime.apply(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is False
    assert applied["status"] == (
        "N8N_WORKFLOW_ACTIVATION_PENDING_EXECUTION_EVIDENCE"
    )
    assert applied["failureFamily"] == (
        "N8N_ACTIVATION_EXECUTION_EVIDENCE_PENDING"
    )
    assert applied["evidence"]["originalFailureFamily"] == "N8N_API_HTTP_503"
    assert applied["evidence"]["structuralReadbackVerified"] is True
    assert applied["evidence"]["executionEvidenceVerified"] is False
    assert applied["readback"]["active"] is True
    assert applied["readbackVerified"] is False
    assert applied["mutationPerformed"] is True
    assert applied["mutationAttempted"] is True
    assert applied["mutationPossible"] is False


def test_http_4xx_write_rejection_is_not_reported_as_possible_mutation() -> None:
    session = AmbiguousWriteSession(
        "sovereign",
        target_path="/workflows/workflow-1/publish",
        commit_before_error=False,
        response_status=409,
    )
    runtime = runtime_for(session)
    session.add_workflow(runtime)
    plan = runtime.plan(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
    )

    applied = runtime.apply(
        lane_id="sovereign",
        operation="activate",
        workflow_id="workflow-1",
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is False
    assert applied["failureFamily"] == "N8N_API_HTTP_409"
    assert applied["observedEffect"] == "rejected"
    assert applied["mutationPerformed"] is False
    assert applied["mutationAttempted"] is True
    assert applied["mutationPossible"] is False


def test_credential_commit_then_transport_error_is_possible_not_confirmed_mutation() -> None:
    session = AmbiguousWriteSession(
        "aurion",
        target_path="/credentials",
        commit_before_error=True,
        credential_present=False,
    )
    runtime = runtime_for(session)
    spec = {"name": "Aurion Credential Recovery", "schedule_minutes": 15}
    plan = runtime.plan(
        lane_id="aurion",
        operation="create_draft",
        spec=spec,
    )

    applied = runtime.apply(
        lane_id="aurion",
        operation="create_draft",
        spec=spec,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert applied["ok"] is False
    assert applied["status"] == "N8N_WORKFLOW_APPLY_OUTCOME_UNCERTAIN"
    assert applied["failureFamily"] == "OUTCOME_UNCERTAIN"
    assert applied["credentialWriteAttempted"] is True
    assert applied["credentialBootstrapped"] is False
    assert applied["workflowWriteAttempted"] is False
    assert applied["mutationPerformed"] is False
    assert applied["mutationAttempted"] is True
    assert applied["mutationPossible"] is True


def test_create_rechecks_exact_inventory_and_blocks_external_race_before_post() -> None:
    session = CreateInventoryRaceSession()
    runtime = runtime_for(session)
    session.arm_external_create(runtime)
    spec = {"name": "Confirmed Empty Lane", "schedule_minutes": 15}
    plan = runtime.plan(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
    )
    assert plan["ok"] is True
    assert plan["currentState"]["workflowCount"] == 0

    applied = runtime.apply(
        lane_id="sovereign",
        operation="create_draft",
        spec=spec,
        confirmation_sha256=plan["confirmationSha256"],
        owner_approved=True,
    )

    assert session.workflow_list_reads == 3
    assert "external-race-workflow" in session.workflows
    assert applied["ok"] is False
    assert applied["failureFamily"] == "N8N_WORKFLOW_PLAN_STALE"
    assert applied["workflowWriteAttempted"] is False
    assert applied["mutationPerformed"] is False
    assert applied["observedEffect"] == "none"
    assert not any(
        call["method"] == "POST" and call["path"] == "/workflows"
        for call in session.calls
    )
