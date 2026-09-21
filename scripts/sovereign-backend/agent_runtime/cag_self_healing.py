"""Deterministic CAG self-healing contracts for Sovereign repository execution.

Runtime observations remain the source of truth. Wolfram CAG is a supplemental
formal-computation oracle that must agree with the locally derived invariant
mask before any repair contract can advance. It never receives prompts,
credentials, repository content or mutation authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Any, Final, Iterable, Mapping, Sequence


SCHEMA_VERSION: Final[str] = "sovereign.cag-self-healing.v1"
OBSERVATION_SCHEMA_VERSION: Final[str] = "sovereign.cag-self-healing-observation.v1"
REPAIR_SCHEMA_VERSION: Final[str] = "sovereign.cag-self-healing-repair.v1"
AUTHORITY_SCHEMA_VERSION: Final[str] = "sovereign.cag-self-healing-authority.v1"

EXPECTED_EXTERNAL_EXECUTOR: Final[str] = "agent-zero-a2a"
EXPECTED_A2A_PATH: Final[str] = "/a2a/"
CURRENT_REPOSITORY_EXECUTION_BILLING_MODE: Final[str] = "free"
MAX_EVENT_STAGES: Final[int] = 80


class FailureFamily(str, Enum):
    EXECUTOR_MISMATCH = "EXECUTOR_MISMATCH"
    ENDPOINT_ROUTE_MISMATCH = "ENDPOINT_ROUTE_MISMATCH"
    HANDOFF_TIMEOUT_WITH_READBACK = "HANDOFF_TIMEOUT_WITH_READBACK"
    JOB_STATE_TRANSITION_VIOLATION = "JOB_STATE_TRANSITION_VIOLATION"
    BILLING_ROUTE_MISMATCH = "BILLING_ROUTE_MISMATCH"


FAILURE_ORDER: Final[tuple[FailureFamily, ...]] = (
    FailureFamily.EXECUTOR_MISMATCH,
    FailureFamily.ENDPOINT_ROUTE_MISMATCH,
    FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK,
    FailureFamily.JOB_STATE_TRANSITION_VIOLATION,
    FailureFamily.BILLING_ROUTE_MISMATCH,
)

FAILURE_BITS: Final[dict[FailureFamily, int]] = {
    family: 1 << index for index, family in enumerate(FAILURE_ORDER)
}

REPAIR_STRATEGIES: Final[dict[FailureFamily, str]] = {
    FailureFamily.EXECUTOR_MISMATCH: "REPAIR_CONTROL_PLANE_EXECUTOR_ROUTE",
    FailureFamily.ENDPOINT_ROUTE_MISMATCH: "REPAIR_CONTROL_PLANE_A2A_ENDPOINT",
    FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK: "RETRY_READBACK_NO_RESUBMIT",
    FailureFamily.JOB_STATE_TRANSITION_VIOLATION: "REPAIR_CONTROL_PLANE_STATE_MACHINE",
    FailureFamily.BILLING_ROUTE_MISMATCH: "REPAIR_CONTROL_PLANE_BILLING_GUARD",
}

CODE_REPAIR_FAMILIES: Final[frozenset[FailureFamily]] = frozenset({
    FailureFamily.EXECUTOR_MISMATCH,
    FailureFamily.ENDPOINT_ROUTE_MISMATCH,
    FailureFamily.JOB_STATE_TRANSITION_VIOLATION,
    FailureFamily.BILLING_ROUTE_MISMATCH,
})

SAFE_READBACK_FAMILIES: Final[frozenset[FailureFamily]] = frozenset({
    FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK,
})

_ALLOWED_AUTHORITY_MODES: Final[frozenset[str]] = frozenset({
    "OBSERVE_ONLY",
    "ASK_FIRST",
    "AUTO_SAFE",
    "AUTO_BOUNDED_CODE_REPAIR",
})

_AGENT_ZERO_REF_PREFIX: Final[str] = "agent-zero-a2a:"
_PENDING_PREFIX: Final[str] = "agent-zero-a2a:pending:submit:"
_CLAIM_PREFIX: Final[str] = "agent-zero-a2a:claim:"
_RETRY_PREFIX: Final[str] = "agent-zero-a2a:retry:"

_SIGNIFICANT_STAGE_ORDER: Final[tuple[str, ...]] = (
    "agent_job_created",
    "agent_zero_repository_access_delegated",
    "repository_execution_contract_bound",
    "agent_zero_a2a_submit_queued",
    "agent_zero_a2a_submitted",
    "repository_ready_for_draft_pr",
)

_SECRETISH = re.compile(
    r"(?:authorization\s*:|bearer\s+|api[_-]?key|password|secret|token|gh[pousr]_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SelfHealingContractError(ValueError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _bounded_text(value: Any, limit: int = 240) -> str:
    text = " ".join(str(value or "").replace("\x00", "").split())[:limit]
    if _SECRETISH.search(text):
        raise SelfHealingContractError("secret-shaped material is forbidden")
    return text


def classify_external_ref(external_ref: Any) -> str:
    value = str(external_ref or "").strip()
    if not value:
        return "missing"
    if value.startswith(_PENDING_PREFIX):
        return "agent-zero-a2a-pending"
    if value.startswith(_CLAIM_PREFIX):
        return "agent-zero-a2a-claim"
    if value.startswith(_RETRY_PREFIX):
        return "agent-zero-a2a-retry"
    if value.startswith(_AGENT_ZERO_REF_PREFIX):
        return EXPECTED_EXTERNAL_EXECUTOR
    return "unexpected-executor"


def normalize_event_stages(events: Sequence[Any] | None) -> tuple[str, ...]:
    stages: list[str] = []
    # Poll observations are not lifecycle transitions and must not hide closeout.
    for item in events or ():
        if isinstance(item, Mapping):
            stage = _bounded_text(item.get("stage"), 80)
        else:
            stage = _bounded_text(item, 80)
        if stage in {
            "agent_zero_a2a_task_observed",
            "agent_zero_a2a_readback_unavailable",
            "agent_zero_material_progress_observed",
        }:
            continue
        if stage:
            stages.append(stage)
            if len(stages) >= MAX_EVENT_STAGES:
                break
    return tuple(stages)


def transition_order_valid(event_stages: Sequence[str]) -> bool:
    positions: dict[str, int] = {}
    for index, stage in enumerate(event_stages):
        positions.setdefault(str(stage), index)
    ordered = [stage for stage in _SIGNIFICANT_STAGE_ORDER if stage in positions]
    if ordered != sorted(ordered, key=lambda stage: positions[stage]):
        return False

    if "repository_ready_for_draft_pr" in positions:
        completion_evidence = (
            "agent_zero_a2a_submitted" in positions
            or "agent_zero_a2a_retry_submitted" in positions
            or "agent_zero_a2a_lost_workspace_changes_detected" in positions
        )
        if not completion_evidence:
            return False
    if "agent_zero_a2a_submitted" in positions and "agent_zero_a2a_submit_queued" not in positions:
        return False
    if "agent_zero_a2a_submit_queued" in positions and "agent_zero_repository_access_delegated" not in positions:
        return False
    return True


@dataclass(frozen=True, slots=True)
class SelfHealingObservation:
    job_id: str
    job_status: str
    external_ref_class: str
    observed_endpoint_path: str
    expected_endpoint_path: str
    event_stages: tuple[str, ...]
    handoff_timed_out: bool
    task_readback_available: bool
    workspace_changes_present: bool
    billing_mode: str
    billing_settlement_count: int
    billing_provider_cost_micros: int
    billing_charged_cost_micros: int
    billing_credit_delta_micros: int
    billing_settled: bool
    source_revision: str

    def __post_init__(self) -> None:
        if not self.job_id or len(self.job_id) > 160:
            raise SelfHealingContractError("job_id is required and bounded")
        if self.billing_mode not in {"free", "paid"}:
            raise SelfHealingContractError("billing mode must be free or paid")
        if len(self.event_stages) > MAX_EVENT_STAGES:
            raise SelfHealingContractError("too many event stages")
        for value in (
            self.billing_settlement_count,
            self.billing_provider_cost_micros,
            self.billing_charged_cost_micros,
        ):
            if int(value) < 0:
                raise SelfHealingContractError("billing counters must be non-negative")
        if self.source_revision and not re.fullmatch(r"[0-9a-f]{40}", self.source_revision):
            raise SelfHealingContractError("source revision must be an exact Git SHA")

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schemaVersion": OBSERVATION_SCHEMA_VERSION,
            "jobId": self.job_id,
            "jobStatus": self.job_status,
            "externalRefClass": self.external_ref_class,
            "observedEndpointPath": self.observed_endpoint_path,
            "expectedEndpointPath": self.expected_endpoint_path,
            "eventStages": list(self.event_stages),
            "handoffTimedOut": self.handoff_timed_out,
            "taskReadbackAvailable": self.task_readback_available,
            "workspaceChangesPresent": self.workspace_changes_present,
            "billingMode": self.billing_mode,
            "billingSettlementCount": self.billing_settlement_count,
            "billingProviderCostMicros": self.billing_provider_cost_micros,
            "billingChargedCostMicros": self.billing_charged_cost_micros,
            "billingCreditDeltaMicros": self.billing_credit_delta_micros,
            "billingSettled": self.billing_settled,
            "sourceRevision": self.source_revision,
        }
        body["observationSha256"] = sha256_json(body)
        return body


def detect_failures(observation: SelfHealingObservation) -> tuple[FailureFamily, ...]:
    failures: list[FailureFamily] = []

    executor_is_agent_zero = observation.external_ref_class in {
        EXPECTED_EXTERNAL_EXECUTOR,
        "agent-zero-a2a-pending",
        "agent-zero-a2a-claim",
        "agent-zero-a2a-retry",
    }
    if not executor_is_agent_zero:
        failures.append(FailureFamily.EXECUTOR_MISMATCH)

    if observation.observed_endpoint_path != observation.expected_endpoint_path:
        failures.append(FailureFamily.ENDPOINT_ROUTE_MISMATCH)

    if observation.handoff_timed_out and observation.external_ref_class in {
        EXPECTED_EXTERNAL_EXECUTOR,
        "agent-zero-a2a-pending",
        "agent-zero-a2a-claim",
        "agent-zero-a2a-retry",
    }:
        failures.append(FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK)

    if not transition_order_valid(observation.event_stages):
        failures.append(FailureFamily.JOB_STATE_TRANSITION_VIOLATION)

    if observation.billing_mode == "free":
        if (
            observation.billing_settlement_count > 0
            or observation.billing_provider_cost_micros > 0
            or observation.billing_charged_cost_micros > 0
            or observation.billing_credit_delta_micros != 0
        ):
            failures.append(FailureFamily.BILLING_ROUTE_MISMATCH)
    else:
        if (
            observation.billing_settlement_count <= 0
            or not observation.billing_settled
            or observation.billing_credit_delta_micros != -observation.billing_charged_cost_micros
        ):
            failures.append(FailureFamily.BILLING_ROUTE_MISMATCH)

    return tuple(family for family in FAILURE_ORDER if family in failures)


def failure_mask(failures: Iterable[FailureFamily]) -> int:
    selected = set(failures)
    return sum(FAILURE_BITS[family] for family in FAILURE_ORDER if family in selected)


def _wl_string(value: Any) -> str:
    return json.dumps(str(value or ""), ensure_ascii=True)


def build_cag_verification_code(observation: SelfHealingObservation) -> str:
    """Build a bounded Wolfram Language invariant computation from structural facts.

    The provider receives only small booleans/integers and route-class strings;
    no mission text, repository content, credentials or raw provider payloads.
    """
    allowed_executor_classes = {
        EXPECTED_EXTERNAL_EXECUTOR,
        "agent-zero-a2a-pending",
        "agent-zero-a2a-claim",
        "agent-zero-a2a-retry",
    }
    executor_values = ",".join(_wl_string(value) for value in sorted(allowed_executor_classes))
    transition_valid = transition_order_valid(observation.event_stages)
    terms = [
        (
            f"If[MemberQ[{{{executor_values}}},{_wl_string(observation.external_ref_class)}],0,"
            f"{FAILURE_BITS[FailureFamily.EXECUTOR_MISMATCH]}]"
        ),
        (
            f"If[{_wl_string(observation.observed_endpoint_path)}=="
            f"{_wl_string(observation.expected_endpoint_path)},0,"
            f"{FAILURE_BITS[FailureFamily.ENDPOINT_ROUTE_MISMATCH]}]"
        ),
        (
            f"If[{'True' if observation.handoff_timed_out else 'False'}&&"
            f"MemberQ[{{{executor_values}}},{_wl_string(observation.external_ref_class)}],"
            f"{FAILURE_BITS[FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK]},0]"
        ),
        (
            f"If[{'True' if transition_valid else 'False'},0,"
            f"{FAILURE_BITS[FailureFamily.JOB_STATE_TRANSITION_VIOLATION]}]"
        ),
    ]
    if observation.billing_mode == "free":
        billing_predicate = (
            f"({int(observation.billing_settlement_count)}>0)||"
            f"({int(observation.billing_provider_cost_micros)}>0)||"
            f"({int(observation.billing_charged_cost_micros)}>0)||"
            f"({int(observation.billing_credit_delta_micros)}!=0)"
        )
    else:
        billing_predicate = (
            f"({int(observation.billing_settlement_count)}<=0)||"
            f"({'True' if not observation.billing_settled else 'False'})||"
            f"({int(observation.billing_credit_delta_micros)}!="
            f"{-int(observation.billing_charged_cost_micros)})"
        )
    terms.append(
        f"If[{billing_predicate},{FAILURE_BITS[FailureFamily.BILLING_ROUTE_MISMATCH]},0]"
    )
    return "Total[{" + ",".join(terms) + "}]"


def parse_cag_failure_mask(value: Any) -> int:
    text = str(value or "").strip()
    # Wolfram Language Computation returns a notebook-style output label such
    # as ``Out[1]=4`` even when the evaluated expression itself is an integer.
    # Accept exactly that bounded provider wrapper or an already-normalized
    # decimal integer; arbitrary messages or multi-line output still fail closed.
    match = re.fullmatch(r"(?:Out\[[0-9]{1,9}\]\s*=\s*)?([0-9]{1,10})", text)
    if match is None:
        raise SelfHealingContractError("CAG failure mask result is invalid")
    result = int(match.group(1))
    max_mask = sum(FAILURE_BITS.values())
    if result < 0 or result > max_mask:
        raise SelfHealingContractError("CAG failure mask is outside the allowed range")
    return result


def failures_from_mask(mask: int) -> tuple[FailureFamily, ...]:
    if mask < 0:
        raise SelfHealingContractError("failure mask cannot be negative")
    return tuple(family for family in FAILURE_ORDER if mask & FAILURE_BITS[family])


def cag_agrees_with_local_verdict(
    observation: SelfHealingObservation,
    normalized_cag_result: Any,
) -> bool:
    return parse_cag_failure_mask(normalized_cag_result) == failure_mask(detect_failures(observation))


def _repair_target_files(family: FailureFamily) -> tuple[str, ...]:
    mapping = {
        FailureFamily.EXECUTOR_MISMATCH: (
            "backend/agent_runtime/repository_execution.py",
            "backend/agent_runtime/routes.py",
            "backend/agent_runtime/cognitive_swarm_routes.py",
        ),
        FailureFamily.ENDPOINT_ROUTE_MISMATCH: (
            "backend/agent_runtime/agent_zero_a2a.py",
            "scripts/sovereign-backend/agent_runtime/agent_zero_a2a.py",
        ),
        FailureFamily.JOB_STATE_TRANSITION_VIOLATION: (
            "backend/agent_runtime/repository_execution.py",
            "backend/agent_runtime/job_store.py",
        ),
        FailureFamily.BILLING_ROUTE_MISMATCH: (
            "backend/agent_runtime/repository_execution.py",
            "backend/agent_runtime/cognitive_usage_billing.py",
        ),
        FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK: (),
    }
    return mapping[family]


def build_repair_contract(
    *,
    observation: SelfHealingObservation,
    failures: Sequence[FailureFamily],
    cag_request_sha256: str,
    cag_response_sha256: str,
    cag_result_sha256: str,
    controller_repository: str,
) -> dict[str, Any]:
    ordered = tuple(family for family in FAILURE_ORDER if family in set(failures))
    if len(ordered) != 1:
        raise SelfHealingContractError("v1 requires exactly one independently verified failure family")
    family = ordered[0]
    for name, value in (
        ("cag request", cag_request_sha256),
        ("cag response", cag_response_sha256),
        ("cag result", cag_result_sha256),
    ):
        if not _SHA256.fullmatch(str(value or "")):
            raise SelfHealingContractError(f"{name} SHA-256 is invalid")
    repo = _bounded_text(controller_repository, 200)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise SelfHealingContractError("controller repository identity is invalid")
    target_files = _repair_target_files(family)
    action_kind = "readback-only" if family in SAFE_READBACK_FAMILIES else "agent-zero-code-repair"
    body: dict[str, Any] = {
        "schemaVersion": REPAIR_SCHEMA_VERSION,
        "sourceJobId": observation.job_id,
        "sourceRevision": observation.source_revision,
        "sourceObservationSha256": observation.to_dict()["observationSha256"],
        "failureFamily": family.value,
        "repairStrategy": REPAIR_STRATEGIES[family],
        "actionKind": action_kind,
        "controllerRepository": repo,
        "requiredExecutor": EXPECTED_EXTERNAL_EXECUTOR,
        "targetFiles": list(target_files),
        "cagRequestSha256": cag_request_sha256,
        "cagResponseSha256": cag_response_sha256,
        "cagResultSha256": cag_result_sha256,
        "forbiddenEffects": [
            "direct-github-coding-executor",
            "github-oauth-execution-authority",
            "secret-read-or-disclosure",
            "automatic-merge",
            "automatic-production-deploy",
            "credit-ledger-manual-edit",
            "billing-guard-disable",
            "duplicate-agent-zero-submit",
        ],
        "requiredEvidence": [
            "exact-head-regression",
            "git-diff-check",
            "agent-zero-only-executor",
            "post-repair-runtime-readback",
            "action-receipt",
        ],
        "successPredicate": (
            "fresh structural observation produces no occurrence of the original failure family "
            "and Wolfram CAG recomputation agrees with the local invariant mask"
        ),
        "authorityRequirement": (
            "AUTO_SAFE"
            if family in SAFE_READBACK_FAMILIES
            else "AUTO_BOUNDED_CODE_REPAIR"
        ),
        "truthNotice": (
            "CAG verifies the formal failure mask only; runtime evidence remains authoritative "
            "and Agent Zero remains the sole repository implementation executor."
        ),
    }
    body["repairContractSha256"] = sha256_json(body)
    return body


def build_agent_zero_repair_mission(repair_contract: Mapping[str, Any]) -> str:
    family = FailureFamily(str(repair_contract.get("failureFamily") or ""))
    target_files = [str(path) for path in (repair_contract.get("targetFiles") or [])]
    contract_sha = str(repair_contract.get("repairContractSha256") or "")
    if not _SHA256.fullmatch(contract_sha):
        raise SelfHealingContractError("repair contract hash is invalid")
    if family in SAFE_READBACK_FAMILIES:
        raise SelfHealingContractError("readback-only repairs do not create Agent Zero code missions")

    focus = {
        FailureFamily.EXECUTOR_MISMATCH: (
            "Restore the canonical repository execution route so exactly one Agent Zero A2A task is the "
            "only external repository implementation worker. Do not introduce GitHub OAuth execution, "
            "Coding Agent, swarm repository execution or alternate checkout paths."
        ),
        FailureFamily.ENDPOINT_ROUTE_MISMATCH: (
            "Restore the Agent Zero A2A JSON-RPC endpoint contract to the mounted /a2a/ path, preserving "
            "header-only protected authentication and nonblocking message/send plus tasks/get readback."
        ),
        FailureFamily.JOB_STATE_TRANSITION_VIOLATION: (
            "Restore the persisted repository job transition ordering and CAS effect boundary. Preserve "
            "durable queueing, exactly-once submission ownership, read-only polling and fail-closed closeout."
        ),
        FailureFamily.BILLING_ROUTE_MISMATCH: (
            "Restore the billing guard so the current free repository execution path cannot create paid "
            "usage settlements or credit deltas. Do not edit balances directly or weaken settlement checks."
        ),
    }[family]

    return (
        f"[SOVEREIGN_SELF_HEALING_REPAIR {contract_sha}]\n"
        f"Failure family: {family.value}\n"
        f"Repair strategy: {REPAIR_STRATEGIES[family]}\n"
        f"Expected controller main revision: {str(repair_contract.get('sourceRevision') or '')}\n"
        f"Allowed focus files: {', '.join(target_files)}\n"
        f"{focus}\n"
        "Make the smallest code change that restores the stated invariant. "
        "Do not change unrelated behavior, do not push or create a PR, do not install dependencies, "
        "and stop after saving the bounded workspace changes. Sovereign owns tests, evidence, publication, "
        "merge and deployment."
    )


def authority_allows(
    *,
    mode: str,
    allowed_failure_families: Sequence[str],
    failure_family: FailureFamily,
    paused: bool,
    expired: bool,
) -> bool:
    normalized_mode = str(mode or "").strip().upper()
    if normalized_mode not in _ALLOWED_AUTHORITY_MODES or paused or expired:
        return False
    allowed = {str(item).strip().upper() for item in allowed_failure_families}
    if failure_family.value not in allowed:
        return False
    if failure_family in SAFE_READBACK_FAMILIES:
        return normalized_mode in {"AUTO_SAFE", "AUTO_BOUNDED_CODE_REPAIR"}
    if failure_family in CODE_REPAIR_FAMILIES:
        return normalized_mode == "AUTO_BOUNDED_CODE_REPAIR"
    return False


__all__ = [
    "AUTHORITY_SCHEMA_VERSION",
    "CODE_REPAIR_FAMILIES",
    "CURRENT_REPOSITORY_EXECUTION_BILLING_MODE",
    "EXPECTED_A2A_PATH",
    "EXPECTED_EXTERNAL_EXECUTOR",
    "FAILURE_BITS",
    "FAILURE_ORDER",
    "FailureFamily",
    "OBSERVATION_SCHEMA_VERSION",
    "REPAIR_SCHEMA_VERSION",
    "REPAIR_STRATEGIES",
    "SAFE_READBACK_FAMILIES",
    "SCHEMA_VERSION",
    "SelfHealingContractError",
    "SelfHealingObservation",
    "authority_allows",
    "build_agent_zero_repair_mission",
    "build_cag_verification_code",
    "build_repair_contract",
    "cag_agrees_with_local_verdict",
    "canonical_json",
    "classify_external_ref",
    "detect_failures",
    "failure_mask",
    "failures_from_mask",
    "normalize_event_stages",
    "parse_cag_failure_mask",
    "sha256_json",
    "sha256_text",
    "transition_order_valid",
]
