"""MIHA-inspired bounded, source-grounded code hunt before repository mutation.

This is Sovereign's internal deterministic code-hunt profile, NOT the external
MIHA Core skill or the public MIHA Evidence Suite exporter. It imports no
external executor, opens no network client, does not fix code, and does not
publish the private repository to a dataset. Static findings are candidates,
not verified live defects. The existing Janitor performs the real scan.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .git_workspace import git_status_changed_files, run_git_command
from .tool_runner import run_agent_job_tool
from .workspace_policy import repo_dir_for_workspace


MIHA_SCHEMA = "sovereign.miha-code-hunt.v1"
_MAX_SCAN_FILES = 200
_MAX_FINDINGS = 20
_MAX_LEVEL_WIDTH = 5
_MAX_NEIGHBORS = 4
_MAX_DEPTH = 10
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_HEAD_RE = re.compile(r"^[a-f0-9]{40}$")


class MihaCodeHuntError(RuntimeError):
    """A required read-only code-hunt/evidence check failed before execution."""


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _source_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        raise MihaCodeHuntError("MIHA_SOURCE_PATH_INVALID")
    candidate = root / relative
    # A scanner finding must not redirect the evidence reader through a symlink.
    if ".." in Path(relative).parts or candidate.is_symlink():
        raise MihaCodeHuntError("MIHA_SOURCE_PATH_INVALID")
    target = candidate.resolve()
    if root not in target.parents or not target.is_file():
        raise MihaCodeHuntError("MIHA_SOURCE_PATH_INVALID")
    return target


def _verified_source(root: Path, raw: Mapping[str, Any]) -> dict[str, Any]:
    relative = raw.get("path")
    if not isinstance(relative, str):
        raise MihaCodeHuntError("MIHA_FINDING_PATH_MISSING")
    path = _source_path(root, relative)
    if path.stat().st_size > 512_000:
        raise MihaCodeHuntError("MIHA_SOURCE_TOO_LARGE_FOR_READBACK")
    try:
        content = path.read_text("utf-8", errors="replace")
    except OSError as exc:
        raise MihaCodeHuntError("MIHA_SOURCE_UNREADABLE") from exc
    sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if raw.get("contentSha256") != sha:
        raise MihaCodeHuntError("MIHA_SOURCE_HASH_MISMATCH")
    rule, severity, line = raw.get("ruleId"), raw.get("severity"), raw.get("line")
    if (not isinstance(rule, str) or not re.fullmatch(r"[A-Z0-9-]{2,80}", rule)
            or severity not in {"critical", "high", "medium", "low"}
            or type(line) is not int or line < 1 or line > len(content.splitlines())):
        raise MihaCodeHuntError("MIHA_FINDING_CONTRACT_INVALID")
    return {
        "id": hashlib.sha256(f"{relative}:{line}:{rule}:{sha}".encode()).hexdigest()[:24],
        "kind": "STATIC_CANDIDATE",
        "path": relative,
        "line": line,
        "ruleId": rule,
        "severity": severity,
        "contentSha256": sha,
        "depth": 1,
    }


def _mirrored_path(relative: str) -> str | None:
    canonical = "backend/agent_runtime/"
    mirror = "scripts/sovereign-backend/agent_runtime/"
    if relative.startswith(canonical):
        return mirror + relative[len(canonical):]
    if relative.startswith(mirror):
        return canonical + relative[len(mirror):]
    return None


def _verified_neighbors(root: Path, node: Mapping[str, Any], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand at most four directly evidenced neighbors, no speculative calls."""
    candidates: list[dict[str, Any]] = []
    mirror = _mirrored_path(str(node["path"]))
    if mirror:
        try:
            target = _source_path(root, mirror)
            if target.stat().st_size <= 512_000:
                digest = hashlib.sha256(target.read_text("utf-8", errors="replace").encode()).hexdigest()
                candidates.append({
                    "from": node["id"], "to": "file:" + mirror,
                    "relation": "BYTE_EQUAL_MIRROR" if digest == node["contentSha256"] else "MIRROR_DRIFT",
                    "sourcePath": mirror, "sourceSha256": digest,
                    "depth": 2,
                })
        except (OSError, MihaCodeHuntError):
            # No evidence -> no derived relationship.
            pass
    for other in findings:
        if other["id"] == node["id"]:
            continue
        if other["path"] == node["path"]:
            candidates.append({
                "from": node["id"], "to": other["id"],
                "relation": "SAME_SOURCE_FILE", "sourcePath": other["path"],
                "sourceSha256": other["contentSha256"], "depth": 2,
            })
        elif other["ruleId"] == node["ruleId"]:
            candidates.append({
                "from": node["id"], "to": other["id"],
                "relation": "SAME_STATIC_RULE", "sourcePath": other["path"],
                "sourceSha256": other["contentSha256"], "depth": 2,
            })
    return sorted(candidates, key=lambda item: (item["relation"], item["to"]))[:_MAX_NEIGHBORS]


def run_repository_miha_code_hunt(
    job: Any, *, workspace_root: Path | None, expected_head_sha: str,
) -> dict[str, Any]:
    """Return a deterministic, non-authoritative code-finding graph and receipt.

    The Git checkout is read-only provenance; this runs BEFORE the local agent
    has authority to write, test, commit, push or open a Draft PR.
    """
    root = repo_dir_for_workspace(str(job.workspace_id or job.job_id), workspace_root).resolve()
    if not root.is_dir() or not (root / ".git").is_dir():
        raise MihaCodeHuntError("MIHA_REPOSITORY_CHECKOUT_MISSING")
    if not _HEAD_RE.fullmatch(expected_head_sha):
        raise MihaCodeHuntError("MIHA_EXPECTED_REVISION_INVALID")
    observed = run_git_command(("git", "rev-parse", "HEAD"), root, 20)
    head = observed.stdout.strip().lower() if observed.returncode == 0 else ""
    if head != expected_head_sha:
        raise MihaCodeHuntError("MIHA_REPOSITORY_REVISION_MISMATCH")
    before = git_status_changed_files(str(job.workspace_id or job.job_id), workspace_root)
    if before.status != "done" or before.changed_files:
        raise MihaCodeHuntError("MIHA_REPOSITORY_NOT_CLEAN_BEFORE_SCAN")
    # Fixed read-only parameters; neither model nor frontend may set apply/confirm.
    result = run_agent_job_tool(
        job, "janitor", {
            "mode": "scan", "maxFindings": _MAX_FINDINGS, "maxFiles": _MAX_SCAN_FILES,
            "includeDocs": True, "explainWithLocalModel": False,
        }, workspace_root,
    )
    if (result.status != "done" or result.changed_files
            or result.metadata.get("mode") != "scan"
            or result.metadata.get("writeAction") is not False):
        raise MihaCodeHuntError("MIHA_READ_ONLY_SCAN_NOT_VERIFIED")
    raw_findings = result.metadata.get("findings")
    scanned = result.metadata.get("scannedFiles")
    # The provider-neutral kernel freezes tool-result arrays as tuples.
    if not isinstance(raw_findings, (list, tuple)) or type(scanned) is not int or scanned < 1:
        raise MihaCodeHuntError("MIHA_SCAN_EVIDENCE_MISSING")
    if len(raw_findings) > _MAX_FINDINGS:
        raise MihaCodeHuntError("MIHA_SCAN_FINDINGS_EXCEED_BOUND")
    confirmed = [_verified_source(root, item) for item in raw_findings]
    # One global width budget per depth; never claim an unlimited hunt.
    admitted = confirmed[:_MAX_LEVEL_WIDTH]
    backlog = confirmed[_MAX_LEVEL_WIDTH:]
    neighbors: list[dict[str, Any]] = []
    for finding in admitted:
        for candidate in _verified_neighbors(root, finding, admitted):
            if len(neighbors) >= _MAX_LEVEL_WIDTH:
                break
            if candidate not in neighbors:
                neighbors.append(candidate)
    after = git_status_changed_files(str(job.workspace_id or job.job_id), workspace_root)
    if after.status != "done" or after.changed_files or after.changed_files != before.changed_files:
        raise MihaCodeHuntError("MIHA_SCAN_CHANGED_WORKSPACE")
    observed_after = run_git_command(("git", "rev-parse", "HEAD"), root, 20)
    if observed_after.returncode != 0 or observed_after.stdout.strip().lower() != head:
        raise MihaCodeHuntError("MIHA_SCAN_REVISION_CHANGED")
    graph = {
        "schemaVersion": MIHA_SCHEMA,
        "sourceMode": "private_repository_reference_only",
        "jobId": job.job_id,
        "ownerScopeSha256": hashlib.sha256(str(job.user_id).encode()).hexdigest(),
        "repositorySha256": hashlib.sha256(str(job.repo_url).encode()).hexdigest(),
        "branch": str(job.branch),
        "missionSha256": hashlib.sha256(str(job.mission).encode()).hexdigest(),
        "expectedHeadSha": expected_head_sha,
        "observedHeadSha": head,
        "scanner": "sovereign-deterministic-janitor",
        "scanReadOnly": True,
        "scannedFiles": scanned,
        "totalStaticCandidates": len(confirmed),
        "sampleLimited": scanned >= _MAX_SCAN_FILES or len(confirmed) >= _MAX_FINDINGS,
        "maxDepth": _MAX_DEPTH,
        "maxWidthPerDepth": _MAX_LEVEL_WIDTH,
        "maxNeighborsPerFinding": _MAX_NEIGHBORS,
        "nodes": [{"id": "submission", "kind": "SOURCE_REVISION", "depth": 0, "sourceSha256": head}, *admitted],
        "edges": neighbors,
        "backlogIds": [n["id"] for n in backlog],
        "truthBoundary": "STATIC_CANDIDATES_NOT_RUNTIME_DEFECTS",
        "datasetExport": "PRIVATE_BLOCKED",
    }
    return {**graph, "receiptSha256": _hash(graph)}


def persist_repository_miha_code_hunt(conn: Any, *, job_id: str, receipt: Mapping[str, Any]) -> str:
    """Persist the actual bounded graph, then independently reread/hash-check it."""
    if receipt.get("jobId") != job_id or receipt.get("schemaVersion") != MIHA_SCHEMA:
        raise MihaCodeHuntError("MIHA_RECEIPT_SCOPE_INVALID")
    canonical = dict(receipt)
    digest = canonical.pop("receiptSha256", None)
    if not isinstance(digest, str) or not _HASH_RE.fullmatch(digest) or digest != _hash(canonical):
        raise MihaCodeHuntError("MIHA_RECEIPT_HASH_INVALID")
    with conn.cursor() as cursor:
        cursor.execute(
            """INSERT INTO sovereign_agent_events (job_id, stage, level, message, payload)
               VALUES (%s, 'miha_preexecution_receipt', 'info', %s, %s::jsonb)
               RETURNING id""",
            (job_id, "Read-only MIHA code-hunt receipt; static findings are non-authoritative.", _canonical(dict(receipt))),
        )
        row = cursor.fetchone()
        if not row or row.get("id") is None:
            raise MihaCodeHuntError("MIHA_RECEIPT_INSERT_UNVERIFIED")
        receipt_id = row["id"]
    conn.commit()
    with conn.cursor() as cursor:
        cursor.execute(
            """SELECT payload FROM sovereign_agent_events
               WHERE id = %s AND job_id = %s AND stage = 'miha_preexecution_receipt'""",
            (receipt_id, job_id),
        )
        stored = cursor.fetchone()
    payload = stored.get("payload") if isinstance(stored, Mapping) else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise MihaCodeHuntError("MIHA_RECEIPT_READBACK_INVALID") from exc
    if (not isinstance(payload, dict) or payload != dict(receipt)
            or _hash({k: v for k, v in payload.items() if k != "receiptSha256"}) != digest):
        raise MihaCodeHuntError("MIHA_RECEIPT_READBACK_MISMATCH")
    return digest
