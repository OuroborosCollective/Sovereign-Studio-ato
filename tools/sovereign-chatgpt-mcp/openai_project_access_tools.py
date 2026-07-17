from __future__ import annotations

import re
from typing import Any, Final

from mcp.types import ToolAnnotations


NETWORK_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_ALLOWED_OPERATIONS: Final[frozenset[str]] = frozenset({"setup", "verify", "rotate", "incident"})
_ALLOWED_ENVIRONMENTS: Final[frozenset[str]] = frozenset({"development", "test", "staging", "production"})
_ALLOWED_TARGETS: Final[frozenset[str]] = frozenset({"backend", "litellm", "agents-sdk", "mcp", "chatgpt-app"})
_ALLOWED_PERMISSION_INTENTS: Final[frozenset[str]] = frozenset({"inference-only", "agents-runtime", "litellm-provider", "administration"})
_SERVICE_ACCOUNT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
_SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:/@+%-]{0,199}$")
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_SECRET_MARKER = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|Authorization\s*:\s*(?:Bearer\s+)?\S+)",
    re.IGNORECASE,
)
_VAGUE_NAMES: Final[frozenset[str]] = frozenset({"test", "default", "default-key", "admin", "admin-key", "key-1", "service", "service-account"})

_BROKER: Any = None
_CONTROLLER: Any = None
_REGISTERED = False


def _clean(value: Any, limit: int = 200) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _safe_reference(value: Any, *, field: str, required: bool = False) -> str:
    selected = _clean(value)
    if required and not selected:
        raise ValueError(f"{field} is required")
    if selected and (not _SAFE_REFERENCE.fullmatch(selected) or _SECRET_MARKER.search(selected)):
        raise ValueError(f"{field} is not a safe non-secret reference")
    return selected


def _safe_models(values: list[str] | None) -> list[str]:
    models = sorted({_clean(value, 160) for value in (values or []) if _clean(value, 160)})
    if any(not _SAFE_MODEL.fullmatch(model) or _SECRET_MARKER.search(model) for model in models):
        raise ValueError("required_models contains an unsafe value")
    return models[:40]


def _safe_budget_alerts(values: list[int] | None) -> list[int]:
    alerts = sorted({int(value) for value in (values or [])})
    if any(value <= 0 or value > 10_000_000 for value in alerts):
        raise ValueError("budget_alerts must contain positive bounded amounts")
    return alerts[:20]


def openai_project_access_plan(
    operation: str,
    project_name: str,
    human_owner_reference: str,
    service_account_name: str,
    environment: str,
    target: str,
    permission_intent: str,
    secret_store_reference: str,
    organization_id: str = "",
    project_id: str = "",
    required_models: list[str] | None = None,
    budget_alerts: list[int] | None = None,
    rotation_days: int = 90,
) -> dict[str, Any]:
    """Validate a non-secret OpenAI project access, rotation or incident plan without external mutation."""
    selected_operation = _clean(operation, 40).casefold()
    selected_environment = _clean(environment, 40).casefold()
    selected_target = _clean(target, 40).casefold()
    selected_permission = _clean(permission_intent, 40).casefold()
    if selected_operation not in _ALLOWED_OPERATIONS:
        raise ValueError("operation must be setup, verify, rotate or incident")
    if selected_environment not in _ALLOWED_ENVIRONMENTS:
        raise ValueError("environment is not supported")
    if selected_target not in _ALLOWED_TARGETS:
        raise ValueError("target is not supported")
    if selected_permission not in _ALLOWED_PERMISSION_INTENTS:
        raise ValueError("permission_intent is not supported")

    normalized_project = _safe_reference(project_name, field="project_name", required=True)
    owner = _safe_reference(human_owner_reference, field="human_owner_reference", required=True)
    secret_target = _safe_reference(secret_store_reference, field="secret_store_reference", required=True)
    organization = _safe_reference(organization_id, field="organization_id")
    project = _safe_reference(project_id, field="project_id")
    account_name = _clean(service_account_name, 80).casefold()
    if not _SERVICE_ACCOUNT_NAME.fullmatch(account_name):
        raise ValueError("service_account_name must contain only lowercase letters, numbers and hyphens")
    if account_name in _VAGUE_NAMES or not account_name.endswith("-" + selected_environment):
        raise ValueError("service_account_name must be purpose-specific and end with the environment")
    rotation = max(1, min(int(rotation_days), 3650))
    models = _safe_models(required_models)
    alerts = _safe_budget_alerts(budget_alerts)

    blockers: list[str] = []
    if not organization:
        blockers.append("organization_id_not_yet_evidenced")
    if not project:
        blockers.append("project_id_not_yet_evidenced")
    if selected_permission == "administration" and selected_operation not in {"verify", "incident"}:
        blockers.append("administration_requires_explicit_owner_authorization")
    if selected_target in {"litellm", "agents-sdk"} and not models:
        blockers.append("required_models_not_declared")
    if not alerts:
        blockers.append("budget_alert_thresholds_not_declared")

    gates = [
        "verify human organization and project role independently",
        "verify project and service-account binding through an authoritative OpenAI surface",
        "store any new credential only through the protected Owner path",
        "verify actual API-key permissions after creation or rotation",
        "run authenticated provider identity and model inventory checks",
        "run private LiteLLM readiness, model and completion canaries when LiteLLM is the target",
        "run a persisted real Agents SDK canary when Agents SDK is the target",
        "scan repository, logs and client bundles for secret-shaped exposure without echoing values",
        "persist safe identifiers, timestamps, revision/digest and request/run evidence",
    ]
    if selected_operation == "rotate":
        gates.extend((
            "activate the new credential before revoking the old credential",
            "run one canary before revocation and a second canary after revocation",
            "never revoke the working credential after a failed canary",
        ))
    if selected_operation == "incident":
        gates.extend((
            "treat any credential exposed in chat, logs or source control as compromised",
            "identify and revoke or rotate by safe key identifier only",
            "inspect authorized usage and repository history without returning the secret value",
        ))

    return {
        "ok": not blockers,
        "status": "OPENAI_ACCESS_PLAN_READY" if not blockers else "OPENAI_ACCESS_PLAN_BLOCKED",
        "record": {
            "operation": selected_operation,
            "organizationId": organization or None,
            "projectId": project or None,
            "projectName": normalized_project,
            "humanOwnerReference": owner,
            "serviceAccountName": account_name,
            "environment": selected_environment,
            "target": selected_target,
            "permissionIntent": selected_permission,
            "secretStoreReference": secret_target,
            "requiredModels": models,
            "budgetAlerts": alerts,
            "rotationDays": rotation,
        },
        "blockers": blockers,
        "requiredGates": gates,
        "ownerMutationRequired": selected_operation in {"setup", "rotate", "incident"},
        "externalMutationPerformed": False,
        "providerPermissionVerified": False,
        "secretValuesAccepted": False,
        "secretValuesExposed": False,
        "truthNotice": "Intent labels are planning metadata. Actual OpenAI roles, scopes, models and limits require current authoritative evidence.",
    }


def openai_project_access_runtime_evidence() -> dict[str, Any]:
    """Aggregate safe OpenAI provider, private LiteLLM and persisted Agents SDK access evidence."""
    if _BROKER is None or _CONTROLLER is None:
        raise RuntimeError("OpenAI project access tools are not registered")
    provider_runtime = _BROKER.call("openai_project_runtime_evidence", {}, timeout=180)
    try:
        listed = _CONTROLLER.list_runs(limit=5)
    except Exception as exc:
        listed = {"ok": False, "status": "CONTROLLER_EVIDENCE_UNAVAILABLE", "error": type(exc).__name__, "runs": []}
    raw_runs = listed.get("runs") if isinstance(listed, dict) and isinstance(listed.get("runs"), list) else []
    latest = raw_runs[0] if raw_runs and isinstance(raw_runs[0], dict) else {}
    latest_run = {
        "runId": _clean(latest.get("run_id"), 80),
        "status": _clean(latest.get("status"), 80),
        "source": _clean(latest.get("source"), 80),
        "nextAction": _clean(latest.get("next_action"), 160),
        "leaseActive": bool(latest.get("lease_active")),
        "updatedAt": _clean(latest.get("updated_at"), 80),
    }
    agents_evidence_present = bool(latest_run["runId"] and latest_run["status"])
    runtime_ok = bool(isinstance(provider_runtime, dict) and provider_runtime.get("ok"))
    return {
        "ok": runtime_ok,
        "status": "OPENAI_PROJECT_ACCESS_EVIDENCE_READY" if runtime_ok else "OPENAI_PROJECT_ACCESS_EVIDENCE_BLOCKED",
        "providerAndLiteLLM": provider_runtime,
        "agentsSdk": {
            "evidencePresent": agents_evidence_present,
            "latestRun": latest_run if agents_evidence_present else None,
            "realCanaryMustBeCompleted": not agents_evidence_present,
        },
        "organizationProjectAttributionVerified": bool(
            isinstance(provider_runtime, dict) and provider_runtime.get("projectAttributionVerified")
        ),
        "externalMutationPerformed": False,
        "providerKeyValueReturned": False,
        "secretValuesExposed": False,
    }


def register(mcp: Any, broker: Any, controller_runtime: Any) -> None:
    global _BROKER, _CONTROLLER, _REGISTERED
    _BROKER = broker
    _CONTROLLER = controller_runtime
    if _REGISTERED:
        return
    mcp.tool(annotations=READ_ONLY)(openai_project_access_plan)
    mcp.tool(annotations=NETWORK_READ)(openai_project_access_runtime_evidence)
    _REGISTERED = True
