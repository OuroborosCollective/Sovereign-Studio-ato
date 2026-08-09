from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Final

from llm_boundary_ledger import atomic_write_bytes, load_ledger, reconcile_ledger


SCHEMA_VERSION: Final[str] = "sovereign.workflow-failure-evidence.v1"
DEFAULT_LEDGER_RELATIVE: Final[str] = "config/architecture/llm-tool-boundary-review-ledger.json"
MAX_ARCHIVE_BYTES: Final[int] = 8_000_000
MAX_TEXT_BYTES: Final[int] = 6_000_000
MAX_ARCHIVE_MEMBERS: Final[int] = 100
_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({".log", ".txt", ".xml", ".json"})
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CANDIDATE_RE = re.compile(r"llm-boundary:[0-9a-f]{24}")
_JUNIT_SUITE_RE = re.compile(r"<testsuite\b([^>]*)>", re.I)
_XML_ATTR_RE = re.compile(r"\b(tests|failures|errors|skipped|disabled)\s*=\s*['\"](\d+)['\"]", re.I)
_JUNIT_FAILURE_RE = re.compile(
    r"<testcase\b([^>]*)>.*?<(?:failure|error)\b",
    re.I | re.S,
)
_JUNIT_NAME_RE = re.compile(r"\b(?:classname|name)\s*=\s*['\"]([^'\"]+)['\"]", re.I)
_SECRET_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.I),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _redact(value: str) -> str:
    text = _ANSI_RE.sub("", value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def bounded_text_sources_from_archive(
    payload: bytes,
    *,
    artifact_name: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Extract bounded text evidence without materializing the archive or returning raw bytes."""

    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError("Workflow artifact exceeds the bounded archive limit")
    sources: list[dict[str, str]] = []
    total_text_bytes = 0
    stream = io.BytesIO(payload)
    if zipfile.is_zipfile(stream):
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ARCHIVE_MEMBERS:
                raise ValueError("Workflow artifact contains too many members")
            seen: set[str] = set()
            for info in infos:
                member = PurePosixPath(info.filename)
                if info.is_dir():
                    continue
                if member.is_absolute() or ".." in member.parts or not member.parts:
                    raise ValueError("Workflow artifact contains an unsafe path")
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted workflow artifacts are not supported")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError("Workflow artifact symlinks are forbidden")
                if info.file_size < 0 or info.file_size > MAX_TEXT_BYTES - total_text_bytes:
                    raise ValueError("Workflow artifact text exceeds the bounded limit")
                name = member.as_posix()
                if name in seen:
                    raise ValueError("Workflow artifact contains duplicate paths")
                seen.add(name)
                if member.suffix.casefold() not in _TEXT_SUFFIXES:
                    continue
                raw = archive.read(info)
                total_text_bytes += len(raw)
                if total_text_bytes > MAX_TEXT_BYTES:
                    raise ValueError("Workflow artifact text exceeds the bounded limit")
                sources.append({"name": name, "text": _redact(raw.decode("utf-8", "replace"))})
    else:
        total_text_bytes = len(payload)
        if total_text_bytes > MAX_TEXT_BYTES:
            raise ValueError("Workflow log exceeds the bounded text limit")
        sources.append({"name": artifact_name, "text": _redact(payload.decode("utf-8", "replace"))})
    return sources, {
        "name": artifact_name,
        "archiveSha256": _sha256(payload),
        "archiveBytes": len(payload),
        "textMemberCount": len(sources),
        "textBytes": total_text_bytes,
    }


def _last_pytest_count(text: str, label: str) -> int:
    values = re.findall(rf"(?<![A-Za-z0-9_])(\d+)\s+{re.escape(label)}\b", text, re.I)
    return int(values[-1]) if values else 0


def _test_counts(text: str) -> tuple[int, int, int]:
    pytest_counts = tuple(_last_pytest_count(text, label) for label in ("failed", "passed", "skipped"))
    if any(pytest_counts):
        return pytest_counts
    failed = passed = skipped = 0
    for suite_match in _JUNIT_SUITE_RE.finditer(text):
        attrs = {
            key.casefold(): int(value)
            for key, value in _XML_ATTR_RE.findall(suite_match.group(1))
        }
        tests = attrs.get("tests", 0)
        suite_failed = attrs.get("failures", 0) + attrs.get("errors", 0)
        suite_skipped = attrs.get("skipped", 0) + attrs.get("disabled", 0)
        failed += suite_failed
        skipped += suite_skipped
        passed += max(0, tests - suite_failed - suite_skipped)
    return failed, passed, skipped


def _causal_test(text: str) -> str | None:
    pytest_failure = re.search(r"(?m)^FAILED\s+([^\s]+)", text)
    if pytest_failure:
        return pytest_failure.group(1)
    junit_failure = _JUNIT_FAILURE_RE.search(text)
    if not junit_failure:
        return None
    names = _JUNIT_NAME_RE.findall(junit_failure.group(1))
    return "::".join(names) if names else "junit:testcase"


def _failure_family(text: str) -> str:
    normalized = text.casefold()
    if any(
        marker in normalized
        for marker in (
            "missing_candidate:",
            "stale_or_removed_candidate:",
            "binding_drift:",
            "raw_candidate_count_drift",
            "canonical_candidate_count_drift",
            "test_current_review_ledger_is_complete_and_fresh",
        )
    ):
        return "LLM_BOUNDARY_LEDGER_DRIFT"
    if any(marker in normalized for marker in ("continuity_ledger_", "continuity_completion_", "continuity-ledger")):
        return "CONTINUITY_DRIFT"
    if any(marker in normalized for marker in ("mirror drift", "mirror_drift", "mismatchcount")):
        return "MIRROR_DRIFT"
    if any(marker in normalized for marker in ("service unavailable", "connection refused", "rate limit", "timed out")):
        return "DEPENDENCY_OUTAGE"
    if any(marker in normalized for marker in ("runner lost communication", "hosted runner", "job was cancelled")):
        return "RUNNER_PROBLEM"
    return "CODE_FAILURE"


def extract_workflow_failure_evidence(
    *,
    workflow_run: dict[str, Any],
    jobs: list[dict[str, Any]],
    sources: list[dict[str, str]],
    artifact_receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    combined = "\n".join(str(item.get("text") or "") for item in sources)
    family = _failure_family(combined)
    failed_jobs = [
        item for item in jobs if str(item.get("conclusion") or "").casefold() not in {"", "success", "skipped"}
    ]
    failed_steps: list[dict[str, Any]] = []
    for job in failed_jobs:
        for step in job.get("steps", []) if isinstance(job.get("steps"), list) else []:
            if not isinstance(step, dict):
                continue
            if str(step.get("conclusion") or "").casefold() in {"", "success", "skipped"}:
                continue
            failed_steps.append(
                {
                    "jobId": int(job.get("id") or 0),
                    "job": _redact(str(job.get("name") or "")),
                    "step": _redact(str(step.get("name") or "")),
                    "conclusion": str(step.get("conclusion") or ""),
                }
            )
    causal_candidate_match = _CANDIDATE_RE.search(combined)
    causal_candidate = causal_candidate_match.group(0) if causal_candidate_match else None
    failed_count, passed_count, skipped_count = _test_counts(combined)
    repair_surface = {
        "LLM_BOUNDARY_LEDGER_DRIFT": DEFAULT_LEDGER_RELATIVE,
        "CONTINUITY_DRIFT": "docs/sovereign-continuity/LEDGER.jsonl",
    }.get(family)
    code_rollback = family in {"CODE_FAILURE"}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "ok": bool(combined and failed_jobs),
        "status": "WORKFLOW_FAILURE_EVIDENCE_EXTRACTED" if combined else "WORKFLOW_FAILURE_EVIDENCE_INCOMPLETE",
        "workflowRunId": int(workflow_run.get("id") or 0),
        "workflow": _redact(str(workflow_run.get("name") or "")),
        "headSha": str(workflow_run.get("head_sha") or "").strip().lower(),
        "runConclusion": workflow_run.get("conclusion"),
        "failedJobs": [
            {
                "id": int(item.get("id") or 0),
                "name": _redact(str(item.get("name") or "")),
                "conclusion": str(item.get("conclusion") or ""),
            }
            for item in failed_jobs
        ],
        "failedSteps": failed_steps,
        "failureFamily": family,
        "failedTests": failed_count,
        "passedTests": passed_count,
        "skippedTests": skipped_count,
        "causalTest": _causal_test(combined),
        "causalCandidate": causal_candidate,
        "repairSurface": repair_surface,
        "codeRollbackRecommended": code_rollback,
        "artifactEvidence": [
            {
                key: _redact(value) if isinstance(value, str) else value
                for key, value in receipt.items()
            }
            for receipt in artifact_receipts
        ],
        "rawLogsReturned": False,
        "mutationPerformed": False,
        "secretValuesReturned": False,
        "truthNotice": (
            "The verdict is derived from bounded job and artifact content tied to the exact workflow head; "
            "workflow or check names alone never determine the failure family."
        ),
    }


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return completed.stdout.strip()


def _git_optional(repo: Path, *args: str) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def _cumulative_changed_paths(repo: Path, source_revision: str) -> tuple[str, ...]:
    """Bind already committed PR paths as well as the dirty reconciliation patch."""

    configured_base = (os.getenv("GITHUB_BASE_REF") or "").strip()
    if configured_base and (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", configured_base)
        or ".." in configured_base
        or "@{" in configured_base
    ):
        raise ValueError("GITHUB_BASE_REF is not a safe Git ref")
    base_refs = (
        [f"origin/{configured_base}", configured_base]
        if configured_base
        else []
    )
    base_refs.extend(("origin/main", "main"))
    seen: set[str] = set()
    for base_ref in base_refs:
        if base_ref in seen:
            continue
        seen.add(base_ref)
        resolved = _git_optional(repo, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
        if not resolved or not _SHA_RE.fullmatch(resolved):
            continue
        merge_base = _git_optional(repo, "merge-base", source_revision, resolved)
        if not merge_base or not _SHA_RE.fullmatch(merge_base):
            continue
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "diff",
                "--name-only",
                "--diff-filter=ACDMRTUXB",
                "-z",
                merge_base,
                source_revision,
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
        )
        if completed.returncode == 0:
            return tuple(sorted(path for path in completed.stdout.split("\0") if path))
    return ()


def append_boundary_reconciliation_continuity(
    repo: Path,
    *,
    source_revision: str,
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    if not _SHA_RE.fullmatch(source_revision):
        raise ValueError("source_revision must be a full Git SHA")
    policy_path = repo / "tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json"
    policy_raw = policy_path.read_bytes()
    policy = json.loads(policy_raw.decode("utf-8"))
    paths = policy["canonicalPaths"]
    context_path = repo / str(paths["context"])
    ledger_paths = [repo / str(paths["ledger"]), repo / str(paths["runtimeLedger"])]
    if ledger_paths[0].read_bytes() != ledger_paths[1].read_bytes():
        raise RuntimeError("CONTINUITY_LEDGER_MIRROR_DRIFT")
    status_output = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    ).stdout.rstrip("\n")
    status_paths = [line[3:].strip() for line in status_output.splitlines() if len(line) >= 4]
    ledger_relative_paths = {str(item.relative_to(repo)) for item in ledger_paths}
    changed_paths = sorted(
        (
            {
                path.split(" -> ", 1)[-1]
                for path in status_paths
            }
            | set(_cumulative_changed_paths(repo, source_revision))
        )
        - ledger_relative_paths
    )
    ledger_hash = str(reconciliation.get("ledgerSha256") or "")
    entry_id = f"continuity-boundary-ledger-reconcile-{source_revision[:12]}-{ledger_hash[:12]}"
    existing_ids = {
        str(json.loads(line).get("entryId") or "")
        for line in ledger_paths[0].read_text("utf-8").splitlines()
        if line.strip()
    }
    if entry_id in existing_ids:
        return {
            "ok": True,
            "status": "CONTINUITY_ENTRY_ALREADY_PRESENT",
            "entryId": entry_id,
            "mutationPerformed": False,
        }
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sourceRevision": source_revision,
        "mission": "Reconcile exact-head LLM/tool boundary ledger drift before the MCP full suite.",
        "summary": (
            f"Preserved {int(reconciliation.get('preservedCandidates') or 0)} reviewed candidates, "
            f"bound {len(reconciliation.get('newCandidates') or [])} new candidates, and validated "
            "the canonical ledger before any workflow rerun."
        ),
        "decisions": [
            "Existing candidate classifications and rationales remain unchanged.",
            "Mirror candidates are represented only by their canonical owner entry.",
            "No candidate requiring owner review is written or published.",
            "PatchMon remains a runtime evidence lane and does not decide the code or ledger verdict.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            f"Exact source revision: {source_revision}.",
            f"Raw/canonical candidates: {reconciliation.get('rawCandidateCount')}/{reconciliation.get('canonicalCandidateCount')}.",
            f"Validated boundary ledger SHA-256: {ledger_hash}.",
        ],
        "openItems": [
            "Publish the bounded patch on the same Draft-PR branch.",
            "Read all required GitHub checks at the exact new PR head.",
            "Read PatchMon fleet evidence separately after code and CI evidence are terminal.",
        ],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {"rawChatTranscriptStored": False, "redacted": True, "secretValuesStored": False},
        "contextSha256": _sha256(context_path.read_bytes()),
        "policySha256": _sha256(policy_raw),
        "identity": {
            "canonicalName": str(policy["identity"]["canonicalName"]),
            "spokenName": str(policy["identity"]["spokenName"]),
            "familyDesignation": str(policy["identity"]["familyDesignation"]),
        },
    }
    serialized = (json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    previous = ledger_paths[0].read_bytes()
    try:
        for path in ledger_paths:
            atomic_write_bytes(path, previous + serialized)
    except Exception:
        for path in ledger_paths:
            atomic_write_bytes(path, previous)
        raise
    if ledger_paths[0].read_bytes() != ledger_paths[1].read_bytes():
        raise RuntimeError("CONTINUITY_LEDGER_WRITE_MIRROR_DRIFT")
    return {
        "ok": True,
        "status": "CONTINUITY_ENTRY_APPENDED",
        "entryId": entry_id,
        "changedPaths": changed_paths,
        "mutationPerformed": True,
        "secretValuesReturned": False,
    }


def revision_bound_ci_repair(
    *,
    runtime: Any,
    broker: Any,
    workspace_id: str,
    pr_number: int,
    workflow_run_id: int,
    expected_pr_head_sha: str,
    owner_decisions: dict[str, dict[str, str]] | None = None,
    apply_patch: bool = False,
    publish_patch: bool = False,
    rerun_failed: bool = False,
    owner_approved: bool = False,
) -> dict[str, Any]:
    expected = str(expected_pr_head_sha or "").strip().lower()
    if not _SHA_RE.fullmatch(expected):
        raise ValueError("expected_pr_head_sha must be a full Git SHA")
    if publish_patch and not apply_patch:
        raise ValueError("publish_patch requires apply_patch")
    if (publish_patch or rerun_failed) and not owner_approved:
        return {
            "ok": False,
            "status": "OWNER_APPROVAL_REQUIRED",
            "failureFamily": "OWNER_APPROVAL_REQUIRED",
            "blocker": "External PR or workflow mutation requires current owner approval",
            "mutationPerformed": False,
        }

    repo = runtime._repo(workspace_id)
    head = _git(repo, "rev-parse", "HEAD").lower()
    dirty = _git(repo, "status", "--porcelain")
    if head != expected or dirty:
        return {
            "ok": False,
            "status": "REVISION_CONFLICT",
            "failureFamily": "REVISION_CONFLICT",
            "workspaceHeadSha": head,
            "expectedPrHeadSha": expected,
            "dirtyEntries": dirty.splitlines(),
            "mutationPerformed": False,
        }
    pr = broker.call("github_pr_status", {"pr_number": int(pr_number)}, timeout=60)
    if str(pr.get("head_sha") or "").lower() != expected:
        return {
            "ok": False,
            "status": "PR_HEAD_CHANGED",
            "failureFamily": "REVISION_CONFLICT",
            "expectedPrHeadSha": expected,
            "actualPrHeadSha": str(pr.get("head_sha") or ""),
            "mutationPerformed": False,
        }
    workspace_branch = _git(repo, "branch", "--show-current")
    pr_head_ref = str(pr.get("head_ref") or "").strip()
    if (
        not pr_head_ref
        or workspace_branch != pr_head_ref
        or workspace_branch in {"main", "master"}
    ):
        return {
            "ok": False,
            "status": "PR_BRANCH_IDENTITY_CONFLICT",
            "failureFamily": "REVISION_CONFLICT",
            "workspaceBranch": workspace_branch,
            "prHeadRef": pr_head_ref,
            "mutationPerformed": False,
        }
    failure = broker.call(
        "github_workflow_failure_evidence_extract",
        {"run_id": int(workflow_run_id), "expected_head_sha": expected},
        timeout=120,
    )
    if failure.get("failureFamily") != "LLM_BOUNDARY_LEDGER_DRIFT":
        return {
            "ok": False,
            "status": "SPECIALIZED_REPAIR_REQUIRED",
            "failureFamily": failure.get("failureFamily"),
            "failureEvidence": failure,
            "repairTool": {
                "CONTINUITY_DRIFT": "sovereign_continuity_status",
                "MIRROR_DRIFT": "repository_mirror_diff_report",
                "DEPENDENCY_OUTAGE": "runtime_dependency_health_matrix",
            }.get(str(failure.get("failureFamily") or ""), "repository_change_impact_manifest"),
            "mutationPerformed": False,
        }

    ledger_path = repo / DEFAULT_LEDGER_RELATIVE
    preview = reconcile_ledger(
        repo,
        load_ledger(ledger_path),
        owner_decisions=owner_decisions,
    )
    base_result = {
        "schemaVersion": "sovereign.revision-bound-ci-repair.v1",
        "prNumber": int(pr_number),
        "expectedPrHeadSha": expected,
        "workspaceHeadSha": head,
        "workflowRunId": int(workflow_run_id),
        "failureEvidence": failure,
        "reconciliation": preview,
    }
    if not apply_patch:
        return {
            **base_result,
            "ok": not preview["ownerDecisionCandidateIds"],
            "status": "REVISION_BOUND_REPAIR_PLAN_READY" if not preview["ownerDecisionCandidateIds"] else "OWNER_DECISION_REQUIRED",
            "mutationPerformed": False,
            "nextAction": "reinvoke_with_apply_patch_after_review",
        }
    if preview["ownerDecisionCandidateIds"]:
        return {
            **base_result,
            "ok": False,
            "status": "OWNER_DECISION_REQUIRED",
            "mutationPerformed": False,
        }

    applied = reconcile_ledger(
        repo,
        load_ledger(ledger_path),
        owner_decisions=owner_decisions,
        write_path=ledger_path,
    )
    continuity = append_boundary_reconciliation_continuity(
        repo,
        source_revision=expected,
        reconciliation=applied,
    )
    targeted = runtime.run_check(
        workspace_id,
        "pytest",
        "tools/sovereign-chatgpt-mcp/tests/test_llm_boundary_ledger.py",
    )
    if not targeted.get("ok"):
        return {
            **base_result,
            "ok": False,
            "status": "TARGETED_VALIDATION_FAILED",
            "reconciliation": applied,
            "continuity": continuity,
            "targetedCheck": targeted,
            "mutationPerformed": True,
        }
    diff_check = runtime.run_check(workspace_id, "git_diff_check")
    if not diff_check.get("ok"):
        return {
            **base_result,
            "ok": False,
            "status": "DIFF_VALIDATION_FAILED",
            "reconciliation": applied,
            "continuity": continuity,
            "targetedCheck": targeted,
            "diffCheck": diff_check,
            "mutationPerformed": True,
        }
    if not publish_patch:
        return {
            **base_result,
            "ok": True,
            "status": "REVISION_BOUND_WORKSPACE_PATCH_READY",
            "reconciliation": applied,
            "continuity": continuity,
            "targetedCheck": targeted,
            "diffCheck": diff_check,
            "mutationPerformed": True,
            "nextAction": "publish_same_pr_branch_and_read_new_exact_head",
        }

    published = runtime.create_draft_pr(
        workspace_id,
        title=str(pr.get("title") or "Reconcile boundary ledger drift"),
        body="Revision-bound boundary-ledger repair with bounded failure evidence and targeted validation.",
        commit_message="feat(ci): reconcile revision-bound boundary ledger drift",
    )
    if int(published.get("number") or 0) != int(pr_number) or str(published.get("branch") or "") != workspace_branch:
        return {
            **base_result,
            "ok": False,
            "status": "SAME_PR_PUBLICATION_NOT_CONFIRMED",
            "published": published,
            "workspaceBranch": workspace_branch,
            "mutationPerformed": True,
        }
    pr_readback = broker.call("github_pr_status", {"pr_number": int(pr_number)}, timeout=60)
    new_head = str(pr_readback.get("head_sha") or "").lower()
    if not _SHA_RE.fullmatch(new_head) or new_head == expected:
        return {
            **base_result,
            "ok": False,
            "status": "PUBLISHED_HEAD_READBACK_FAILED",
            "published": published,
            "prReadback": pr_readback,
            "mutationPerformed": True,
        }
    rerun = None
    if rerun_failed:
        rerun = broker.call("github_rerun_failed_workflows", {"pr_number": int(pr_number)}, timeout=120)
    return {
        **base_result,
        "ok": True,
        "status": "PUBLISHED_AWAITING_EXACT_HEAD_CI",
        "reconciliation": applied,
        "continuity": continuity,
        "targetedCheck": targeted,
        "diffCheck": diff_check,
        "published": published,
        "previousPrHeadSha": expected,
        "newPrHeadSha": new_head,
        "prReadback": pr_readback,
        "rerun": rerun,
        "mutationPerformed": True,
        "nextAction": "wait_for_terminal_checks_on_new_pr_head",
        "secretValuesReturned": False,
    }
