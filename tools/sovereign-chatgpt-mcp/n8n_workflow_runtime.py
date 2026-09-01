from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator


API_ROOT = "http://127.0.0.1:5678/api/v1"
TOOLCHAIN_EVIDENCE_URL = "http://host.docker.internal:8002/api/v1/n8n/ci-evidence"
WRITE_ENABLE_ENV = "SOVEREIGN_MCP_ENABLE_N8N_WORKFLOW_WRITE"
EVIDENCE_KEY_FILE = Path("/etc/sovereign-toolchain/n8n-evidence.key")
EVIDENCE_CREDENTIAL_TYPE = "httpHeaderAuth"
EVIDENCE_HEADER_NAME = "X-Sovereign-Evidence-Capability"
EVIDENCE_CAPABILITY_CONTEXT = "sovereign.n8n-ci-evidence-capability.v1"
DEFAULT_LOCK_ROOT = Path("/run/sovereign-chatgpt-broker/n8n-workflows")
MAX_WORKFLOW_NODES = 32
MIN_SCHEDULE_MINUTES = 15
_MAX_API_PAGES = 10
_MAX_KEY_BYTES = 4096
_WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_CONFIG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_NODE_TYPES = frozenset(
    {
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.httpRequest",
    }
)


class CIEvidenceWatchSpec(BaseModel):
    """The only typed workflow family accepted by this control plane."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["sovereign.n8n-ci-evidence-watch-spec.v1"] = (
        "sovereign.n8n-ci-evidence-watch-spec.v1"
    )
    kind: Literal["ci_evidence_watch"] = "ci_evidence_watch"
    name: str = Field(min_length=3, max_length=80)
    schedule_minutes: int = Field(default=15, ge=MIN_SCHEDULE_MINUTES, le=1440)
    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{2,79}", value):
            raise ValueError("name contains unsupported characters")
        lowered = value.lower()
        if "://" in value or "{{" in value or any(
            marker in lowered
            for marker in ("password", "secret", "token", "api_key", "apikey")
        ):
            raise ValueError("name contains a forbidden marker")
        return value

@dataclass(frozen=True)
class LaneConfig:
    lane_id: Literal["sovereign", "aurion"]
    repository: str
    project_name: str
    api_key_file: Path
    evidence_credential_name: str
    workflow_selector: str


_LANES: dict[str, LaneConfig] = {
    "sovereign": LaneConfig(
        lane_id="sovereign",
        repository="OuroborosCollective/Sovereign-Studio-ato",
        project_name="Personal",
        api_key_file=Path(
            "/opt/sovereign-owner-managed/n8n_sovereign_api_key.txt"
        ),
        evidence_credential_name="Sovereign Toolchain Evidence",
        workflow_selector="sovereign-coordinated-release.yml",
    ),
    "aurion": LaneConfig(
        lane_id="aurion",
        repository="OuroborosCollective/Echoes_of_Aurion",
        project_name="Personal",
        api_key_file=Path(
            "/opt/sovereign-owner-managed/n8n_aurion_api_key.txt"
        ),
        evidence_credential_name="Aurion Toolchain Evidence",
        workflow_selector="340269357",
    ),
}


class WorkflowAutomationError(RuntimeError):
    def __init__(self, failure_family: str, blocker: str) -> None:
        super().__init__(blocker)
        self.failure_family = failure_family
        self.blocker = blocker


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _definition_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    nodes = value.get("nodes") if isinstance(value.get("nodes"), list) else []
    projected_nodes: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        projected_nodes.append(
            {
                key: node[key]
                for key in (
                    "id",
                    "name",
                    "type",
                    "typeVersion",
                    "position",
                    "parameters",
                    "credentials",
                )
                if key in node
            }
        )
    settings = value.get("settings")
    projected_settings = (
        {"executionOrder": settings["executionOrder"]}
        if isinstance(settings, dict) and "executionOrder" in settings
        else {}
    )
    return {
        "name": str(value.get("name") or ""),
        "nodes": projected_nodes,
        "connections": (
            value.get("connections")
            if isinstance(value.get("connections"), dict)
            else {}
        ),
        "settings": projected_settings,
    }


def _definition_confirmation_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    projected = json.loads(
        json.dumps(_definition_projection(value), ensure_ascii=False)
    )
    for node in projected["nodes"]:
        credentials = node.get("credentials")
        if not isinstance(credentials, dict):
            continue
        binding = credentials.get("httpHeaderAuth")
        if isinstance(binding, dict) and binding.get("id"):
            binding["id"] = "__fixed_lane_evidence_credential__"
    return projected


def _failure(
    status: str,
    failure_family: str,
    blocker: str,
    *,
    next_action: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schemaVersion": "sovereign.n8n-workflow-control.v1",
        "ok": False,
        "status": status,
        "failureFamily": failure_family,
        "blocker": blocker,
        "mutationPerformed": False,
        "nextAction": next_action,
        "evidence": {},
        "data": {},
        "secretValuesReturned": False,
        **extra,
    }


class N8NWorkflowAutomationRuntime:
    """Host-broker runtime for fixed, project-bound n8n Public API operations."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        lane_configs: Mapping[str, LaneConfig] | None = None,
        environ: Mapping[str, str] | None = None,
        evidence_key_file: Path = EVIDENCE_KEY_FILE,
        lock_root: Path = DEFAULT_LOCK_ROOT,
    ) -> None:
        if session is None:
            self._session = requests.Session()
            self._session.trust_env = False
        else:
            self._session = session
        self._lanes = dict(_LANES if lane_configs is None else lane_configs)
        self._environ = dict(os.environ if environ is None else environ)
        self._evidence_key_file = evidence_key_file
        self._lock_root = lock_root

    def _lane(self, lane_id: str) -> LaneConfig:
        normalized = str(lane_id or "").strip().lower()
        expected = _LANES.get(normalized)
        lane = self._lanes.get(normalized)
        if expected is None or lane is None:
            raise WorkflowAutomationError(
                "N8N_LANE_NOT_ALLOWLISTED",
                "lane must be exactly sovereign or aurion",
            )
        if (
            lane.lane_id != expected.lane_id
            or lane.repository != expected.repository
            or lane.project_name != expected.project_name
            or lane.api_key_file != expected.api_key_file
            or lane.evidence_credential_name != expected.evidence_credential_name
            or lane.workflow_selector != expected.workflow_selector
        ):
            raise WorkflowAutomationError(
                "N8N_LANE_BINDING_INVALID",
                "lane repository, project, or credential binding is not allowlisted",
            )
        return lane

    @staticmethod
    def _workflow_id(value: str, *, required: bool) -> str:
        normalized = str(value or "").strip()
        if not normalized and not required:
            return ""
        if not _WORKFLOW_ID_RE.fullmatch(normalized):
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_ID_INVALID",
                "workflow_id is missing or not a valid bounded n8n identifier",
            )
        return normalized

    @staticmethod
    def _spec(
        value: Mapping[str, Any] | None, *, required: bool
    ) -> CIEvidenceWatchSpec | None:
        if value is None:
            if required:
                raise WorkflowAutomationError(
                    "N8N_WORKFLOW_SPEC_REQUIRED",
                    "a typed ci_evidence_watch spec is required for this operation",
                )
            return None
        if not required:
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_SPEC_NOT_ALLOWED",
                "this operation does not accept a workflow spec",
            )
        try:
            return CIEvidenceWatchSpec.model_validate(dict(value))
        except Exception as exc:
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_SPEC_INVALID",
                f"typed ci_evidence_watch spec rejected: {type(exc).__name__}",
            ) from None

    @staticmethod
    def _read_root_secret(path: Path, *, purpose: str) -> str:
        try:
            before = path.lstat()
        except OSError as exc:
            raise WorkflowAutomationError(
                f"{purpose}_FILE_UNAVAILABLE",
                f"required root-owned file is unavailable: {type(exc).__name__}",
            ) from None
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise WorkflowAutomationError(
                f"{purpose}_FILE_INVALID",
                "required path must be a regular non-symlink file",
            )
        if (
            before.st_uid != 0
            or before.st_gid != 0
            or stat.S_IMODE(before.st_mode) != 0o600
        ):
            raise WorkflowAutomationError(
                f"{purpose}_FILE_PERMISSIONS",
                "required file must be root:root with mode 0600",
            )
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as handle:
                observed = os.fstat(handle.fileno())
                if (
                    observed.st_dev != before.st_dev
                    or observed.st_ino != before.st_ino
                    or not stat.S_ISREG(observed.st_mode)
                    or observed.st_uid != 0
                    or observed.st_gid != 0
                    or stat.S_IMODE(observed.st_mode) != 0o600
                ):
                    raise WorkflowAutomationError(
                        f"{purpose}_FILE_CHANGED",
                        "required file changed during secure open",
                    )
                raw = handle.read(_MAX_KEY_BYTES + 1)
        except WorkflowAutomationError:
            raise
        except OSError as exc:
            raise WorkflowAutomationError(
                f"{purpose}_FILE_UNAVAILABLE",
                f"required file could not be opened securely: {type(exc).__name__}",
            ) from None
        if len(raw) > _MAX_KEY_BYTES:
            raise WorkflowAutomationError(
                f"{purpose}_FILE_INVALID",
                "required value exceeds the bounded file size",
            )
        try:
            value = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise WorkflowAutomationError(
                f"{purpose}_FILE_INVALID",
                "required file is not UTF-8",
            ) from None
        if len(value) < 16 or any(marker in value for marker in ("\n", "\r", "\x00")):
            raise WorkflowAutomationError(
                f"{purpose}_FILE_INVALID",
                "required value is empty or malformed",
            )
        return value

    def _api_key(self, lane: LaneConfig) -> str:
        return self._read_root_secret(
            lane.api_key_file, purpose="N8N_LANE_API_KEY"
        )

    def _evidence_capability(self, lane: LaneConfig) -> str:
        master = self._read_root_secret(
            self._evidence_key_file,
            purpose="N8N_EVIDENCE_KEY",
        )
        owner, repo = lane.repository.split("/", 1)
        message = "\n".join(
            (
                EVIDENCE_CAPABILITY_CONTEXT,
                f"{owner}/{repo}",
                lane.workflow_selector,
                "main",
            )
        ).encode("utf-8")
        return hmac.new(
            master.encode("utf-8"), message, hashlib.sha256
        ).hexdigest()

    def _request(
        self,
        api_key: str,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._session.request(
                method,
                f"{API_ROOT}{path}",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-N8N-API-KEY": api_key,
                },
                params=dict(params or {}),
                json=dict(json_body) if json_body is not None else None,
                timeout=(3.05, 30),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WorkflowAutomationError(
                "N8N_API_UNAVAILABLE",
                f"loopback n8n API request failed: {type(exc).__name__}",
            ) from None
        if response.status_code < 200 or response.status_code >= 300:
            raise WorkflowAutomationError(
                f"N8N_API_HTTP_{response.status_code}",
                "loopback n8n API rejected the bounded request",
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise WorkflowAutomationError(
                "N8N_API_RESPONSE_INVALID",
                "loopback n8n API returned non-JSON data",
            ) from None

    def _list_endpoint(
        self,
        api_key: str,
        path: str,
        *,
        base_params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = ""
        for _page in range(_MAX_API_PAGES):
            params: dict[str, Any] = {
                **dict(base_params or {}),
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            payload = self._request(api_key, "GET", path, params=params)
            if isinstance(payload, list):
                page_rows = payload
                next_cursor = ""
            elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
                page_rows = payload["data"]
                next_cursor = str(payload.get("nextCursor") or "")
            else:
                raise WorkflowAutomationError(
                    "N8N_API_RESPONSE_INVALID",
                    f"{path} did not contain a bounded data list",
                )
            rows.extend(item for item in page_rows if isinstance(item, dict))
            if not next_cursor:
                return rows
            cursor = next_cursor
        raise WorkflowAutomationError(
            "N8N_API_PAGINATION_LIMIT",
            f"{path} exceeded the bounded pagination limit",
        )

    def _project(self, lane: LaneConfig, api_key: str) -> dict[str, str]:
        projects = self._list_endpoint(api_key, "/projects")
        exact = [
            row
            for row in projects
            if str(row.get("name") or "") == lane.project_name
            and _CONFIG_ID_RE.fullmatch(str(row.get("id") or ""))
        ]
        if len(exact) != 1:
            raise WorkflowAutomationError(
                "PROJECT_BINDING_UNAVAILABLE",
                "n8n Public API must return exactly one allowlisted project-name match",
            )
        return {"id": str(exact[0]["id"]), "name": lane.project_name}

    @staticmethod
    def _credential_project_id(row: Mapping[str, Any]) -> str:
        direct = str(row.get("projectId") or "")
        if direct:
            return direct
        for key in ("project", "homeProject"):
            nested = row.get(key)
            if isinstance(nested, dict) and nested.get("id"):
                return str(nested["id"])
        shared = row.get("shared")
        if isinstance(shared, list) and len(shared) == 1:
            item = shared[0]
            if isinstance(item, dict):
                project = item.get("project")
                if isinstance(project, dict) and project.get("id"):
                    return str(project["id"])
                if item.get("projectId"):
                    return str(item["projectId"])
        return ""

    def _credential(
        self,
        lane: LaneConfig,
        api_key: str,
        project: Mapping[str, str],
    ) -> dict[str, Any]:
        credentials = self._list_endpoint(api_key, "/credentials")
        named = [
            row
            for row in credentials
            if str(row.get("name") or "") == lane.evidence_credential_name
            and str(row.get("type") or row.get("typeName") or "")
            == EVIDENCE_CREDENTIAL_TYPE
        ]
        for row in named:
            if not self._credential_project_id(row):
                raise WorkflowAutomationError(
                    "CREDENTIAL_BINDING_UNAVAILABLE",
                    "n8n credential readback did not expose an exact project binding",
                )
        exact = [
            row
            for row in named
            if self._credential_project_id(row) == project["id"]
            and _CONFIG_ID_RE.fullmatch(str(row.get("id") or ""))
        ]
        if len(exact) > 1:
            raise WorkflowAutomationError(
                "CREDENTIAL_BINDING_AMBIGUOUS",
                "multiple exact evidence credentials exist in the selected project",
            )
        if not exact:
            return {
                "present": False,
                "id": None,
                "name": lane.evidence_credential_name,
                "type": EVIDENCE_CREDENTIAL_TYPE,
                "projectId": project["id"],
            }
        return {
            "present": True,
            "id": str(exact[0]["id"]),
            "name": lane.evidence_credential_name,
            "type": EVIDENCE_CREDENTIAL_TYPE,
            "projectId": project["id"],
        }

    def _bootstrap_credential(
        self,
        lane: LaneConfig,
        api_key: str,
        project: Mapping[str, str],
        evidence_value: str,
    ) -> dict[str, Any]:
        self._request(
            api_key,
            "POST",
            "/credentials",
            json_body={
                "name": lane.evidence_credential_name,
                "type": EVIDENCE_CREDENTIAL_TYPE,
                "projectId": project["id"],
                "data": {
                    "name": EVIDENCE_HEADER_NAME,
                    "value": evidence_value,
                },
            },
        )
        try:
            readback = self._credential(lane, api_key, project)
        except WorkflowAutomationError:
            raise WorkflowAutomationError(
                "CREDENTIAL_BOOTSTRAP_OUTCOME_UNCERTAIN",
                "credential create returned but exact project readback could not be verified",
            ) from None
        if not readback["present"]:
            raise WorkflowAutomationError(
                "CREDENTIAL_BOOTSTRAP_OUTCOME_UNCERTAIN",
                "credential create returned but exact project readback is absent",
            )
        return readback

    @staticmethod
    def _summary(
        workflow: Mapping[str, Any], project_id: str
    ) -> dict[str, Any]:
        definition = {
            "name": str(workflow.get("name") or ""),
            "nodes": (
                workflow.get("nodes")
                if isinstance(workflow.get("nodes"), list)
                else []
            ),
            "connections": (
                workflow.get("connections")
                if isinstance(workflow.get("connections"), dict)
                else {}
            ),
            "settings": (
                workflow.get("settings")
                if isinstance(workflow.get("settings"), dict)
                else {}
            ),
        }
        return {
            "id": str(workflow.get("id") or ""),
            "name": str(workflow.get("name") or "")[:160],
            "active": bool(workflow.get("active", False)),
            "archived": bool(workflow.get("isArchived", False)),
            "versionId": str(workflow.get("versionId") or ""),
            "updatedAt": str(workflow.get("updatedAt") or ""),
            "projectId": project_id,
            "nodeCount": len(definition["nodes"]),
            "definitionSha256": _canonical_sha256(_definition_projection(definition)),
        }

    @classmethod
    @staticmethod
    def _readback_semantics_are_bounded(
        workflow: Mapping[str, Any],
    ) -> bool:
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list):
            return False
        for node in nodes:
            if not isinstance(node, dict):
                return False
            allowed_keys = {
                "id",
                "name",
                "type",
                "typeVersion",
                "position",
                "parameters",
            }
            if node.get("type") == "n8n-nodes-base.httpRequest":
                allowed_keys.add("credentials")
            if set(node) != allowed_keys:
                return False
        settings = workflow.get("settings")
        if not isinstance(settings, dict):
            return False
        allowed_readback_settings = {
            "executionOrder": "v1",
            "saveManualExecutions": False,
            "callerPolicy": "workflowsFromSameOwner",
        }
        if any(
            key not in allowed_readback_settings
            or value != allowed_readback_settings[key]
            for key, value in settings.items()
        ):
            return False
        for field in ("pinData", "staticData"):
            if field in workflow and workflow.get(field) not in (None, {}):
                return False
        return True

    @classmethod
    def _compiler_owned_definition(
        cls,
        workflow: Mapping[str, Any],
        lane: LaneConfig,
        expected_credential_id: str | None,
    ) -> bool:
        if not cls._readback_semantics_are_bounded(workflow):
            return False
        nodes = workflow.get("nodes")
        if not isinstance(nodes, list):
            return False
        schedule = next(
            (
                node
                for node in nodes
                if isinstance(node, dict)
                and node.get("id") == cls._node_id(lane, "schedule")
                and node.get("type") == "n8n-nodes-base.scheduleTrigger"
            ),
            None,
        )
        if not isinstance(schedule, dict):
            return False
        try:
            intervals = schedule["parameters"]["rule"]["interval"]
            if not isinstance(intervals, list) or len(intervals) != 1:
                return False
            interval = intervals[0]
            if not isinstance(interval, dict) or interval.get("field") != "minutes":
                return False
            spec = CIEvidenceWatchSpec(
                name=str(workflow.get("name") or ""),
                schedule_minutes=int(interval.get("minutesInterval")),
            )
            cls._validate_definition(
                _definition_projection(workflow),
                lane,
                spec,
                expected_credential_id=expected_credential_id,
            )
        except (KeyError, TypeError, ValueError, WorkflowAutomationError):
            return False
        return True

    def _inventory(
        self,
        lane: LaneConfig,
        api_key: str,
        project: Mapping[str, str],
        expected_credential_id: str,
    ) -> list[dict[str, Any]]:
        raw = self._list_endpoint(
            api_key,
            "/workflows",
            base_params={"projectId": project["id"]},
        )
        summaries: list[dict[str, Any]] = []
        for item in raw:
            workflow_id = str(item.get("id") or "")
            if not _WORKFLOW_ID_RE.fullmatch(workflow_id):
                continue
            payload = self._request(api_key, "GET", f"/workflows/{workflow_id}")
            if (
                not isinstance(payload, dict)
                or str(payload.get("id") or "") != workflow_id
            ):
                continue
            compiler_shaped = self._compiler_owned_definition(
                payload, lane, None
            )
            compiler_owned = (
                bool(_CONFIG_ID_RE.fullmatch(expected_credential_id))
                and self._compiler_owned_definition(
                    payload, lane, expected_credential_id
                )
            )
            if compiler_shaped and not compiler_owned:
                raise WorkflowAutomationError(
                    "N8N_WORKFLOW_CREDENTIAL_MISMATCH",
                    "lane-shaped workflow is not bound to the exact current evidence credential",
                )
            if not compiler_owned:
                continue
            summary = self._summary(payload, project["id"])
            summary["lane"] = lane.lane_id
            summary["compilerOwned"] = True
            summaries.append(summary)
        summaries.sort(key=lambda item: item["id"])
        return summaries

    def _workflow(
        self,
        lane: LaneConfig,
        api_key: str,
        project: Mapping[str, str],
        workflow_id: str,
        expected_credential_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        project_rows = self._list_endpoint(
            api_key,
            "/workflows",
            base_params={"projectId": project["id"]},
        )
        project_matches = [
            row
            for row in project_rows
            if str(row.get("id") or "") == workflow_id
        ]
        if len(project_matches) != 1:
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_PROJECT_MISMATCH",
                "workflow is not uniquely present in the selected n8n project",
            )
        payload = self._request(api_key, "GET", f"/workflows/{workflow_id}")
        if (
            not isinstance(payload, dict)
            or str(payload.get("id") or "") != workflow_id
        ):
            raise WorkflowAutomationError(
                "N8N_API_RESPONSE_INVALID",
                "n8n workflow readback did not match the requested identifier",
            )
        compiler_shaped = self._compiler_owned_definition(
            payload, lane, None
        )
        compiler_owned = (
            bool(_CONFIG_ID_RE.fullmatch(expected_credential_id))
            and self._compiler_owned_definition(
                payload, lane, expected_credential_id
            )
        )
        if compiler_shaped and not compiler_owned:
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_CREDENTIAL_MISMATCH",
                "lane-shaped workflow is not bound to the exact current evidence credential",
            )
        if not compiler_owned:
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_NOT_COMPILER_OWNED",
                "workflow is foreign or belongs to the other compiler-owned lane",
            )
        summary = self._summary(payload, project["id"])
        summary["lane"] = lane.lane_id
        summary["compilerOwned"] = True
        return payload, summary

    @staticmethod
    def _node_id(lane: LaneConfig, logical_name: str) -> str:
        return str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"sovereign:n8n:{lane.lane_id}:{logical_name}",
            )
        )

    def _definition(
        self,
        lane: LaneConfig,
        credential_id: str,
        spec: CIEvidenceWatchSpec,
    ) -> dict[str, Any]:
        repo_name = lane.repository.split("/", 1)[1]
        request_body = {
            "owner": "OuroborosCollective",
            "repo": repo_name,
            "branch": "main",
            "workflow_id": lane.workflow_selector,
            "previous_fingerprint": None,
        }
        nodes: list[dict[str, Any]] = [
            {
                "id": self._node_id(lane, "schedule"),
                "name": "Evidence Schedule",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [-240, 0],
                "parameters": {
                    "rule": {
                        "interval": [
                            {
                                "field": "minutes",
                                "minutesInterval": spec.schedule_minutes,
                            }
                        ]
                    }
                },
            },
            {
                "id": self._node_id(lane, "receipt"),
                "name": "Submit Evidence Receipt",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [0, 0],
                "credentials": {
                    "httpHeaderAuth": {
                        "id": credential_id,
                        "name": lane.evidence_credential_name,
                    }
                },
                "parameters": {
                    "method": "POST",
                    "url": TOOLCHAIN_EVIDENCE_URL,
                    "authentication": "genericCredentialType",
                    "genericAuthType": EVIDENCE_CREDENTIAL_TYPE,
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": json.dumps(
                        request_body,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "options": {},
                },
            },
        ]
        definition = {
            "name": spec.name,
            "nodes": nodes,
            "connections": {
                "Evidence Schedule": {
                    "main": [
                        [
                            {
                                "node": "Submit Evidence Receipt",
                                "type": "main",
                                "index": 0,
                            }
                        ]
                    ]
                }
            },
            "settings": {"executionOrder": "v1"},
        }
        self._validate_definition(
            definition,
            lane,
            spec,
            expected_credential_id=credential_id,
        )
        return definition

    @staticmethod
    def _validate_definition(
        definition: Mapping[str, Any],
        lane: LaneConfig,
        spec: CIEvidenceWatchSpec,
        *,
        expected_credential_id: str | None = None,
    ) -> None:
        nodes = definition.get("nodes")
        if (
            not isinstance(nodes, list)
            or len(nodes) != 2
            or len(nodes) > MAX_WORKFLOW_NODES
        ):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow must contain exactly two bounded nodes",
            )
        if spec.schedule_minutes < MIN_SCHEDULE_MINUTES:
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow schedule is below fifteen minutes",
            )
        node_types = {
            str(node.get("type") or "")
            for node in nodes
            if isinstance(node, dict)
        }
        if node_types != _ALLOWED_NODE_TYPES:
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow contains a non-allowlisted node type",
            )
        expected_nodes = {
            self_id: (name, node_type)
            for self_id, name, node_type in (
                (
                    N8NWorkflowAutomationRuntime._node_id(lane, "schedule"),
                    "Evidence Schedule",
                    "n8n-nodes-base.scheduleTrigger",
                ),
                (
                    N8NWorkflowAutomationRuntime._node_id(lane, "receipt"),
                    "Submit Evidence Receipt",
                    "n8n-nodes-base.httpRequest",
                ),
            )
        }
        observed_nodes = {
            str(node.get("id") or ""): node
            for node in nodes
            if isinstance(node, dict)
        }
        if set(observed_nodes) != set(expected_nodes):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow node identities do not match the lane compiler signature",
            )
        for node_id, (expected_name, expected_type) in expected_nodes.items():
            node = observed_nodes[node_id]
            if node.get("name") != expected_name or node.get("type") != expected_type:
                raise WorkflowAutomationError(
                    "N8N_GENERATED_WORKFLOW_INVALID",
                    "generated workflow node identity, name, or type is not compiler-owned",
                )
        schedule = observed_nodes[
            N8NWorkflowAutomationRuntime._node_id(lane, "schedule")
        ]
        expected_schedule = {
            "rule": {
                "interval": [
                    {
                        "field": "minutes",
                        "minutesInterval": spec.schedule_minutes,
                    }
                ]
            }
        }
        expected_connections = {
            "Evidence Schedule": {
                "main": [
                    [
                        {
                            "node": "Submit Evidence Receipt",
                            "type": "main",
                            "index": 0,
                        }
                    ]
                ]
            }
        }
        if (
            str(definition.get("name") or "") != spec.name
            or schedule.get("parameters") != expected_schedule
            or definition.get("connections") != expected_connections
            or definition.get("settings") != {"executionOrder": "v1"}
        ):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow topology or schedule does not match the compiler signature",
            )
        receipt_nodes = [
            node
            for node in nodes
            if isinstance(node, dict)
            and node.get("type") == "n8n-nodes-base.httpRequest"
        ]
        if len(receipt_nodes) != 1:
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow must contain one fixed HTTP receipt node",
            )
        receipt = receipt_nodes[0]
        parameters = receipt.get("parameters")
        if not isinstance(parameters, dict):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated receipt parameters are absent",
            )
        expected_body = {
            "owner": "OuroborosCollective",
            "repo": lane.repository.split("/", 1)[1],
            "branch": "main",
            "workflow_id": lane.workflow_selector,
            "previous_fingerprint": None,
        }
        try:
            observed_body = json.loads(str(parameters.get("jsonBody") or ""))
        except (TypeError, ValueError):
            observed_body = None
        credential_binding = (
            receipt.get("credentials", {}).get("httpHeaderAuth", {})
            if isinstance(receipt.get("credentials"), dict)
            else {}
        )
        credential_id = str(credential_binding.get("id") or "")
        if (
            receipt.get("typeVersion") != 4.2
            or receipt.get("position") != [0, 0]
            or schedule.get("typeVersion") != 1.2
            or schedule.get("position") != [-240, 0]
            or parameters.get("method") != "POST"
            or parameters.get("url") != TOOLCHAIN_EVIDENCE_URL
            or parameters.get("authentication") != "genericCredentialType"
            or parameters.get("genericAuthType") != EVIDENCE_CREDENTIAL_TYPE
            or parameters.get("sendBody") is not True
            or parameters.get("specifyBody") != "json"
            or parameters.get("options") != {}
            or observed_body != expected_body
            or not _CONFIG_ID_RE.fullmatch(credential_id)
            or (
                expected_credential_id is not None
                and credential_id != expected_credential_id
            )
            or credential_binding.get("name") != lane.evidence_credential_name
        ):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated receipt request does not match the fixed adapter contract",
            )
        serialized = json.dumps(definition, sort_keys=True)
        if any(
            marker in serialized
            for marker in (
                "n8n-nodes-base.code",
                "n8n-nodes-base.webhook",
                "n8n-nodes-base.executeCommand",
                "N8N_API_KEY",
                "api.github.com",
            )
        ):
            raise WorkflowAutomationError(
                "N8N_GENERATED_WORKFLOW_INVALID",
                "generated workflow contains a forbidden execution, URL, or key surface",
            )

    def plan(
        self,
        *,
        lane_id: str,
        operation: str,
        workflow_id: str = "",
        spec: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        operation = str(operation or "").strip()
        if operation not in {
            "inventory",
            "create_draft",
            "update_draft",
            "activate",
            "pause",
        }:
            return _failure(
                "N8N_WORKFLOW_PLAN_BLOCKED",
                "N8N_OPERATION_NOT_ALLOWLISTED",
                "operation must be inventory, create_draft, update_draft, activate, or pause",
            )
        try:
            lane = self._lane(lane_id)
            needs_id = operation in {"update_draft", "activate", "pause"}
            workflow_id = self._workflow_id(
                workflow_id, required=needs_id
            )
            if operation == "create_draft" and workflow_id:
                raise WorkflowAutomationError(
                    "N8N_WORKFLOW_ID_NOT_ALLOWED",
                    "create_draft does not accept a workflow_id",
                )
            typed_spec = self._spec(
                spec,
                required=operation in {"create_draft", "update_draft"},
            )
            api_key = self._api_key(lane)
            project = self._project(lane, api_key)
            credential = self._credential(lane, api_key, project)

            workflows: list[dict[str, Any]] = []
            if operation in {"inventory", "create_draft"}:
                workflows = self._inventory(
                    lane,
                    api_key,
                    project,
                    str(credential["id"] or ""),
                )
                if operation == "create_draft" and workflows:
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_ALREADY_EXISTS",
                        "the selected lane already has a compiler-owned workflow",
                    )
                current_state: dict[str, Any] = {
                    "projectId": project["id"],
                    "projectName": project["name"],
                    "workflowCount": len(workflows),
                    "inventorySha256": _canonical_sha256(workflows),
                }
            else:
                _raw, current_state = self._workflow(
                    lane,
                    api_key,
                    project,
                    workflow_id,
                    str(credential["id"] or ""),
                )
                if (
                    operation == "update_draft"
                    and current_state["active"]
                ):
                    raise WorkflowAutomationError(
                        "N8N_ACTIVE_WORKFLOW_UPDATE_BLOCKED",
                        "active workflows must be paused before update_draft",
                    )

            normalized_spec = (
                typed_spec.model_dump(mode="json")
                if typed_spec is not None
                else None
            )
            definition = (
                self._definition(
                    lane,
                    str(credential["id"] or "__fixed_bootstrap_required__"),
                    typed_spec,
                )
                if typed_spec is not None
                else None
            )
            definition_sha = (
                _canonical_sha256(
                    _definition_confirmation_projection(definition)
                )
                if definition is not None
                else None
            )
            credential_binding = {
                "present": bool(credential["present"]),
                "id": credential["id"],
                "name": credential["name"],
                "type": credential["type"],
                "projectId": credential["projectId"],
            }
            binding = {
                "schemaVersion": "sovereign.n8n-workflow-plan-binding.v1",
                "lane": lane.lane_id,
                "repository": lane.repository,
                "project": project,
                "operation": operation,
                "workflowId": workflow_id or None,
                "currentState": current_state,
                "currentVersionId": current_state.get("versionId"),
                "credential": credential_binding,
                "credentialResolutionMode": (
                    "existing-exact-id"
                    if credential["present"]
                    else "bootstrap-fixed-lane-capability"
                ),
                "spec": normalized_spec,
                "definitionSha256": definition_sha,
            }
            confirmation = _canonical_sha256(binding)
            desired_active = (
                True
                if operation == "activate"
                else False
                if operation
                in {"create_draft", "update_draft", "pause"}
                else None
            )
            result: dict[str, Any] = {
                "schemaVersion": "sovereign.n8n-workflow-plan.v1",
                "ok": True,
                "status": (
                    "N8N_WORKFLOW_INVENTORY_READY"
                    if operation == "inventory"
                    else "N8N_WORKFLOW_PLAN_READY"
                ),
                "failureFamily": None,
                "blocker": None,
                "lane": lane.lane_id,
                "repository": lane.repository,
                "projectId": project["id"],
                "projectName": project["name"],
                "operation": operation,
                "workflowId": workflow_id or None,
                "currentState": current_state,
                "credentialPresent": bool(credential["present"]),
                "credentialName": credential["name"],
                "credentialType": credential["type"],
                "credentialBindingSha256": _canonical_sha256(
                    credential_binding
                ),
                "desiredState": {
                    "active": desired_active,
                    "workflowKind": (
                        typed_spec.kind if typed_spec else None
                    ),
                    "definitionSha256": definition_sha,
                    "definitionHashMode": "fixed-credential-template",
                    "nodeCount": (
                        len(definition["nodes"]) if definition else None
                    ),
                    "nodeTypes": (
                        sorted(
                            {
                                str(node["type"])
                                for node in definition["nodes"]
                            }
                        )
                        if definition
                        else []
                    ),
                },
                "spec": normalized_spec,
                "confirmationSha256": confirmation,
                "ownerApprovalRequired": operation != "inventory",
                "mutationPerformed": False,
                "nextAction": (
                    None
                    if operation == "inventory"
                    else "call_n8n_workflow_apply_with_confirmation"
                ),
                "evidence": {
                    "apiRoot": API_ROOT,
                    "keyFileVerified": True,
                    "projectBound": True,
                    "currentStateSha256": _canonical_sha256(
                        current_state
                    ),
                },
                "data": {},
                "secretValuesReturned": False,
            }
            if operation == "inventory":
                result["workflows"] = workflows
                result["workflowCount"] = len(workflows)
            if operation == "activate":
                result["alreadyDesiredState"] = bool(
                    current_state.get("active")
                )
            elif operation == "pause":
                result["alreadyDesiredState"] = not bool(
                    current_state.get("active")
                )
            return result
        except WorkflowAutomationError as exc:
            return _failure(
                "N8N_WORKFLOW_PLAN_BLOCKED",
                exc.failure_family,
                exc.blocker,
                lane=str(lane_id or ""),
                operation=operation,
            )

    @staticmethod
    def _assert_confirmed_current_state(
        expected: Mapping[str, Any],
        observed: Mapping[str, Any],
    ) -> None:
        fields = (
            "id",
            "name",
            "active",
            "archived",
            "versionId",
            "updatedAt",
            "projectId",
            "nodeCount",
            "definitionSha256",
        )
        if any(expected.get(field) != observed.get(field) for field in fields):
            raise WorkflowAutomationError(
                "N8N_WORKFLOW_PLAN_STALE",
                "workflow changed after confirmation and before the external effect",
            )

    @contextmanager
    def _apply_lock(
        self,
        *,
        lane_id: str,
        operation: str,
        workflow_id: str,
    ):
        normalized_lane = (
            str(lane_id or "").strip().lower()
            if str(lane_id or "").strip().lower() in _LANES
            else "invalid-lane"
        )
        normalized_operation = (
            str(operation or "").strip()
            if str(operation or "").strip()
            in {"create_draft", "update_draft", "activate", "pause"}
            else "invalid-operation"
        )
        candidate_id = str(workflow_id or "").strip()
        target = (
            "create-draft"
            if normalized_operation == "create_draft"
            else candidate_id
            if _WORKFLOW_ID_RE.fullmatch(candidate_id)
            else "invalid-workflow"
        )
        identity = hashlib.sha256(
            f"{normalized_lane}:{target}".encode("utf-8")
        ).hexdigest()
        try:
            self._lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            root_state = self._lock_root.lstat()
        except OSError as exc:
            raise WorkflowAutomationError(
                "N8N_APPLY_LOCK_UNAVAILABLE",
                f"n8n apply lock root is unavailable: {type(exc).__name__}",
            ) from None
        if (
            self._lock_root.is_symlink()
            or not stat.S_ISDIR(root_state.st_mode)
            or root_state.st_uid != os.geteuid()
        ):
            raise WorkflowAutomationError(
                "N8N_APPLY_LOCK_INVALID",
                "n8n apply lock root must be a process-owned non-symlink directory",
            )
        os.chmod(self._lock_root, 0o700)
        lock_path = self._lock_root / f"{identity}.lock"
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_uid != os.geteuid()
            ):
                os.close(descriptor)
                raise WorkflowAutomationError(
                    "N8N_APPLY_LOCK_INVALID",
                    "n8n apply lock file must be process-owned and regular",
                )
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        except WorkflowAutomationError:
            raise
        except OSError as exc:
            raise WorkflowAutomationError(
                "N8N_APPLY_LOCK_UNAVAILABLE",
                f"n8n apply lock could not be acquired: {type(exc).__name__}",
            ) from None
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @staticmethod
    def _write_error_has_ambiguous_outcome(
        exc: WorkflowAutomationError,
    ) -> bool:
        if exc.failure_family in {
            "N8N_API_UNAVAILABLE",
            "N8N_API_RESPONSE_INVALID",
            "CREDENTIAL_BOOTSTRAP_OUTCOME_UNCERTAIN",
        }:
            return True
        match = re.fullmatch(r"N8N_API_HTTP_([0-9]{3})", exc.failure_family)
        return bool(match and 500 <= int(match.group(1)) <= 599)

    def _workflow_write_readback(
        self,
        *,
        lane: LaneConfig,
        api_key: str,
        project: Mapping[str, str],
        credential_id: str,
        operation: str,
        workflow_id: str,
        definition: Mapping[str, Any] | None,
        pre_effect: Mapping[str, Any] | None,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        desired_active = operation == "activate"
        desired_definition_sha = (
            _canonical_sha256(_definition_projection(definition))
            if definition is not None
            else str((pre_effect or {}).get("definitionSha256") or "")
        )
        resolved_workflow_id = workflow_id
        if operation == "create_draft" and not _WORKFLOW_ID_RE.fullmatch(
            resolved_workflow_id
        ):
            candidates = self._inventory(
                lane,
                api_key,
                project,
                credential_id,
            )
            matches = [
                candidate
                for candidate in candidates
                if candidate.get("definitionSha256") == desired_definition_sha
                and candidate.get("projectId") == project["id"]
                and candidate.get("active") is False
                and candidate.get("archived") is False
            ]
            if len(matches) != 1:
                raise WorkflowAutomationError(
                    "N8N_CREATE_RECONCILIATION_AMBIGUOUS",
                    "create response was ambiguous and exact lane inventory did not contain exactly one desired compiler-owned workflow",
                )
            readback = dict(matches[0])
            resolved_workflow_id = str(readback.get("id") or "")
        else:
            _raw, readback = self._workflow(
                lane,
                api_key,
                project,
                resolved_workflow_id,
                credential_id,
            )
        definition_verified = bool(
            desired_definition_sha
            and readback.get("definitionSha256") == desired_definition_sha
        )
        active_verified = readback.get("active") is desired_active
        project_verified = readback.get("projectId") == project["id"]
        archived_verified = readback.get("archived") is False
        return resolved_workflow_id, readback, {
            "verified": bool(
                definition_verified
                and active_verified
                and project_verified
                and archived_verified
            ),
            "definitionVerified": definition_verified,
            "activeStateVerified": active_verified,
            "projectBound": project_verified,
            "archivedStateVerified": archived_verified,
            "desiredDefinitionSha256": desired_definition_sha or None,
        }

    def apply(
        self,
        *,
        lane_id: str,
        operation: str,
        confirmation_sha256: str,
        owner_approved: bool,
        workflow_id: str = "",
        spec: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            with self._apply_lock(
                lane_id=lane_id,
                operation=operation,
                workflow_id=workflow_id,
            ):
                return self._apply_locked(
                    lane_id=lane_id,
                    operation=operation,
                    confirmation_sha256=confirmation_sha256,
                    owner_approved=owner_approved,
                    workflow_id=workflow_id,
                    spec=spec,
                )
        except WorkflowAutomationError as exc:
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                exc.failure_family,
                exc.blocker,
                ownerApproved=bool(owner_approved),
                readbackVerified=False,
            )

    def _apply_locked(
        self,
        *,
        lane_id: str,
        operation: str,
        confirmation_sha256: str,
        owner_approved: bool,
        workflow_id: str = "",
        spec: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        operation = str(operation or "").strip()
        if operation == "inventory":
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                "N8N_INVENTORY_IS_READ_ONLY",
                "inventory is available only through n8n_workflow_plan",
                ownerApproved=bool(owner_approved),
                readbackVerified=False,
            )
        if not owner_approved:
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                "N8N_OWNER_APPROVAL_REQUIRED",
                "owner_approved=true is required for n8n workflow writes",
                next_action="obtain_explicit_owner_approval",
                ownerApproved=False,
                readbackVerified=False,
            )
        if self._environ.get(WRITE_ENABLE_ENV, "").strip() != "1":
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                "N8N_WORKFLOW_WRITE_DISABLED",
                f"host write gate {WRITE_ENABLE_ENV}=1 is required",
                ownerApproved=True,
                readbackVerified=False,
            )
        supplied = str(confirmation_sha256 or "").strip().lower()
        if not _SHA256_RE.fullmatch(supplied):
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                "N8N_CONFIRMATION_INVALID",
                "confirmation_sha256 must be a lowercase SHA-256",
                ownerApproved=True,
                readbackVerified=False,
            )
        plan = self.plan(
            lane_id=lane_id,
            operation=operation,
            workflow_id=workflow_id,
            spec=spec,
        )
        if not plan.get("ok"):
            return {
                **plan,
                "status": "N8N_WORKFLOW_APPLY_BLOCKED",
                "ownerApproved": True,
                "readbackVerified": False,
            }
        expected = str(plan.get("confirmationSha256") or "")
        expected_revision = str(
            (plan.get("currentState") or {}).get("versionId") or ""
        ) or None
        if supplied != expected:
            return _failure(
                "N8N_WORKFLOW_APPLY_BLOCKED",
                "N8N_WORKFLOW_PLAN_STALE",
                "confirmation no longer matches current workflow, project, version, credential, and spec",
                next_action="replan_and_obtain_fresh_owner_confirmation",
                expectedConfirmationSha256=expected,
                ownerApproved=True,
                expectedRevision=expected_revision,
                readbackVerified=False,
            )
        if operation in {"activate", "pause"} and bool(
            plan.get("alreadyDesiredState")
        ):
            current_state = dict(plan.get("currentState") or {})
            resolved_workflow_id = str(plan.get("workflowId") or "")
            return {
                "schemaVersion": "sovereign.n8n-workflow-apply.v1",
                "ok": True,
                "status": "N8N_WORKFLOW_ALREADY_IN_DESIRED_STATE",
                "failureFamily": None,
                "blocker": None,
                "lane": plan.get("lane"),
                "repository": plan.get("repository"),
                "projectId": plan.get("projectId"),
                "projectName": plan.get("projectName"),
                "operation": operation,
                "workflowId": resolved_workflow_id,
                "operationId": resolved_workflow_id,
                "requestedEffect": operation,
                "observedEffect": "already-in-desired-state",
                "ownerApproved": True,
                "expectedRevision": expected_revision,
                "actualRevision": current_state.get("versionId") or None,
                "readback": current_state,
                "readbackVerified": True,
                "mutationPerformed": False,
                "credentialBootstrapped": False,
                "nextAction": None,
                "evidence": {
                    "confirmationSha256": expected,
                    "projectBound": True,
                    "activeStateVerified": True,
                },
                "data": {},
                "secretValuesReturned": False,
            }

        workflow_mutated = False
        credential_mutated = False
        workflow_write_attempted = False
        credential_write_attempted = False
        workflow_id = str(plan.get("workflowId") or "")
        lane: LaneConfig | None = None
        api_key = ""
        project: dict[str, str] | None = None
        credential: dict[str, Any] | None = None
        definition: dict[str, Any] | None = None
        pre_effect: dict[str, Any] | None = None
        try:
            lane = self._lane(lane_id)
            api_key = self._api_key(lane)
            project = self._project(lane, api_key)
            if (
                project["id"] != plan.get("projectId")
                or project["name"] != plan.get("projectName")
            ):
                raise WorkflowAutomationError(
                    "PROJECT_BINDING_CHANGED",
                    "exact n8n project binding changed after plan",
                )
            credential = self._credential(lane, api_key, project)
            typed_spec = self._spec(
                spec,
                required=operation
                in {"create_draft", "update_draft"},
            )
            if typed_spec is not None and not credential["present"]:
                evidence_value = self._evidence_capability(lane)
                credential_write_attempted = True
                credential = self._bootstrap_credential(
                    lane, api_key, project, evidence_value
                )
                credential_mutated = True
            observed_credential_binding = {
                "present": bool(credential["present"]),
                "id": credential["id"],
                "name": credential["name"],
                "type": credential["type"],
                "projectId": credential["projectId"],
            }
            if (
                _canonical_sha256(observed_credential_binding)
                != str(plan.get("credentialBindingSha256") or "")
                and not credential_mutated
            ):
                raise WorkflowAutomationError(
                    "CREDENTIAL_BINDING_CHANGED",
                    "evidence credential binding changed after plan",
                )
            definition = (
                self._definition(
                    lane, str(credential["id"]), typed_spec
                )
                if typed_spec is not None
                else None
            )
            if definition is not None:
                observed_definition_confirmation = _canonical_sha256(
                    _definition_confirmation_projection(definition)
                )
                planned_definition_confirmation = str(
                    (plan.get("desiredState") or {}).get(
                        "definitionSha256"
                    )
                    or ""
                )
                if (
                    observed_definition_confirmation
                    != planned_definition_confirmation
                ):
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_PLAN_STALE",
                        "generated definition no longer matches the confirmed credential template",
                    )

            pre_effect = None
            if operation != "create_draft":
                _raw, pre_effect = self._workflow(
                    lane,
                    api_key,
                    project,
                    workflow_id,
                    str(credential["id"] or ""),
                )
                self._assert_confirmed_current_state(
                    dict(plan.get("currentState") or {}),
                    pre_effect,
                )

            if operation == "create_draft":
                assert definition is not None
                confirmed_create_state = dict(
                    plan.get("currentState") or {}
                )
                pre_create_workflows = self._inventory(
                    lane,
                    api_key,
                    project,
                    str(credential["id"] or ""),
                )
                observed_create_state = {
                    "projectId": project["id"],
                    "projectName": project["name"],
                    "workflowCount": len(pre_create_workflows),
                    "inventorySha256": _canonical_sha256(
                        pre_create_workflows
                    ),
                }
                if (
                    any(
                        confirmed_create_state.get(field)
                        != observed_create_state.get(field)
                        for field in (
                            "projectId",
                            "projectName",
                            "workflowCount",
                            "inventorySha256",
                        )
                    )
                    or _canonical_sha256(confirmed_create_state)
                    != _canonical_sha256(observed_create_state)
                ):
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_PLAN_STALE",
                        "exact lane inventory changed after confirmation and before workflow creation",
                    )
                workflow_write_attempted = True
                created = self._request(
                    api_key,
                    "POST",
                    "/workflows",
                    json_body={
                        **definition,
                        "projectId": project["id"],
                    },
                )
                workflow_mutated = True
                workflow_id = (
                    str(created.get("id") or "")
                    if isinstance(created, dict)
                    else ""
                )
                if not _WORKFLOW_ID_RE.fullmatch(workflow_id):
                    raise WorkflowAutomationError(
                        "N8N_CREATE_READBACK_INVALID",
                        "created workflow did not return a valid identifier",
                    )
            elif operation == "update_draft":
                assert definition is not None
                if bool((plan.get("currentState") or {}).get("active")):
                    raise WorkflowAutomationError(
                        "N8N_ACTIVE_WORKFLOW_UPDATE_BLOCKED",
                        "active workflows must be paused before update_draft",
                    )
                workflow_write_attempted = True
                self._request(
                    api_key,
                    "PUT",
                    f"/workflows/{workflow_id}",
                    params={"publishIfActive": "false"},
                    json_body=definition,
                )
                workflow_mutated = True
            elif operation == "activate":
                if bool(plan.get("alreadyDesiredState")):
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_ALREADY_ACTIVE",
                        "workflow is already active; no write was performed",
                    )
                if pre_effect is None or not pre_effect.get("versionId"):
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_PLAN_STALE",
                        "confirmed workflow version is unavailable for version-bound publish",
                    )
                workflow_write_attempted = True
                self._request(
                    api_key,
                    "POST",
                    f"/workflows/{workflow_id}/publish",
                    json_body={"versionId": pre_effect["versionId"]},
                )
                workflow_mutated = True
            elif operation == "pause":
                if bool(plan.get("alreadyDesiredState")):
                    raise WorkflowAutomationError(
                        "N8N_WORKFLOW_ALREADY_PAUSED",
                        "workflow is already paused; no write was performed",
                    )
                workflow_write_attempted = True
                self._request(
                    api_key,
                    "POST",
                    f"/workflows/{workflow_id}/unpublish",
                )
                workflow_mutated = True
            else:
                raise WorkflowAutomationError(
                    "N8N_OPERATION_NOT_ALLOWLISTED",
                    "operation is not allowlisted for apply",
                )

            workflow_id, readback, verification = (
                self._workflow_write_readback(
                    lane=lane,
                    api_key=api_key,
                    project=project,
                    credential_id=str(credential["id"] or ""),
                    operation=operation,
                    workflow_id=workflow_id,
                    definition=definition,
                    pre_effect=pre_effect,
                )
            )
            verified = bool(verification["verified"])
            definition_verified = bool(
                verification["definitionVerified"]
            )
            active_verified = bool(
                verification["activeStateVerified"]
            )
            project_verified = bool(verification["projectBound"])
            archived_verified = bool(
                verification["archivedStateVerified"]
            )
            desired_definition_sha = verification[
                "desiredDefinitionSha256"
            ]
            return {
                "schemaVersion": "sovereign.n8n-workflow-apply.v1",
                "ok": verified,
                "status": (
                    "N8N_WORKFLOW_APPLIED_VERIFIED"
                    if verified
                    else "N8N_WORKFLOW_APPLIED_UNVERIFIED"
                ),
                "failureFamily": (
                    None if verified else "N8N_READBACK_MISMATCH"
                ),
                "blocker": (
                    None
                    if verified
                    else "n8n readback did not match the confirmed desired state"
                ),
                "lane": lane.lane_id,
                "repository": lane.repository,
                "projectId": project["id"],
                "projectName": project["name"],
                "operation": operation,
                "workflowId": workflow_id,
                "operationId": workflow_id,
                "requestedEffect": operation,
                "observedEffect": (
                    operation if verified else "unverified"
                ),
                "ownerApproved": True,
                "expectedRevision": expected_revision,
                "actualRevision": (
                    readback.get("versionId") or None
                ),
                "readback": readback,
                "readbackVerified": verified,
                "mutationPerformed": True,
                "mutationAttempted": True,
                "mutationPossible": False,
                "workflowWriteAttempted": workflow_write_attempted,
                "credentialWriteAttempted": credential_write_attempted,
                "credentialBootstrapped": credential_mutated,
                "nextAction": (
                    None
                    if verified
                    else "inspect_n8n_workflow_readback"
                ),
                "evidence": {
                    "confirmationSha256": expected,
                    "projectBound": project_verified,
                    "definitionVerified": definition_verified,
                    "activeStateVerified": active_verified,
                    "archivedStateVerified": archived_verified,
                    "desiredDefinitionSha256": desired_definition_sha,
                },
                "data": {},
                "secretValuesReturned": False,
            }
        except WorkflowAutomationError as exc:
            ambiguous_error = self._write_error_has_ambiguous_outcome(exc)
            workflow_outcome_ambiguous = bool(
                workflow_write_attempted
                and (workflow_mutated or ambiguous_error)
            )
            credential_outcome_ambiguous = bool(
                credential_write_attempted
                and not credential_mutated
                and ambiguous_error
            )
            if (
                workflow_outcome_ambiguous
                and lane is not None
                and project is not None
                and credential is not None
                and credential.get("present")
            ):
                try:
                    workflow_id, readback, verification = (
                        self._workflow_write_readback(
                            lane=lane,
                            api_key=api_key,
                            project=project,
                            credential_id=str(credential["id"] or ""),
                            operation=operation,
                            workflow_id=workflow_id,
                            definition=definition,
                            pre_effect=pre_effect,
                        )
                    )
                except WorkflowAutomationError:
                    pass
                else:
                    if verification["verified"]:
                        return {
                            "schemaVersion": "sovereign.n8n-workflow-apply.v1",
                            "ok": True,
                            "status": "N8N_WORKFLOW_APPLIED_VERIFIED_AFTER_AMBIGUOUS_RESPONSE",
                            "failureFamily": None,
                            "blocker": None,
                            "lane": lane.lane_id,
                            "repository": lane.repository,
                            "projectId": project["id"],
                            "projectName": project["name"],
                            "operation": operation,
                            "workflowId": workflow_id,
                            "operationId": workflow_id,
                            "requestedEffect": operation,
                            "observedEffect": "verified-after-ambiguous-response",
                            "ownerApproved": True,
                            "expectedRevision": expected_revision,
                            "actualRevision": readback.get("versionId") or None,
                            "readback": readback,
                            "readbackVerified": True,
                            "mutationPerformed": True,
                            "mutationAttempted": True,
                            "mutationPossible": False,
                            "workflowWriteAttempted": True,
                            "credentialWriteAttempted": credential_write_attempted,
                            "credentialBootstrapped": credential_mutated,
                            "reconciledAfterAmbiguousResponse": True,
                            "nextAction": None,
                            "evidence": {
                                "confirmationSha256": expected,
                                "originalFailureFamily": exc.failure_family,
                                "projectBound": verification["projectBound"],
                                "definitionVerified": verification[
                                    "definitionVerified"
                                ],
                                "activeStateVerified": verification[
                                    "activeStateVerified"
                                ],
                                "archivedStateVerified": verification[
                                    "archivedStateVerified"
                                ],
                                "desiredDefinitionSha256": verification[
                                    "desiredDefinitionSha256"
                                ],
                            },
                            "data": {},
                            "secretValuesReturned": False,
                        }

            mutated = workflow_mutated or credential_mutated
            uncertain = bool(
                workflow_outcome_ambiguous
                or credential_outcome_ambiguous
            )
            write_attempted = bool(
                workflow_write_attempted or credential_write_attempted
            )
            if uncertain:
                status = "N8N_WORKFLOW_APPLY_OUTCOME_UNCERTAIN"
                failure_family = "OUTCOME_UNCERTAIN"
                blocker = (
                    "a bounded write was attempted but its final outcome "
                    "could not be verified by exact project readback"
                )
                observed_effect = "outcome-uncertain"
            else:
                status = (
                    "N8N_WORKFLOW_APPLY_FAILED"
                    if mutated
                    else "N8N_WORKFLOW_APPLY_BLOCKED"
                )
                failure_family = exc.failure_family
                blocker = exc.blocker
                if write_attempted:
                    observed_effect = "rejected"
                elif credential_mutated:
                    observed_effect = "credential-bootstrap-only"
                else:
                    observed_effect = "none"
            return {
                **_failure(
                    status,
                    failure_family,
                    blocker,
                    lane=str(lane_id or ""),
                    operation=operation,
                    workflowId=workflow_id or None,
                ),
                "operationId": workflow_id or None,
                "requestedEffect": operation,
                "observedEffect": observed_effect,
                "ownerApproved": True,
                "expectedRevision": expected_revision,
                "actualRevision": None,
                "readbackVerified": False,
                "mutationPerformed": mutated,
                "mutationAttempted": write_attempted,
                "mutationPossible": uncertain,
                "workflowWriteAttempted": workflow_write_attempted,
                "credentialWriteAttempted": credential_write_attempted,
                "credentialBootstrapped": credential_mutated,
                "evidence": {
                    "originalFailureFamily": exc.failure_family,
                    "confirmationSha256": expected,
                },
            }
