"""Runtime controller for bounded CAG-assisted self-healing.

The controller observes the persisted Agent-Zero-only repository workflow,
derives deterministic invariant violations, asks Wolfram CAG to recompute the
bounded failure mask, and only then evaluates a revocable standing authority.
CAG never mutates. Repository repairs are always new Agent Zero A2A jobs;
handoff recovery is readback-only and never resubmits an unknown effect.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit
import uuid

from .adapters.wolfram_agenttools import (
    WolframCagError,
    execute_live_cag_request,
)
from .agent_zero_a2a import AgentZeroA2AClient, AgentZeroA2AError, AgentZeroA2ATaskLost
from .cag_self_healing import (
    AUTHORITY_SCHEMA_VERSION,
    CURRENT_REPOSITORY_EXECUTION_BILLING_MODE,
    EXPECTED_A2A_PATH,
    FAILURE_ORDER,
    SCHEMA_VERSION,
    FailureFamily,
    SelfHealingContractError,
    SelfHealingObservation,
    authority_allows,
    build_agent_zero_repair_mission,
    build_cag_verification_code,
    build_repair_contract,
    cag_agrees_with_local_verdict,
    canonical_json,
    classify_external_ref,
    detect_failures,
    failure_mask,
    normalize_event_stages,
    sha256_json,
    sha256_text,
)
from .contracts import SovereignAgentEvent
from .job_store import (
    StoredSovereignAgentJob,
    append_agent_event,
    stored_job_from_row,
)
from .repository_execution import (
    recover_stalled_repository_job_from_verified_readback,
    start_repository_execution,
)


ConnectionFactory = Callable[[], Any]

_LOGGER = logging.getLogger(__name__)
_THREAD_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_CONTROLLER_REPOSITORY_DEFAULT = "OuroborosCollective/Sovereign-Studio-ato"
_INCIDENT_WINDOW_HOURS = 24
_MAX_CANDIDATES = 50
_MAX_INCIDENTS_API = 100
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _close(connection: Any) -> None:
    close = getattr(connection, "close", None)
    if callable(close):
        close()


def _source_revision() -> str:
    value = str(os.getenv("SOVEREIGN_SOURCE_REVISION") or "").strip().casefold()
    return value if _SHA40.fullmatch(value) else ""


def _controller_repository() -> str:
    value = str(
        os.getenv("SOVEREIGN_CONTROLLER_REPOSITORY")
        or _CONTROLLER_REPOSITORY_DEFAULT
    ).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise SelfHealingContractError("controller repository identity is invalid")
    return value


def _configured_owner_admin_id() -> str:
    value = str(os.getenv("SOVEREIGN_OWNER_ADMIN_ID") or "").strip().casefold()
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return ""
    return parsed if _UUID.fullmatch(parsed) else ""


def _poll_seconds() -> float:
    try:
        value = float(os.getenv("SOVEREIGN_SELF_HEALING_POLL_SECONDS", "15"))
    except (TypeError, ValueError):
        value = 15.0
    return max(5.0, min(value, 300.0))


def _stall_seconds() -> float:
    try:
        value = float(os.getenv("SOVEREIGN_REPOSITORY_STALL_SECONDS", "1800"))
    except (TypeError, ValueError):
        value = 1800.0
    return max(300.0, min(value, 86400.0))


def _age_seconds(job: StoredSovereignAgentJob) -> float | None:
    observed = job.updated_at or job.created_at
    if not isinstance(observed, datetime):
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds())


def _json_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _candidate_jobs(connection: Any, limit: int = _MAX_CANDIDATES) -> tuple[StoredSovereignAgentJob, ...]:
    safe_limit = max(1, min(int(limit), _MAX_CANDIDATES))
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM sovereign_agent_jobs
            WHERE updated_at >= NOW() - (%s * INTERVAL '1 hour')
              AND status IN ('running','blocked','validating','completed')
              AND (
                    external_ref LIKE 'agent-zero-a2a:%%'
                    OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(events, '[]'::jsonb)) AS event
                        WHERE event->>'stage' = 'repository_execution_contract_bound'
                    )
              )
            ORDER BY updated_at ASC, job_id ASC
            LIMIT %s
            """,
            (_INCIDENT_WINDOW_HOURS, safe_limit),
        )
        rows = cur.fetchall()
    result: list[StoredSovereignAgentJob] = []
    for row in rows:
        job = stored_job_from_row(row)
        stages = normalize_event_stages(job.events)
        if "self_healing_repair_job_started" in stages:
            continue
        if str(job.mission or "").startswith("[SOVEREIGN_SELF_HEALING_REPAIR "):
            continue
        result.append(job)
    return tuple(result)


def _billing_summary(connection: Any, job_id: str) -> dict[str, Any]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::integer AS settlement_count,
                   COALESCE(SUM(COALESCE(provider_cost_usd_micros, 0)), 0)::bigint AS provider_cost_micros,
                   COALESCE(SUM(COALESCE(billed_value_usd_micros, 0)), 0)::bigint AS charged_cost_micros,
                   COALESCE(BOOL_AND(status IN (
                       'settled_usage','settled_estimate','refunded','failed'
                   )), FALSE) AS terminal
            FROM llm_usage_settlements
            WHERE trace_id = %s
            """,
            (job_id,),
        )
        row = cur.fetchone() or {}
    count = int(row.get("settlement_count") or 0)
    provider_cost = int(row.get("provider_cost_micros") or 0)
    charged_cost = int(row.get("charged_cost_micros") or 0)
    return {
        "settlementCount": count,
        "providerCostMicros": provider_cost,
        "chargedCostMicros": charged_cost,
        # The current repository route is free-only. For a future paid route this
        # projection is the exact billed-value debit expressed in provider USD
        # micros; the credit ledger remains independently authoritative.
        "creditDeltaMicros": -charged_cost if count else 0,
        "settled": bool(row.get("terminal")) if count else False,
    }


def _agent_zero_endpoint_path() -> str:
    try:
        endpoint = AgentZeroA2AClient.from_env().endpoint
    except AgentZeroA2AError:
        return ""
    try:
        return str(urlsplit(endpoint).path or "")
    except ValueError:
        return ""


def _bound_task_id(external_ref: str) -> str:
    value = str(external_ref or "")
    if value.startswith("agent-zero-a2a:retry:"):
        return value[len("agent-zero-a2a:retry:"):]
    if (
        value.startswith("agent-zero-a2a:")
        and not value.startswith("agent-zero-a2a:pending:")
        and not value.startswith("agent-zero-a2a:claim:")
    ):
        return value[len("agent-zero-a2a:"):]
    return ""


def _readback_available_for_timeout(job: StoredSovereignAgentJob, timed_out: bool) -> bool:
    if not timed_out:
        return False
    task_id = _bound_task_id(str(job.external_ref or ""))
    if not task_id:
        return False
    try:
        AgentZeroA2AClient.from_env().get_task(task_id)
        return True
    except (AgentZeroA2AError, AgentZeroA2ATaskLost):
        return False


def _build_observation(connection: Any, job: StoredSovereignAgentJob) -> SelfHealingObservation:
    billing = _billing_summary(connection, job.job_id)
    stages = normalize_event_stages(job.events)
    age = _age_seconds(job)
    external_class = classify_external_ref(job.external_ref)
    timed_out = (
        "AGENT_ZERO_A2A_STALLED" in str(job.blocker or "")
        or (
            job.status == "running"
            and age is not None
            and age >= _stall_seconds()
            and external_class in {
                "agent-zero-a2a",
                "agent-zero-a2a-pending",
                "agent-zero-a2a-claim",
                "agent-zero-a2a-retry",
            }
        )
    )
    return SelfHealingObservation(
        job_id=job.job_id,
        job_status=job.status,
        external_ref_class=external_class,
        observed_endpoint_path=_agent_zero_endpoint_path(),
        expected_endpoint_path=EXPECTED_A2A_PATH,
        event_stages=stages,
        handoff_timed_out=timed_out,
        task_readback_available=_readback_available_for_timeout(job, timed_out),
        workspace_changes_present=bool(job.changed_files),
        billing_mode=CURRENT_REPOSITORY_EXECUTION_BILLING_MODE,
        billing_settlement_count=int(billing["settlementCount"]),
        billing_provider_cost_micros=int(billing["providerCostMicros"]),
        billing_charged_cost_micros=int(billing["chargedCostMicros"]),
        billing_credit_delta_micros=int(billing["creditDeltaMicros"]),
        billing_settled=bool(billing["settled"]),
        source_revision=_source_revision(),
    )


def _incident_identity(job_id: str, family: FailureFamily, observation_sha256: str) -> str:
    digest = sha256_json({
        "jobId": job_id,
        "failureFamily": family.value,
        "observationSha256": observation_sha256,
    })
    return f"self-heal-{digest[:24]}"


def _persist_action_receipt(
    connection: Any,
    *,
    incident_id: str,
    action_kind: str,
    effect_class: str,
    payload: Mapping[str, Any],
) -> str:
    body = {
        "schemaVersion": "sovereign.cag-self-healing-action-receipt.v1",
        "incidentId": incident_id,
        "actionKind": action_kind,
        "effectClass": effect_class,
        "payload": dict(payload),
    }
    receipt_sha = sha256_json(body)
    receipt_id = f"self-heal-receipt-{receipt_sha[:24]}"
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_self_healing_action_receipts
                (receipt_id, incident_id, action_kind, effect_class, receipt_sha256, payload)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (receipt_sha256) DO NOTHING
            """,
            (
                receipt_id,
                incident_id,
                action_kind,
                effect_class,
                receipt_sha,
                canonical_json(body),
            ),
        )
    connection.commit()
    return receipt_sha


def _upsert_detected_incident(
    connection: Any,
    *,
    job: StoredSovereignAgentJob,
    observation: SelfHealingObservation,
    family: FailureFamily,
) -> dict[str, Any]:
    projection = observation.to_dict()
    observation_sha = str(projection["observationSha256"])
    incident_id = _incident_identity(job.job_id, family, observation_sha)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_self_healing_incidents (
                incident_id, schema_version, source_job_id, source_user_id,
                failure_family, observation_sha256, observation, status
            ) VALUES (%s,%s,%s,%s::uuid,%s,%s,%s::jsonb,'DETECTED')
            ON CONFLICT (source_job_id, failure_family, observation_sha256) DO NOTHING
            """,
            (
                incident_id,
                SCHEMA_VERSION,
                job.job_id,
                job.user_id,
                family.value,
                observation_sha,
                canonical_json(projection),
            ),
        )
        inserted = cur.rowcount == 1
        cur.execute(
            """
            SELECT incident_id, failure_family, status, repair_job_id,
                   observation_sha256, repair_contract_sha256, blocker,
                   cag_request_sha256, cag_response_sha256, cag_result_sha256,
                   cag_verified
            FROM sovereign_self_healing_incidents
            WHERE source_job_id=%s AND failure_family=%s AND observation_sha256=%s
            LIMIT 1
            """,
            (job.job_id, family.value, observation_sha),
        )
        row = cur.fetchone()
    connection.commit()
    if not row:
        raise RuntimeError("self-healing incident readback missing")
    if inserted:
        _persist_action_receipt(
            connection,
            incident_id=incident_id,
            action_kind="DETECTED",
            effect_class="read",
            payload={
                "failureFamily": family.value,
                "observationSha256": observation_sha,
                "sourceRevision": observation.source_revision,
            },
        )
    return dict(row)


def _update_incident(
    connection: Any,
    *,
    incident_id: str,
    status: str,
    blocker: str | None = None,
    cag_request_sha256: str | None = None,
    cag_response_sha256: str | None = None,
    cag_result_sha256: str | None = None,
    cag_verified: bool | None = None,
    repair_contract: Mapping[str, Any] | None = None,
    authority_owner_admin_id: str | None = None,
    repair_job_id: str | None = None,
    resolved: bool = False,
) -> None:
    contract_sha = (
        str(repair_contract.get("repairContractSha256") or "")
        if isinstance(repair_contract, Mapping)
        else None
    )
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_self_healing_incidents
            SET status=%s,
                blocker=%s,
                cag_request_sha256=COALESCE(%s, cag_request_sha256),
                cag_response_sha256=COALESCE(%s, cag_response_sha256),
                cag_result_sha256=COALESCE(%s, cag_result_sha256),
                cag_verified=COALESCE(%s, cag_verified),
                repair_contract_sha256=COALESCE(%s, repair_contract_sha256),
                repair_contract=COALESCE(%s::jsonb, repair_contract),
                authority_owner_admin_id=COALESCE(%s::uuid, authority_owner_admin_id),
                repair_job_id=COALESCE(%s, repair_job_id),
                resolved_at=CASE WHEN %s THEN NOW() ELSE resolved_at END,
                updated_at=NOW()
            WHERE incident_id=%s
            """,
            (
                status,
                blocker,
                cag_request_sha256,
                cag_response_sha256,
                cag_result_sha256,
                cag_verified,
                contract_sha,
                canonical_json(dict(repair_contract)) if repair_contract is not None else None,
                authority_owner_admin_id,
                repair_job_id,
                resolved,
                incident_id,
            ),
        )
    connection.commit()


def _persisted_cag_evidence(incidents: Sequence[Mapping[str, Any]]) -> dict[str, str] | None:
    """Reuse one already verified observation-level CAG result after a worker restart.

    All failure-family incidents for one observation share the same formal mask.
    A single persisted verified result is therefore sufficient to repair a
    partial multi-row update without consuming another provider call. Divergent
    persisted hashes fail closed.
    """
    verified: set[tuple[str, str, str]] = set()
    for incident in incidents:
        if incident.get("cag_verified") is not True:
            continue
        values = (
            str(incident.get("cag_request_sha256") or "").strip().casefold(),
            str(incident.get("cag_response_sha256") or "").strip().casefold(),
            str(incident.get("cag_result_sha256") or "").strip().casefold(),
        )
        if all(_SHA64.fullmatch(value) for value in values):
            verified.add(values)
    if not verified:
        return None
    if len(verified) != 1:
        raise SelfHealingContractError("persisted CAG evidence diverged across one observation")
    request_sha, response_sha, result_sha = next(iter(verified))
    return {
        "requestSha256": request_sha,
        "responseSha256": response_sha,
        "resultSha256": result_sha,
    }


def _claim_incident_for_cag(connection: Any, incident_id: str) -> bool:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_self_healing_incidents
            SET status='CAG_VERIFYING', updated_at=NOW()
            WHERE incident_id=%s
              AND status='DETECTED'
              AND cag_verified=FALSE
            RETURNING incident_id
            """,
            (incident_id,),
        )
        won = cur.fetchone() is not None
    connection.commit()
    return won


def _claim_incident_for_action(connection: Any, incident_id: str) -> bool:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_self_healing_incidents
            SET status='REPAIR_CLAIMED', updated_at=NOW()
            WHERE incident_id=%s
              AND status IN ('CAG_VERIFIED','WAITING_FOR_AUTHORITY')
              AND repair_job_id IS NULL
            RETURNING incident_id
            """,
            (incident_id,),
        )
        won = cur.fetchone() is not None
    connection.commit()
    return won


def _authority_row(connection: Any, owner_admin_id: str) -> dict[str, Any] | None:
    if not owner_admin_id:
        return None
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT owner_admin_id::text, schema_version, mode, allowed_failure_families,
                   max_auto_repairs_per_hour, max_changed_files, expires_at, paused,
                   grant_sha256, created_at, updated_at, last_used_at,
                   (expires_at <= NOW()) AS expired
            FROM sovereign_self_healing_authority
            WHERE owner_admin_id=%s::uuid
            LIMIT 1
            """,
            (owner_admin_id,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _allowed_families(value: Any) -> list[str]:
    values = _json_array(value)
    allowed = {family.value for family in FAILURE_ORDER}
    return [str(item) for item in values if str(item) in allowed]


def _recent_action_count(connection: Any, owner_admin_id: str) -> int:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::integer AS action_count
            FROM sovereign_self_healing_action_receipts receipt
            JOIN sovereign_self_healing_incidents incident
              ON incident.incident_id=receipt.incident_id
            WHERE incident.authority_owner_admin_id=%s::uuid
              AND receipt.created_at >= NOW() - INTERVAL '1 hour'
              AND receipt.action_kind IN ('READBACK_RECOVERED','REPAIR_JOB_STARTED')
            """,
            (owner_admin_id,),
        )
        row = cur.fetchone() or {}
    return int(row.get("action_count") or 0)


def _touch_authority(connection: Any, owner_admin_id: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_self_healing_authority
            SET last_used_at=NOW(), updated_at=NOW()
            WHERE owner_admin_id=%s::uuid
            """,
            (owner_admin_id,),
        )
    connection.commit()


def _cag_verify_observation(observation: SelfHealingObservation) -> dict[str, Any]:
    code = build_cag_verification_code(observation)
    receipt = execute_live_cag_request(
        capability_id="wolfram.cag.compute",
        payload={"code": code, "maxChars": 64, "timeConstraint": 10},
    )
    if not cag_agrees_with_local_verdict(observation, receipt.normalized_result):
        raise SelfHealingContractError("CAG invariant mask diverged from local deterministic verdict")
    return {
        "requestSha256": receipt.request_hash,
        "responseSha256": receipt.response_hash,
        "resultSha256": sha256_text(receipt.normalized_result),
        "normalizedResult": receipt.normalized_result,
        "responseStatus": receipt.response_status,
        "responseUuidSha256": (
            sha256_text(receipt.response_uuid) if receipt.response_uuid else None
        ),
        "truthNotice": (
            "The Wolfram result verifies only the bounded invariant computation; "
            "runtime state remains owned by Sovereign readbacks."
        ),
    }


def _authority_permits(
    authority: Mapping[str, Any] | None,
    family: FailureFamily,
    target_file_count: int,
) -> bool:
    if not authority:
        return False
    return (
        authority_allows(
            mode=str(authority.get("mode") or ""),
            allowed_failure_families=_allowed_families(authority.get("allowed_failure_families")),
            failure_family=family,
            paused=bool(authority.get("paused")),
            expired=bool(authority.get("expired")),
        )
        and int(authority.get("max_changed_files") or 0) >= target_file_count
    )


def _start_code_repair(
    connection: Any,
    *,
    incident_id: str,
    repair_contract: Mapping[str, Any],
    authority_owner_admin_id: str,
) -> str:
    mission = build_agent_zero_repair_mission(repair_contract)
    source_revision = str(repair_contract.get("sourceRevision") or "")
    if not _SHA40.fullmatch(source_revision):
        raise SelfHealingContractError("code repair requires exact controller source revision")
    repository = str(repair_contract.get("controllerRepository") or "")
    job = start_repository_execution(
        connection,
        user_id=authority_owner_admin_id,
        body={
            "mode": "free",
            "agentMode": "single",
            "intentMode": "repository_execution",
            "repositoryUrl": f"https://github.com/{repository}",
            "repositoryBranch": "main",
            "expectedHeadSha": source_revision,
            "mission": mission,
            "allowAutoMerge": False,
        },
    )
    if not job.job_id:
        raise RuntimeError("self-healing repair job was not persisted")
    append_agent_event(connection, job.job_id, SovereignAgentEvent(
        stage="self_healing_repair_job_started",
        level="success",
        message=(
            f"Bounded self-healing repair started for incident {incident_id}; "
            "Agent Zero is the only repository implementation worker and automatic merge is forbidden."
        ),
    ))
    return job.job_id


def process_cag_self_healing_once(
    *,
    get_connection: ConnectionFactory,
    workspace_root: Path | None = None,
    limit: int = _MAX_CANDIDATES,
) -> dict[str, Any]:
    owner_admin_id = _configured_owner_admin_id()
    listing = get_connection()
    try:
        candidates = _candidate_jobs(listing, limit=limit)
    finally:
        _close(listing)

    observed = 0
    cag_verified = 0
    authority_blocked = 0
    readback_recovered = 0
    repair_started = 0
    failures = 0

    for candidate in candidates:
        connection = get_connection()
        try:
            observation = _build_observation(connection, candidate)
            local_failures = detect_failures(observation)
            if not local_failures:
                continue
            observed += 1
            incidents = [
                _upsert_detected_incident(
                    connection,
                    job=candidate,
                    observation=observation,
                    family=family,
                )
                for family in local_failures
            ]
            terminal = {"READBACK_RECOVERED", "REPAIR_STARTED", "RESOLVED"}
            if any(str(item.get("status") or "") in terminal for item in incidents):
                continue

            try:
                cag = _persisted_cag_evidence(incidents)
            except SelfHealingContractError as exc:
                failures += 1
                for incident in incidents:
                    incident_id = str(incident["incident_id"])
                    _update_incident(
                        connection,
                        incident_id=incident_id,
                        status="FAILED",
                        blocker=f"CAG_EVIDENCE_DIVERGED:{type(exc).__name__}",
                    )
                continue

            if cag is None:
                if any(str(item.get("status") or "") == "CAG_VERIFYING" for item in incidents):
                    # Another Gunicorn worker owns the provider call for this
                    # observation. Never duplicate the Wolfram request.
                    continue
                claim_target = next(
                    (
                        str(item["incident_id"])
                        for item in incidents
                        if str(item.get("status") or "") == "DETECTED"
                        and item.get("cag_verified") is not True
                    ),
                    "",
                )
                if not claim_target or not _claim_incident_for_cag(connection, claim_target):
                    continue
                try:
                    cag = _cag_verify_observation(observation)
                except (WolframCagError, SelfHealingContractError) as exc:
                    failures += 1
                    for incident in incidents:
                        incident_id = str(incident["incident_id"])
                        _update_incident(
                            connection,
                            incident_id=incident_id,
                            status="FAILED",
                            blocker=f"CAG_VERIFICATION_FAILED:{type(exc).__name__}",
                        )
                        _persist_action_receipt(
                            connection,
                            incident_id=incident_id,
                            action_kind="FAILED",
                            effect_class="read",
                            payload={
                                "failureFamily": str(incident.get("failure_family") or ""),
                                "reason": "CAG_VERIFICATION_FAILED",
                            },
                        )
                    continue

            cag_verified += len(local_failures)
            for incident in incidents:
                incident_id = str(incident["incident_id"])
                already_verified = incident.get("cag_verified") is True
                _update_incident(
                    connection,
                    incident_id=incident_id,
                    status="CAG_VERIFIED",
                    cag_request_sha256=str(cag["requestSha256"]),
                    cag_response_sha256=str(cag["responseSha256"]),
                    cag_result_sha256=str(cag["resultSha256"]),
                    cag_verified=True,
                )
                if not already_verified:
                    _persist_action_receipt(
                        connection,
                        incident_id=incident_id,
                        action_kind="CAG_VERIFIED",
                        effect_class="read",
                        payload={
                            "failureMask": failure_mask(local_failures),
                            "cagRequestSha256": cag["requestSha256"],
                            "cagResponseSha256": cag["responseSha256"],
                            "cagResultSha256": cag["resultSha256"],
                        },
                    )

            # v1 deliberately refuses to auto-fix more than one simultaneous root
            # violation. The complete mask remains receipted for human review.
            if len(local_failures) != 1:
                authority_blocked += len(local_failures)
                for incident in incidents:
                    incident_id = str(incident["incident_id"])
                    _update_incident(
                        connection,
                        incident_id=incident_id,
                        status="WAITING_FOR_AUTHORITY",
                        blocker="MULTIPLE_FAILURE_FAMILIES_REQUIRE_OWNER_REVIEW",
                    )
                    _persist_action_receipt(
                        connection,
                        incident_id=incident_id,
                        action_kind="AUTHORITY_BLOCKED",
                        effect_class="read",
                        payload={"reason": "MULTIPLE_FAILURE_FAMILIES_REQUIRE_OWNER_REVIEW"},
                    )
                continue

            family = local_failures[0]
            incident_id = str(incidents[0]["incident_id"])
            repair_contract = build_repair_contract(
                observation=observation,
                failures=local_failures,
                cag_request_sha256=str(cag["requestSha256"]),
                cag_response_sha256=str(cag["responseSha256"]),
                cag_result_sha256=str(cag["resultSha256"]),
                controller_repository=_controller_repository(),
            )
            _update_incident(
                connection,
                incident_id=incident_id,
                status="CAG_VERIFIED",
                repair_contract=repair_contract,
            )
            authority = _authority_row(connection, owner_admin_id)
            if not _authority_permits(
                authority,
                family,
                len(repair_contract.get("targetFiles") or []),
            ):
                authority_blocked += 1
                _update_incident(
                    connection,
                    incident_id=incident_id,
                    status="WAITING_FOR_AUTHORITY",
                    blocker="STANDING_AUTHORITY_NOT_ACTIVE_FOR_FAILURE_FAMILY",
                )
                _persist_action_receipt(
                    connection,
                    incident_id=incident_id,
                    action_kind="AUTHORITY_BLOCKED",
                    effect_class="read",
                    payload={
                        "failureFamily": family.value,
                        "requiredAuthority": repair_contract.get("authorityRequirement"),
                        "repairContractSha256": repair_contract["repairContractSha256"],
                    },
                )
                continue
            if not owner_admin_id:
                continue
            if _recent_action_count(connection, owner_admin_id) >= int(
                (authority or {}).get("max_auto_repairs_per_hour") or 1
            ):
                authority_blocked += 1
                _update_incident(
                    connection,
                    incident_id=incident_id,
                    status="WAITING_FOR_AUTHORITY",
                    blocker="SELF_HEALING_RATE_LIMIT_REACHED",
                )
                _persist_action_receipt(
                    connection,
                    incident_id=incident_id,
                    action_kind="AUTHORITY_BLOCKED",
                    effect_class="read",
                    payload={"reason": "SELF_HEALING_RATE_LIMIT_REACHED"},
                )
                continue
            if not _claim_incident_for_action(connection, incident_id):
                continue

            # Consent revocation/expiry is re-read after the effect claim so a
            # standing grant changed during this scan is honored before mutation.
            authority = _authority_row(connection, owner_admin_id)
            if not _authority_permits(
                authority,
                family,
                len(repair_contract.get("targetFiles") or []),
            ):
                authority_blocked += 1
                _update_incident(
                    connection,
                    incident_id=incident_id,
                    status="WAITING_FOR_AUTHORITY",
                    blocker="STANDING_AUTHORITY_REVOKED_OR_EXPIRED",
                )
                _persist_action_receipt(
                    connection,
                    incident_id=incident_id,
                    action_kind="AUTHORITY_BLOCKED",
                    effect_class="read",
                    payload={"reason": "STANDING_AUTHORITY_REVOKED_OR_EXPIRED"},
                )
                continue

            if family is FailureFamily.HANDOFF_TIMEOUT_WITH_READBACK:
                if not observation.task_readback_available:
                    _update_incident(
                        connection,
                        incident_id=incident_id,
                        status="REPAIR_BLOCKED",
                        blocker="BOUND_TASK_READBACK_UNAVAILABLE_NO_RESUBMIT",
                    )
                    _persist_action_receipt(
                        connection,
                        incident_id=incident_id,
                        action_kind="REPAIR_BLOCKED",
                        effect_class="read",
                        payload={"reason": "BOUND_TASK_READBACK_UNAVAILABLE_NO_RESUBMIT"},
                    )
                    continue
                _, recovered = recover_stalled_repository_job_from_verified_readback(
                    connection,
                    user_id=candidate.user_id,
                    job_id=candidate.job_id,
                    workspace_root=workspace_root,
                )
                if recovered:
                    readback_recovered += 1
                    _touch_authority(connection, owner_admin_id)
                    _update_incident(
                        connection,
                        incident_id=incident_id,
                        status="READBACK_RECOVERED",
                        authority_owner_admin_id=owner_admin_id,
                        resolved=True,
                    )
                    _persist_action_receipt(
                        connection,
                        incident_id=incident_id,
                        action_kind="READBACK_RECOVERED",
                        effect_class="external-write",
                        payload={
                            "repairContractSha256": repair_contract["repairContractSha256"],
                            "resubmitted": False,
                            "taskReadbackVerified": True,
                        },
                    )
                else:
                    _update_incident(
                        connection,
                        incident_id=incident_id,
                        status="REPAIR_BLOCKED",
                        blocker="TASK_NOT_COMPLETED_OR_READBACK_CHANGED",
                    )
                    _persist_action_receipt(
                        connection,
                        incident_id=incident_id,
                        action_kind="REPAIR_BLOCKED",
                        effect_class="read",
                        payload={"reason": "TASK_NOT_COMPLETED_OR_READBACK_CHANGED"},
                    )
                continue

            try:
                repair_job_id = _start_code_repair(
                    connection,
                    incident_id=incident_id,
                    repair_contract=repair_contract,
                    authority_owner_admin_id=owner_admin_id,
                )
            except Exception as exc:
                failures += 1
                _update_incident(
                    connection,
                    incident_id=incident_id,
                    status="REPAIR_BLOCKED",
                    blocker=f"AGENT_ZERO_REPAIR_START_FAILED:{type(exc).__name__}",
                )
                _persist_action_receipt(
                    connection,
                    incident_id=incident_id,
                    action_kind="REPAIR_BLOCKED",
                    effect_class="external-write",
                    payload={"reason": "AGENT_ZERO_REPAIR_START_FAILED"},
                )
                continue
            repair_started += 1
            _touch_authority(connection, owner_admin_id)
            _update_incident(
                connection,
                incident_id=incident_id,
                status="REPAIR_STARTED",
                authority_owner_admin_id=owner_admin_id,
                repair_job_id=repair_job_id,
            )
            _persist_action_receipt(
                connection,
                incident_id=incident_id,
                action_kind="REPAIR_JOB_STARTED",
                effect_class="external-write",
                payload={
                    "repairContractSha256": repair_contract["repairContractSha256"],
                    "repairJobId": repair_job_id,
                    "executor": "agent-zero-a2a",
                    "automaticMerge": False,
                },
            )
        except Exception as exc:
            failures += 1
            _LOGGER.warning(
                "CAG self-healing candidate processing failed job=%s type=%s",
                candidate.job_id,
                type(exc).__name__,
            )
        finally:
            _close(connection)

    return {
        "ok": failures == 0,
        "status": "CAG_SELF_HEALING_SCAN_COMPLETED",
        "scanned": len(candidates),
        "violationsObserved": observed,
        "cagVerified": cag_verified,
        "authorityBlocked": authority_blocked,
        "readbackRecovered": readback_recovered,
        "repairJobsStarted": repair_started,
        "failures": failures,
        "mutationPerformed": bool(readback_recovered or repair_started),
        "secretValuesReturned": False,
    }


def _authority_projection(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "configured": False,
            "active": False,
            "mode": "OBSERVE_ONLY",
            "allowedFailureFamilies": [],
            "maxAutoRepairsPerHour": 0,
            "maxChangedFiles": 0,
            "expiresAt": None,
            "paused": True,
            "grantSha256": None,
            "lastUsedAt": None,
        }
    expires_at = row.get("expires_at")
    expired = bool(row.get("expired"))
    return {
        "configured": True,
        "active": not bool(row.get("paused")) and not expired,
        "mode": str(row.get("mode") or "OBSERVE_ONLY"),
        "allowedFailureFamilies": _allowed_families(row.get("allowed_failure_families")),
        "maxAutoRepairsPerHour": int(row.get("max_auto_repairs_per_hour") or 0),
        "maxChangedFiles": int(row.get("max_changed_files") or 0),
        "expiresAt": expires_at.isoformat() if getattr(expires_at, "isoformat", None) else str(expires_at or "") or None,
        "paused": bool(row.get("paused")),
        "grantSha256": str(row.get("grant_sha256") or "") or None,
        "lastUsedAt": (
            row.get("last_used_at").isoformat()
            if getattr(row.get("last_used_at"), "isoformat", None)
            else str(row.get("last_used_at") or "") or None
        ),
    }


def _admin_id(get_current_admin: Callable[[], Any]) -> str:
    admin = get_current_admin() or {}
    value = str(admin.get("id") or "").strip().casefold() if isinstance(admin, Mapping) else ""
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, AttributeError):
        return ""
    return parsed


def _upsert_authority(
    connection: Any,
    *,
    owner_admin_id: str,
    mode: str,
    allowed_failure_families: Sequence[str],
    max_auto_repairs_per_hour: int,
    max_changed_files: int,
    expires_in_seconds: int,
    paused: bool,
) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip().upper()
    allowed_modes = {"OBSERVE_ONLY", "ASK_FIRST", "AUTO_SAFE", "AUTO_BOUNDED_CODE_REPAIR"}
    if normalized_mode not in allowed_modes:
        raise SelfHealingContractError("authority mode is invalid")
    requested = {str(item).strip().upper() for item in allowed_failure_families}
    known = {family.value for family in FAILURE_ORDER}
    if not requested or not requested.issubset(known):
        raise SelfHealingContractError("allowed failure families are invalid")
    max_rate = int(max_auto_repairs_per_hour)
    max_files = int(max_changed_files)
    expires_seconds = int(expires_in_seconds)
    if not 1 <= max_rate <= 10:
        raise SelfHealingContractError("maxAutoRepairsPerHour must be between 1 and 10")
    if not 1 <= max_files <= 50:
        raise SelfHealingContractError("maxChangedFiles must be between 1 and 50")
    if not 300 <= expires_seconds <= 604800:
        raise SelfHealingContractError("expiresInSeconds must be between 300 and 604800")

    ordered = [family.value for family in FAILURE_ORDER if family.value in requested]
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    grant = {
        "schemaVersion": AUTHORITY_SCHEMA_VERSION,
        "ownerAdminIdSha256": sha256_text(owner_admin_id),
        "mode": normalized_mode,
        "allowedFailureFamilies": ordered,
        "maxAutoRepairsPerHour": max_rate,
        "maxChangedFiles": max_files,
        "expiresAt": expires_at.isoformat(),
        "paused": bool(paused),
    }
    grant_sha = sha256_json(grant)
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_self_healing_authority (
                owner_admin_id, schema_version, mode, allowed_failure_families,
                max_auto_repairs_per_hour, max_changed_files, expires_at, paused,
                grant_sha256
            ) VALUES (%s::uuid,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
            ON CONFLICT (owner_admin_id) DO UPDATE SET
                schema_version=EXCLUDED.schema_version,
                mode=EXCLUDED.mode,
                allowed_failure_families=EXCLUDED.allowed_failure_families,
                max_auto_repairs_per_hour=EXCLUDED.max_auto_repairs_per_hour,
                max_changed_files=EXCLUDED.max_changed_files,
                expires_at=EXCLUDED.expires_at,
                paused=EXCLUDED.paused,
                grant_sha256=EXCLUDED.grant_sha256,
                updated_at=NOW()
            """,
            (
                owner_admin_id,
                AUTHORITY_SCHEMA_VERSION,
                normalized_mode,
                canonical_json(ordered),
                max_rate,
                max_files,
                expires_at,
                bool(paused),
                grant_sha,
            ),
        )
    connection.commit()
    row = _authority_row(connection, owner_admin_id)
    return _authority_projection(row)


def _revoke_authority(connection: Any, owner_admin_id: str) -> dict[str, Any]:
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE sovereign_self_healing_authority
            SET mode='OBSERVE_ONLY',
                allowed_failure_families='[]'::jsonb,
                paused=TRUE,
                expires_at=NOW(),
                updated_at=NOW()
            WHERE owner_admin_id=%s::uuid
            """,
            (owner_admin_id,),
        )
    connection.commit()
    return _authority_projection(_authority_row(connection, owner_admin_id))


def _incident_projection(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "incidentId": str(row.get("incident_id") or ""),
        "sourceJobId": str(row.get("source_job_id") or ""),
        "failureFamily": str(row.get("failure_family") or ""),
        "observationSha256": str(row.get("observation_sha256") or ""),
        "cagVerified": bool(row.get("cag_verified")),
        "cagRequestSha256": str(row.get("cag_request_sha256") or "") or None,
        "cagResponseSha256": str(row.get("cag_response_sha256") or "") or None,
        "cagResultSha256": str(row.get("cag_result_sha256") or "") or None,
        "repairContractSha256": str(row.get("repair_contract_sha256") or "") or None,
        "repairJobId": str(row.get("repair_job_id") or "") or None,
        "status": str(row.get("status") or ""),
        "blocker": str(row.get("blocker") or "") or None,
        "createdAt": (
            row.get("created_at").isoformat()
            if getattr(row.get("created_at"), "isoformat", None)
            else str(row.get("created_at") or "")
        ),
        "updatedAt": (
            row.get("updated_at").isoformat()
            if getattr(row.get("updated_at"), "isoformat", None)
            else str(row.get("updated_at") or "")
        ),
    }


def register_cag_self_healing_admin_routes(
    app: Any,
    *,
    get_connection: ConnectionFactory,
    require_admin: Callable[..., Any],
    get_current_admin: Callable[[], Any],
) -> None:
    # Flask is a production/web dependency; keep the deterministic/runtime module
    # importable by repository tests that intentionally install no web stack.
    from flask import jsonify, request
    @app.route("/api/admin/self-healing/authority", methods=["GET"])
    @require_admin
    def _self_healing_authority_get():
        owner_admin_id = _admin_id(get_current_admin)
        if not owner_admin_id:
            return jsonify({"error": "admin_identity_missing"}), 401
        configured_owner = _configured_owner_admin_id()
        if not configured_owner:
            return jsonify({"error": "owner_identity_not_configured"}), 503
        if owner_admin_id != configured_owner:
            return jsonify({"error": "owner_authority_required"}), 403
        connection = get_connection()
        try:
            return jsonify({
                "ok": True,
                "authority": _authority_projection(_authority_row(connection, owner_admin_id)),
                "consentNotice": (
                    "Standing authority is scoped, rate-limited, expiring and immediately revocable. "
                    "CAG never gains mutation authority and Agent Zero remains the only repository executor."
                ),
                "secretValuesReturned": False,
            }), 200
        finally:
            _close(connection)

    @app.route("/api/admin/self-healing/authority", methods=["PUT"])
    @require_admin
    def _self_healing_authority_put():
        owner_admin_id = _admin_id(get_current_admin)
        if not owner_admin_id:
            return jsonify({"error": "admin_identity_missing"}), 401
        configured_owner = _configured_owner_admin_id()
        if not configured_owner:
            return jsonify({"error": "owner_identity_not_configured"}), 503
        if owner_admin_id != configured_owner:
            return jsonify({"error": "owner_authority_required"}), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "invalid_request"}), 400
        allowed_keys = {
            "mode", "allowedFailureFamilies", "maxAutoRepairsPerHour",
            "maxChangedFiles", "expiresInSeconds", "paused",
        }
        if set(body) - allowed_keys:
            return jsonify({"error": "invalid_request"}), 400
        try:
            connection = get_connection()
            try:
                projection = _upsert_authority(
                    connection,
                    owner_admin_id=owner_admin_id,
                    mode=str(body.get("mode") or ""),
                    allowed_failure_families=(
                        body.get("allowedFailureFamilies")
                        if isinstance(body.get("allowedFailureFamilies"), list)
                        else []
                    ),
                    max_auto_repairs_per_hour=int(body.get("maxAutoRepairsPerHour") or 1),
                    max_changed_files=int(body.get("maxChangedFiles") or 8),
                    expires_in_seconds=int(body.get("expiresInSeconds") or 0),
                    paused=bool(body.get("paused", False)),
                )
            finally:
                _close(connection)
        except (SelfHealingContractError, TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "authority": projection, "secretValuesReturned": False}), 200

    @app.route("/api/admin/self-healing/authority", methods=["DELETE"])
    @require_admin
    def _self_healing_authority_delete():
        owner_admin_id = _admin_id(get_current_admin)
        if not owner_admin_id:
            return jsonify({"error": "admin_identity_missing"}), 401
        configured_owner = _configured_owner_admin_id()
        if not configured_owner:
            return jsonify({"error": "owner_identity_not_configured"}), 503
        if owner_admin_id != configured_owner:
            return jsonify({"error": "owner_authority_required"}), 403
        connection = get_connection()
        try:
            projection = _revoke_authority(connection, owner_admin_id)
        finally:
            _close(connection)
        return jsonify({
            "ok": True,
            "authority": projection,
            "revoked": True,
            "secretValuesReturned": False,
        }), 200

    @app.route("/api/admin/self-healing/incidents", methods=["GET"])
    @require_admin
    def _self_healing_incidents_get():
        connection = get_connection()
        try:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT incident_id, source_job_id, failure_family, observation_sha256,
                           cag_verified, cag_request_sha256, cag_response_sha256,
                           cag_result_sha256, repair_contract_sha256, repair_job_id,
                           status, blocker, created_at, updated_at
                    FROM sovereign_self_healing_incidents
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (_MAX_INCIDENTS_API,),
                )
                rows = cur.fetchall()
        finally:
            _close(connection)
        return jsonify({
            "ok": True,
            "incidents": [_incident_projection(dict(row)) for row in rows],
            "secretValuesReturned": False,
        }), 200


def start_cag_self_healing_reconciler(
    *,
    get_connection: ConnectionFactory,
    workspace_root: Path | None = None,
) -> bool:
    """Start one process-local bounded scanner; DB claims prevent duplicate effects."""
    global _THREAD
    with _THREAD_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return False

        def loop() -> None:
            while True:
                try:
                    process_cag_self_healing_once(
                        get_connection=get_connection,
                        workspace_root=workspace_root,
                    )
                except Exception as exc:
                    _LOGGER.warning(
                        "CAG self-healing scan failed type=%s",
                        type(exc).__name__,
                    )
                time.sleep(_poll_seconds())

        _THREAD = threading.Thread(
            target=loop,
            name="sovereign-cag-self-healing-reconciler",
            daemon=True,
        )
        _THREAD.start()
        return True


__all__ = [
    "process_cag_self_healing_once",
    "register_cag_self_healing_admin_routes",
    "start_cag_self_healing_reconciler",
]
