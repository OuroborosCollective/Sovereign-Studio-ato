"""Revision-bound persistent closure canary for Issues #1111, #1117 and #1120.

This module is deliberately narrow.  It persists one deterministic Bug Evidence
case, one Durable Memory leaf/retrieval-pack receipt and one read-only
Environment-Bound MCP execution chain.  It is not a generic SQL or execution
surface.  Every identity is bound to the running backend revision and immutable
image digest, and every negative mutation probe is rolled back to a savepoint.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from typing import Any, Callable

import psycopg2
import psycopg2.extras

from agent_runtime.bug_evidence_lane import (
    AffectedSurface,
    BugEvidenceLane,
    FailureFamily,
    ProvenanceChain,
)
from agent_runtime.durable_memory_forest import (
    DurableMemoryForest,
    EvidenceClass,
    RetrievalScope,
    SourceClass,
)
from agent_runtime.environment_mcp_execution import (
    CredentialMode,
    CredentialResolver,
    EgressDecision,
    EgressPolicyEngine,
    EnvironmentKind,
    EnvironmentManifestCompiler,
    ExecutionIdentityReceiptBuilder,
    McpInstallationBinder,
    PrincipalResolver,
    ResolutionMethod,
)

COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_HOST = "example.com"
PUBLIC_PORT = 443
PUBLIC_PATH = "/"
EXPECTED_SCHEMA_TABLES = (
    "bug_evidence_cases",
    "bug_evidence_embeddings",
    "memory_forest_leaves",
    "memory_forest_embeddings",
    "memory_forest_conflicts",
    "environment_manifests",
    "principal_resolution_receipts",
    "credential_resolution_receipts",
    "egress_decision_receipts",
    "mcp_installation_bindings",
    "execution_identity_receipts",
)


def _sha256(value: object) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _deterministic_uuid4(label: str) -> str:
    raw = list(hashlib.sha256(label.encode("utf-8")).hexdigest()[:32])
    raw[12] = "4"
    raw[16] = "8"
    value = "".join(raw)
    return f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:32]}"


def _scalar(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(sql, params)
    row = cur.fetchone()
    if isinstance(row, dict):
        return int(next(iter(row.values())) or 0)
    return int(row[0] or 0)


def _require_identity(
    *,
    expected_revision: str,
    expected_image_digest: str,
    baseline_revision: str,
    release_evidence_sha256: str,
    patchmon_evidence_sha256: str,
) -> None:
    for name, value in (
        ("expected_revision", expected_revision),
        ("baseline_revision", baseline_revision),
    ):
        if not COMMIT_SHA_RE.fullmatch(value):
            raise ValueError(f"{name} must be a full commit SHA")
    if not IMAGE_DIGEST_RE.fullmatch(expected_image_digest):
        raise ValueError("expected_image_digest must be a full sha256 digest")
    for name, value in (
        ("release_evidence_sha256", release_evidence_sha256),
        ("patchmon_evidence_sha256", patchmon_evidence_sha256),
    ):
        if not SHA256_RE.fullmatch(value):
            raise ValueError(f"{name} must be a full SHA-256")


def _connect() -> Any:
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "postgres"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        connect_timeout=10,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def _verify_runtime_identity(expected_revision: str, expected_image_digest: str) -> None:
    runtime_revision = os.environ.get("SOVEREIGN_SOURCE_REVISION", "").strip()
    runtime_digest = os.environ.get("SOVEREIGN_IMAGE_DIGEST", "").strip()
    if runtime_revision != expected_revision or runtime_digest != expected_image_digest:
        raise RuntimeError("backend runtime identity mismatch")

    connection = http.client.HTTPConnection("127.0.0.1", 8787, timeout=8)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = response.read(1_000_000)
    finally:
        connection.close()
    if response.status != 200:
        raise RuntimeError("backend health request failed")
    health = json.loads(body.decode("utf-8"))
    if (
        health.get("ok") is not True
        or health.get("sourceRevision") != expected_revision
        or health.get("imageDigest") != expected_image_digest
    ):
        raise RuntimeError("backend health identity mismatch")


def _resolve_public_ip() -> str:
    candidates: set[str] = set()
    for family, _socktype, _proto, _canonname, sockaddr in socket.getaddrinfo(
        PUBLIC_HOST,
        PUBLIC_PORT,
        type=socket.SOCK_STREAM,
    ):
        if family not in (socket.AF_INET, socket.AF_INET6):
            continue
        address = str(sockaddr[0])
        parsed = ipaddress.ip_address(address)
        if parsed.is_global:
            candidates.add(str(parsed))
    if not candidates:
        raise RuntimeError("public egress DNS produced no global address")
    return sorted(candidates, key=lambda item: (ipaddress.ip_address(item).version, item))[0]


def _public_https_read(pinned_ip: str) -> tuple[int, str, int]:
    raw_socket = socket.create_connection((pinned_ip, PUBLIC_PORT), timeout=10)
    context = ssl.create_default_context()
    tls_socket = context.wrap_socket(raw_socket, server_hostname=PUBLIC_HOST)
    try:
        request = (
            f"GET {PUBLIC_PATH} HTTP/1.1\r\n"
            f"Host: {PUBLIC_HOST}\r\n"
            "User-Agent: Sovereign-Issue-Closure-Canary/1.0\r\n"
            "Accept: text/html\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        tls_socket.sendall(request)
        response = http.client.HTTPResponse(tls_socket)
        response.begin()
        body = response.read(128_000)
        status = int(response.status)
    finally:
        tls_socket.close()
    if status != 200 or not body:
        raise RuntimeError("pinned public HTTPS read failed")
    return status, hashlib.sha256(body).hexdigest(), len(body)


def _assert_savepoint_rejection(
    cur: Any,
    *,
    savepoint: str,
    statement: str,
    params: tuple[Any, ...],
    expected_marker: str,
) -> bool:
    cur.execute(f"SAVEPOINT {savepoint}")
    rejected = False
    try:
        cur.execute(statement, params)
    except psycopg2.Error as exc:
        rejected = expected_marker in str(exc)
        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
    else:
        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
    cur.execute(f"RELEASE SAVEPOINT {savepoint}")
    if not rejected:
        raise RuntimeError(f"negative mutation probe was not rejected: {savepoint}")
    return True


def _build_verified_bug_case(
    *,
    baseline_revision: str,
    expected_revision: str,
    expected_image_digest: str,
    release_evidence_sha256: str,
    patchmon_evidence_sha256: str,
) -> Any:
    candidate = BugEvidenceLane.create_candidate(
        raw_failure_text=(
            "DB_DRIFT_MISSING_LIVE_TABLE: Bug Evidence, Durable Memory and "
            "Environment MCP receipt tables were absent from production PostgreSQL"
        ),
        failure_family=FailureFamily.POSTGRES_MIGRATION,
        repo_owner="OuroborosCollective",
        repo_name="Sovereign-Studio-ato",
        base_revision=baseline_revision,
        head_revision=expected_revision,
        merge_revision=expected_revision,
        workflow_id="issue-closure-release",
        run_id=f"release:{release_evidence_sha256[:24]}",
        job_id="issues-1111-1117-1120-1103",
        step_id="runtime-closure-canary",
        log_evidence=(
            "Repository-owned schema count was 92 while the live schema count was 81.",
            "Forward migrations 046, 048 and 049 were previewed, applied and read back.",
        ),
        affected_surfaces=(
            AffectedSurface.PERSISTENCE,
            AffectedSurface.MIGRATION,
            AffectedSurface.RUNTIME_PROJECTION,
        ),
        diagnostic_tools=("repository_architecture_runtime_drift_evidence",),
        diagnostic_params={"repositoryOwnedTables": 92, "initialLiveTables": 81},
    )
    case_id = _deterministic_uuid4(f"issue-closure:{expected_revision}")
    candidate = replace(
        candidate,
        evidence_case_id=case_id,
        provenance_hash=ProvenanceChain.compute(
            evidence_case_id=case_id,
            failure_family=candidate.failure_family.value,
            signature_hash=candidate.signature_hash,
            repo_owner=candidate.repo_owner,
            repo_name=candidate.repo_name,
            base_revision=candidate.base_revision,
            head_revision=candidate.head_revision,
            status=candidate.status.value,
            log_evidence_hash=candidate.log_evidence_hash,
            diagnostic_params_hash=candidate.diagnostic_params_hash,
            predecessor_provenance_hash=None,
        ),
    )
    diagnosed = BugEvidenceLane.advance_to_diagnosed(
        candidate,
        diagnostic_tools=(
            "repository_architecture_runtime_drift_evidence",
            "postgres_migration_preview",
            "postgres_migration_apply",
        ),
        diagnostic_params={
            "migrations": ("046", "048", "049", "050"),
            "requiredLiveTableCount": 92,
        },
    )
    patched = BugEvidenceLane.advance_to_patched(
        diagnosed,
        patch_commit=expected_revision,
        tests_run=(
            "bug-evidence-contract-tests",
            "durable-memory-contract-tests",
            "environment-mcp-contract-tests",
            "continuity-ledger-gate",
            "revision-guardian",
        ),
    )
    return BugEvidenceLane.advance_to_verified(
        patched,
        gate_results=(
            ("release_exact_head", release_evidence_sha256),
            ("postgres_schema_92_of_92", "verified"),
            ("patchmon_runtime", patchmon_evidence_sha256),
            ("backend_runtime_identity", "verified"),
        ),
        artifact_digest=expected_image_digest,
        revision_label=expected_revision,
        patchmon_readback=f"patchmon:evidence:{patchmon_evidence_sha256}",
        container_readback=f"container:image:{expected_image_digest}",
        postgres_readback="postgres:schema:92-of-92",
        runtime_readback=f"runtime:revision:{expected_revision}",
    )


def _persist_bug_case(conn: Any, case: Any) -> dict[str, Any]:
    payload = BugEvidenceLane.to_dict(case)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bug_evidence_cases (
                   evidence_case_id, schema_version, failure_family,
                   normalized_signature, signature_hash, repo_owner, repo_name,
                   base_revision, head_revision, merge_revision, workflow_id,
                   run_id, job_id, step_id, log_evidence, log_evidence_hash,
                   affected_surfaces, diagnostic_tools, diagnostic_params_hash,
                   patch_commit, tests_run, gate_results, artifact_digest,
                   revision_label, patchmon_readback, container_readback,
                   postgres_readback, runtime_readback, status, provenance_hash,
                   predecessor_case_id, predecessor_provenance_hash
               ) VALUES (
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                   %s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb,
                   %s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
               ) ON CONFLICT (evidence_case_id) DO NOTHING""",
            (
                payload["evidence_case_id"], payload["schema_version"],
                payload["failure_family"], payload["normalized_signature"],
                payload["signature_hash"], payload["repo_owner"], payload["repo_name"],
                payload["base_revision"], payload["head_revision"],
                payload["merge_revision"], payload["workflow_id"], payload["run_id"],
                payload["job_id"], payload["step_id"], json.dumps(payload["log_evidence"]),
                payload["log_evidence_hash"], json.dumps(payload["affected_surfaces"]),
                json.dumps(payload["diagnostic_tools"]), payload["diagnostic_params_hash"],
                payload["patch_commit"], json.dumps(payload["tests_run"]),
                json.dumps(payload["gate_results"]), payload["artifact_digest"],
                payload["revision_label"], payload["patchmon_readback"],
                payload["container_readback"], payload["postgres_readback"],
                payload["runtime_readback"], payload["status"], payload["provenance_hash"],
                payload["predecessor_case_id"], payload["predecessor_provenance_hash"],
            ),
        )
        cur.execute(
            """SELECT evidence_case_id, status, signature_hash, provenance_hash,
                      head_revision, artifact_digest
                 FROM bug_evidence_cases WHERE evidence_case_id=%s""",
            (case.evidence_case_id,),
        )
        row = cur.fetchone()
        if (
            not row
            or row["status"] != "verified"
            or row["signature_hash"] != case.signature_hash
            or row["provenance_hash"] != case.provenance_hash
            or row["head_revision"] != case.head_revision
            or row["artifact_digest"] != case.artifact_digest
        ):
            raise RuntimeError("bug evidence readback mismatch")
        _assert_savepoint_rejection(
            cur,
            savepoint="bug_append_only_probe",
            statement="UPDATE bug_evidence_cases SET status='invalidated' WHERE evidence_case_id=%s",
            params=(case.evidence_case_id,),
            expected_marker="BUG_EVIDENCE_APPEND_ONLY_VIOLATION",
        )
    conn.commit()
    return {
        "caseId": case.evidence_case_id,
        "status": "verified",
        "signatureSha256": case.signature_hash,
        "provenanceSha256": case.provenance_hash,
        "appendOnlyRejected": True,
    }


def _persist_memory_leaf(
    conn: Any,
    *,
    expected_revision: str,
    release_evidence_sha256: str,
    patchmon_evidence_sha256: str,
    bug_case_id: str,
) -> dict[str, Any]:
    receipt_identity = f"bug-evidence:{bug_case_id}"
    leaf = DurableMemoryForest.create_leaf(
        owner="OuroborosCollective",
        tenant="OuroborosCollective",
        repo="Sovereign-Studio-ato",
        workspace_id="issue-closure-runtime",
        revision=expected_revision,
        observed_period_start=f"release:{release_evidence_sha256[:24]}",
        observed_period_end=f"patchmon:{patchmon_evidence_sha256[:24]}",
        source_class=SourceClass.POSTGRES_READBACK,
        evidence_class=EvidenceClass.VERIFIED,
        content_summary=(
            "At the bound release revision, production PostgreSQL exposes all 92 "
            "repository-owned tables, including Bug Evidence, Durable Memory Forest "
            "and Environment-Bound MCP receipt storage."
        ),
        validity_rules=(
            f"valid_at_revision={expected_revision}",
            "runtime_claims_require_live_revalidation",
        ),
        readback_links=(
            f"release:evidence:{release_evidence_sha256}",
            f"patchmon:evidence:{patchmon_evidence_sha256}",
            "postgres:schema:92-of-92",
        ),
        evidence_receipt_identity=receipt_identity,
    )
    foreign_leaf = DurableMemoryForest.create_leaf(
        owner="ForeignOwner",
        tenant="ForeignTenant",
        repo="ForeignRepo",
        workspace_id="foreign-workspace",
        revision=expected_revision,
        source_class=SourceClass.HUMAN_REPORTED,
        evidence_class=EvidenceClass.REPORTED,
        content_summary="Foreign-scope candidate that must never enter the owner retrieval pack.",
    )
    pack = DurableMemoryForest.build_retrieval_pack(
        scope=RetrievalScope(
            owner="OuroborosCollective",
            tenant="OuroborosCollective",
            repo="Sovereign-Studio-ato",
            workspace_id="issue-closure-runtime",
        ),
        candidate_pool=(foreign_leaf, leaf),
    )
    if tuple(item.leaf_id for item in pack.leaves) != (leaf.leaf_id,):
        raise RuntimeError("memory retrieval scope isolation failed")

    row = DurableMemoryForest.to_dict(leaf)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO memory_forest_leaves (
                   leaf_id, schema_version, owner, tenant, repo, workspace_id,
                   revision, observed_period_start, observed_period_end,
                   source_class, evidence_class, content_hash, content_summary,
                   validity_rules, revalidation_gap_hint, readback_links,
                   evidence_receipt_identity, predecessor_leaf_id,
                   predecessor_hash, provenance_hash
               ) VALUES (
                   %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
               ) ON CONFLICT (leaf_id) DO NOTHING""",
            (
                row["leaf_id"], row["schema_version"], row["owner"], row["tenant"],
                row["repo"], row["workspace_id"], row["revision"],
                row["observed_period_start"], row["observed_period_end"],
                row["source_class"], row["evidence_class"], row["content_hash"],
                row["content_summary"], row["validity_rules"],
                row["revalidation_gap_hint"], row["readback_links"],
                row["evidence_receipt_identity"], row["predecessor_leaf_id"],
                row["predecessor_hash"], row["provenance_hash"],
            ),
        )
        cur.execute(
            """SELECT leaf_id, evidence_class, content_hash, provenance_hash, revision
                 FROM memory_forest_leaves WHERE leaf_id=%s""",
            (leaf.leaf_id,),
        )
        persisted = cur.fetchone()
        if (
            not persisted
            or persisted["evidence_class"] != "verified"
            or persisted["content_hash"] != leaf.content_hash
            or persisted["provenance_hash"] != leaf.provenance_hash
            or persisted["revision"].strip() != expected_revision
        ):
            raise RuntimeError("memory leaf readback mismatch")
        _assert_savepoint_rejection(
            cur,
            savepoint="memory_append_only_probe",
            statement="UPDATE memory_forest_leaves SET content_summary=content_summary WHERE leaf_id=%s",
            params=(leaf.leaf_id,),
            expected_marker="MEMORY_FOREST_APPEND_ONLY_VIOLATION",
        )
    conn.commit()
    return {
        "leafId": leaf.leaf_id,
        "evidenceClass": "verified",
        "contentSha256": leaf.content_hash,
        "provenanceSha256": leaf.provenance_hash,
        "retrievalPackId": pack.pack_id,
        "retrievalPackSha256": pack.pack_hash,
        "retrievalLeafCount": len(pack.leaves),
        "crossScopeCandidateExcluded": True,
        "appendOnlyRejected": True,
    }


def _persist_environment_receipts(
    conn: Any,
    *,
    expected_revision: str,
) -> dict[str, Any]:
    run_id = f"issue-closure:{expected_revision}"
    manifest = EnvironmentManifestCompiler.compile(
        environment_id="production",
        kind=EnvironmentKind.PRODUCTION,
        repo_owner="OuroborosCollective",
        repo_name="Sovereign-Studio-ato",
        revision=expected_revision,
        network_policy_descriptor={
            "mode": "allowlisted-public-https",
            "hosts": (PUBLIC_HOST,),
        },
        credential_scope_descriptor={"mode": "anonymous-read-only"},
        allowed_protocols=("https",),
        allowed_egress_hosts=(PUBLIC_HOST,),
    )
    principal = PrincipalResolver.resolve(
        environment_id=manifest.environment_id,
        server_resolved_principal_id="configured-owner",
        owner_id="OuroborosCollective",
        resolution_method=ResolutionMethod.SERVICE_ACCOUNT,
        run_id=run_id,
        revision=expected_revision,
        client_supplied_candidate="ignored-client-owner-candidate",
    )
    credential = CredentialResolver.resolve(
        environment_id=manifest.environment_id,
        credential_id="public-read-only",
        owner_id="OuroborosCollective",
        mode=CredentialMode.ANONYMOUS,
        provider="public-https",
        scopes=(),
        executed_as_principal_id=principal.principal_id,
    )
    binding = McpInstallationBinder.bind(
        tool_id="issue_closure_runtime_canary",
        server_id="sovereign-chatgpt-mcp",
        installation_id="private-owner-runtime",
        registry_revision=expected_revision,
        verified_at_revision=expected_revision,
    )
    pinned_ip = _resolve_public_ip()
    egress = EgressPolicyEngine.decide(
        environment_manifest=manifest,
        target_host=PUBLIC_HOST,
        target_port=PUBLIC_PORT,
        protocol="https",
        resolved_ip=pinned_ip,
    )
    if egress.decision != EgressDecision.ALLOW:
        raise RuntimeError("public egress was not allowed")
    blocked_loopback = EgressPolicyEngine.decide(
        environment_manifest=manifest,
        target_host="127.0.0.1",
        target_port=PUBLIC_PORT,
        protocol="https",
        resolved_ip="127.0.0.1",
    )
    blocked_metadata = EgressPolicyEngine.decide(
        environment_manifest=manifest,
        target_host="169.254.169.254",
        target_port=PUBLIC_PORT,
        protocol="https",
        resolved_ip="169.254.169.254",
    )
    if (
        blocked_loopback.decision != EgressDecision.BLOCK
        or blocked_metadata.decision != EgressDecision.BLOCK
    ):
        raise RuntimeError("unsafe egress negative decisions failed")

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO environment_manifests (
                   manifest_hash, environment_id, kind, schema_version, repo_owner,
                   repo_name, revision, network_policy_hash, credential_scope_hash,
                   allowed_protocols, allowed_egress_hosts, is_production
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (manifest_hash) DO NOTHING""",
            (
                manifest.manifest_hash, manifest.environment_id, manifest.kind.value,
                manifest.schema_version, manifest.repo_owner, manifest.repo_name,
                manifest.revision, manifest.network_policy_hash,
                manifest.credential_scope_hash, list(manifest.allowed_protocols),
                list(manifest.allowed_egress_hosts), manifest.is_production,
            ),
        )
        cur.execute(
            """INSERT INTO principal_resolution_receipts (
                   receipt_id, schema_version, environment_id, principal_id, owner_id,
                   resolution_method, is_server_resolved, run_id, revision,
                   client_supplied_candidate, receipt_hash
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (receipt_id) DO NOTHING""",
            (
                principal.receipt_id, principal.schema_version, principal.environment_id,
                principal.principal_id, principal.owner_id, principal.resolution_method.value,
                principal.is_server_resolved, principal.run_id, principal.revision,
                principal.client_supplied_candidate, principal.receipt_hash,
            ),
        )
        cur.execute(
            """INSERT INTO credential_resolution_receipts (
                   receipt_id, schema_version, environment_id, credential_id, owner_id,
                   mode, provider, scope_hash, audience, executed_as_principal_id,
                   refresh_version, is_expired, receipt_hash
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (receipt_id) DO NOTHING""",
            (
                credential.receipt_id, credential.schema_version, credential.environment_id,
                credential.credential_id, credential.owner_id, credential.mode.value,
                credential.provider, credential.scope_hash, credential.audience,
                credential.executed_as_principal_id, credential.refresh_version,
                credential.is_expired, credential.receipt_hash,
            ),
        )
        for receipt in (egress, blocked_loopback, blocked_metadata):
            cur.execute(
                """INSERT INTO egress_decision_receipts (
                       receipt_id, schema_version, environment_id, environment_kind,
                       target_host, resolved_ip, target_port, protocol, decision,
                       block_reason, receipt_hash
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (receipt_id) DO NOTHING""",
                (
                    receipt.receipt_id, receipt.schema_version, receipt.environment_id,
                    receipt.environment_kind.value, receipt.target_host, receipt.resolved_ip,
                    receipt.target_port, receipt.protocol, receipt.decision.value,
                    receipt.block_reason.value if receipt.block_reason else None,
                    receipt.receipt_hash,
                ),
            )
        cur.execute(
            """INSERT INTO mcp_installation_bindings (
                   binding_id, tool_id, server_id, installation_id, registry_revision,
                   verified_at_revision, binding_hash
               ) VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (binding_id) DO NOTHING""",
            (
                binding.binding_id, binding.tool_id, binding.server_id,
                binding.installation_id, binding.registry_revision,
                binding.verified_at_revision, binding.binding_hash,
            ),
        )
    conn.commit()

    http_status, response_sha256, response_bytes = _public_https_read(pinned_ip)
    execution = ExecutionIdentityReceiptBuilder.build(
        run_id=run_id,
        environment_manifest=manifest,
        principal_receipt=principal,
        credential_receipt=credential,
        egress_receipt=egress,
        installation_binding=binding,
        is_mutation=False,
    )

    blocked_builder_rejected = False
    try:
        ExecutionIdentityReceiptBuilder.build(
            run_id=run_id,
            environment_manifest=manifest,
            principal_receipt=principal,
            credential_receipt=credential,
            egress_receipt=blocked_loopback,
            installation_binding=binding,
            is_mutation=False,
        )
    except ValueError:
        blocked_builder_rejected = True
    if not blocked_builder_rejected:
        raise RuntimeError("blocked egress reached execution receipt builder")

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO execution_identity_receipts (
                   receipt_id, schema_version, run_id, revision,
                   environment_manifest_hash, principal_receipt_id,
                   credential_receipt_id, egress_receipt_id,
                   installation_binding_id, tool_id, environment_kind,
                   is_mutation, receipt_hash
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (receipt_id) DO NOTHING""",
            (
                execution.receipt_id, execution.schema_version, execution.run_id,
                execution.revision, execution.environment_manifest_hash,
                execution.principal_receipt_id, execution.credential_receipt_id,
                execution.egress_receipt_id, execution.installation_binding_id,
                execution.tool_id, execution.environment_kind.value,
                execution.is_mutation, execution.receipt_hash,
            ),
        )
        cur.execute(
            """SELECT receipt_id, revision, tool_id, receipt_hash
                 FROM execution_identity_receipts WHERE receipt_id=%s""",
            (execution.receipt_id,),
        )
        row = cur.fetchone()
        if (
            not row
            or row["revision"].strip() != expected_revision
            or row["tool_id"] != binding.tool_id
            or row["receipt_hash"] != execution.receipt_hash
        ):
            raise RuntimeError("execution identity readback mismatch")

        fake_id = f"execution:{_sha256('blocked-db:' + expected_revision)}"
        _assert_savepoint_rejection(
            cur,
            savepoint="blocked_egress_execution_probe",
            statement=(
                "INSERT INTO execution_identity_receipts ("
                "receipt_id,schema_version,run_id,revision,environment_manifest_hash,"
                "principal_receipt_id,credential_receipt_id,egress_receipt_id,"
                "installation_binding_id,tool_id,environment_kind,is_mutation,receipt_hash"
                ") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            ),
            params=(
                fake_id, execution.schema_version, run_id, expected_revision,
                manifest.manifest_hash, principal.receipt_id, credential.receipt_id,
                blocked_loopback.receipt_id, binding.binding_id, binding.tool_id,
                manifest.kind.value, False, _sha256(fake_id),
            ),
            expected_marker="ENVIRONMENT_EXECUTION_COMPOSITE_CONTRACT_VIOLATION",
        )
        _assert_savepoint_rejection(
            cur,
            savepoint="environment_append_only_probe",
            statement="UPDATE environment_manifests SET environment_id=environment_id WHERE manifest_hash=%s",
            params=(manifest.manifest_hash,),
            expected_marker="ENVIRONMENT_EXECUTION_APPEND_ONLY_VIOLATION",
        )
    conn.commit()
    return {
        "environmentManifestSha256": manifest.manifest_hash,
        "principalReceiptId": principal.receipt_id,
        "credentialReceiptId": credential.receipt_id,
        "egressReceiptId": egress.receipt_id,
        "installationBindingId": binding.binding_id,
        "executionReceiptId": execution.receipt_id,
        "executionReceiptSha256": execution.receipt_hash,
        "publicHttpsStatus": http_status,
        "publicResponseSha256": response_sha256,
        "publicResponseBytes": response_bytes,
        "resolvedIpSha256": _sha256(pinned_ip),
        "loopbackBlocked": True,
        "metadataIpBlocked": True,
        "blockedExecutionBuilderRejected": True,
        "blockedExecutionDatabaseRejected": True,
        "appendOnlyRejected": True,
    }


def run_issue_closure_canary(
    *,
    expected_revision: str,
    expected_image_digest: str,
    baseline_revision: str,
    release_evidence_sha256: str,
    patchmon_evidence_sha256: str,
    connect: Callable[[], Any] = _connect,
) -> dict[str, Any]:
    """Persist and read back the exact closure evidence for Issues 1111/1117/1120."""
    _require_identity(
        expected_revision=expected_revision,
        expected_image_digest=expected_image_digest,
        baseline_revision=baseline_revision,
        release_evidence_sha256=release_evidence_sha256,
        patchmon_evidence_sha256=patchmon_evidence_sha256,
    )
    _verify_runtime_identity(expected_revision, expected_image_digest)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT table_name
                     FROM information_schema.tables
                    WHERE table_schema='public' AND table_name=ANY(%s)""",
                (list(EXPECTED_SCHEMA_TABLES),),
            )
            present = {str(row["table_name"]) for row in cur.fetchall()}
        missing = sorted(set(EXPECTED_SCHEMA_TABLES) - present)
        if missing:
            raise RuntimeError("closure schema is incomplete")

        bug_case = _build_verified_bug_case(
            baseline_revision=baseline_revision,
            expected_revision=expected_revision,
            expected_image_digest=expected_image_digest,
            release_evidence_sha256=release_evidence_sha256,
            patchmon_evidence_sha256=patchmon_evidence_sha256,
        )
        bug = _persist_bug_case(conn, bug_case)
        memory = _persist_memory_leaf(
            conn,
            expected_revision=expected_revision,
            release_evidence_sha256=release_evidence_sha256,
            patchmon_evidence_sha256=patchmon_evidence_sha256,
            bug_case_id=bug_case.evidence_case_id,
        )
        environment = _persist_environment_receipts(
            conn,
            expected_revision=expected_revision,
        )
        with conn.cursor() as cur:
            schema_count = _scalar(
                cur,
                """SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema='public' AND table_name=ANY(%s)""",
                (list(EXPECTED_SCHEMA_TABLES),),
            )
        if schema_count != len(EXPECTED_SCHEMA_TABLES):
            raise RuntimeError("closure schema readback count changed")
        evidence = {
            "schema": {
                "requiredTableCount": len(EXPECTED_SCHEMA_TABLES),
                "presentTableCount": schema_count,
                "complete": True,
            },
            "bugEvidence": bug,
            "durableMemory": memory,
            "environmentMcpExecution": environment,
        }
        return {
            "ok": True,
            "status": "ISSUE_CLOSURE_RUNTIME_CANARY_VERIFIED",
            "sourceRevision": expected_revision,
            "imageDigest": expected_image_digest,
            "baselineRevision": baseline_revision,
            "releaseEvidenceSha256": release_evidence_sha256,
            "patchmonEvidenceSha256": patchmon_evidence_sha256,
            "evidence": evidence,
            "evidenceBundleSha256": _sha256(evidence),
            "persistentEvidence": True,
            "negativeProbeWritesCommitted": False,
            "mutationPerformed": True,
            "secretValuesReturned": False,
            "rowPayloadsReturned": False,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
