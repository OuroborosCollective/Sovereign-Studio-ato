"""Read-only, authenticated UI projections of existing runtime and billing owners.

No registry, balance, agent, permission or execution state is created here.
"""
from datetime import datetime, timezone
import os
from typing import Any, Callable

from llm_execution_resolver import (
    ExecutionResolutionError, FREE_SINGLE_AGENT_PROFILE, FREE_SWARM_PROFILE, PAID_SWARM_PROFILE, load_execution_resolution,
)
from paid_execution_entitlement import resolve_paid_execution_entitlement

from .durable_workflow import canonical_sha256
from .repository_execution import repository_execution_manifest


def _at(value: Any) -> str:
    text = value.isoformat() if isinstance(value, datetime) else str(value or "")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("readback_timestamp_invalid")
    return parsed.isoformat()


def read_control_surface_credits(conn: Any, *, user_id: str) -> dict[str, Any]:
    """Verify the account cache against its append-only ledger in one DB snapshot."""
    with conn.cursor() as cur:
        cur.execute(
            """/* control-surface:credits */
            SELECT account.id::text, account.email, account.role,
                   account.credits::integer, account.provider_funded_credits::integer,
                   COALESCE(SUM(ledger.amount), 0)::integer AS ledger_balance,
                   EXISTS (SELECT 1 FROM transactions tx
                     JOIN credit_receipts receipt ON receipt.user_id = tx.user_id
                       AND receipt.provider = tx.provider AND receipt.provider_tx_id = tx.provider_tx_id
                     WHERE tx.user_id = account.id AND tx.type = 'credit_purchase'
                       AND tx.status = 'completed') AS purchase_verified
            FROM admin_users account
            LEFT JOIN credit_ledger ledger ON ledger.user_id = account.id
            WHERE account.id = %s::uuid
            GROUP BY account.id
            LIMIT 1""", (str(user_id),),
        )
        account = cur.fetchone()
    if not account:
        raise LookupError("authenticated_account_missing")
    credits = account.get("credits")
    funded = account.get("provider_funded_credits")
    ledger = account.get("ledger_balance")
    if (any(type(value) is not int or value < 0 for value in (credits, funded, ledger))
            or credits != ledger or funded > credits):
        raise ValueError("credit_state_verification_failed")
    entitlement = resolve_paid_execution_entitlement(
        account_id=str(account["id"]), email=str(account.get("email") or ""),
        role=str(account.get("role") or ""), purchase_verified=bool(account["purchase_verified"]),
        credit_balance=credits, configured_owner_id=os.getenv("SOVEREIGN_OWNER_ADMIN_ID", ""),
        configured_owner_email=os.getenv("SOVEREIGN_OWNER_ADMIN_EMAIL", ""),
    )
    return {"readbackState": "live", "credits": credits, "providerFundedCredits": funded,
            "creditStateVerified": True, "paidEntitlementVerified": entitlement.verified,
            "paidEntitlementSource": entitlement.source}


def read_control_surface_agents(conn: Any, *, user_id: str, job: Any | None) -> list[dict[str, Any]]:
    policy = repository_execution_manifest()
    if job is None:
        return [{"id": policy["executor"], "name": policy["executor"], "status": "DECLARED",
                 "source": "repository-execution-manifest", "kind": "executor",
                 "description": "Registered single-agent repository executor. No active job is selected."}]
    reference = str(job.external_ref or "")
    queued = reference.startswith("sovereign-local-runner:pending:submit:")
    state = "QUEUED" if queued and job.status == "running" else str(job.status).upper()
    agents = [{"id": str(job.executor), "name": str(job.executor), "status": state,
               "source": "sovereign-agent-jobs", "kind": "executor", "jobId": job.job_id,
               "description": "Persisted executor/job state; a running job alone does not prove a live agent."}]
    with conn.cursor() as cur:
        cur.execute(
            """/* control-surface:agents */
            SELECT DISTINCT ON (task.agent_id) task.agent_id, task.task_id, task.run_id,
                   task.status, task.source, task.created_at, task.updated_at
            FROM sovereign_agent_jobs job
            JOIN agent_runs run ON run.job_id = job.job_id AND run.user_id = job.user_id
            JOIN agent_tasks task ON task.run_id = run.run_id
            WHERE job.user_id = %s::uuid AND job.job_id = %s
              AND run.source = 'agents-sdk' AND task.source = 'agents-sdk'
            ORDER BY task.agent_id, task.created_at DESC, task.task_id DESC
            LIMIT 128""", (str(user_id), str(job.job_id)),
        )
        rows = cur.fetchall()
    for row in rows:
        persisted = str(row["status"])
        agents.append({
            "id": str(row["agent_id"]), "name": str(row["agent_id"]), "kind": "agent",
            "status": str(job.status).upper() if job.status in {"blocked", "failed", "cancelled"} else persisted,
            "persistedStatus": persisted, "source": "agents-sdk", "jobId": str(job.job_id),
            "runId": str(row["run_id"]), "taskId": str(row["task_id"]),
            "createdAt": _at(row["created_at"]), "updatedAt": _at(row["updated_at"]),
            "description": "Actual persisted agent task. Its status is separate from executor heartbeat and progress.",
        })
    return agents


def read_control_surface_integrations(reader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Expose bounded service readbacks, never credentials, endpoints or raw evidence."""
    result = []
    statuses = {"verified", "blocked", "degraded", "isolated", "defined_not_run"}
    for row in reader():
        if not isinstance(row, dict) or row.get("status") not in statuses or not row.get("id") or not row.get("label"):
            raise ValueError("integration_readback_invalid")
        item = {"id": str(row["id"]), "name": str(row["label"]), "status": row["status"],
                "source": "enterprise-platform-readback", "observedAt": _at(row.get("checkedAt")),
                "boundary": str(row.get("boundary") or "")[:300],
                "blocker": str(row.get("blocker") or "")[:160] or None}
        item["readbackSha256"] = canonical_sha256(item)
        result.append(item)
    return result


def read_control_surface_routing(get_connection: Callable, *, user_id: str, credits: dict) -> dict:
    policy = repository_execution_manifest()
    modes = []
    for mode in ("free", "paid"):
        item: dict[str, Any] = {"mode": mode, "available": False, "providerAvailable": False}
        try:
            resolution = load_execution_resolution(get_connection, user_id=user_id, requested_mode=mode)
            if resolution is None:
                item["blocker"] = "verified_provider_route_unavailable"
            else:
                item.update({"providerAvailable": True, "model": str(resolution.primary_route.get("model_id") or ""),
                             "routeId": str(resolution.primary_route.get("id") or ""), "profileId": resolution.profile_id})
                profiles = {PAID_SWARM_PROFILE} if mode == "paid" else {FREE_SINGLE_AGENT_PROFILE, FREE_SWARM_PROFILE}
                item["available"] = (mode in policy["executionModes"] and resolution.repository_execution_allowed
                                     and resolution.profile_id in profiles)
                if not item["available"]:
                    item["blocker"] = "single_agent_route_required"
        except ExecutionResolutionError as exc:
            item["blocker"] = exc.failure_family
        except Exception:
            item["blocker"] = "route_readback_unavailable"
        if mode == "paid":
            if credits.get("creditStateVerified") is not True:
                item["available"] = False
                item["providerAvailable"] = False
                item["blocker"] = "credit_state_verification_failed"
            elif not credits.get("paidEntitlementVerified"):
                item["available"] = False
                item["blocker"] = "paid_purchase_required"
                item["executionBlocker"] = "paid_entitlement_required"
            elif not credits.get("providerFundedCredits"):
                item["available"] = False
                item["blocker"] = "paid_credits_required"
                item["executionBlocker"] = "provider_funded_credits_required"
        modes.append(item)
    return {"repositoryMode": policy["executionModes"][0], "agentMode": policy["agentMode"], "modes": modes}
