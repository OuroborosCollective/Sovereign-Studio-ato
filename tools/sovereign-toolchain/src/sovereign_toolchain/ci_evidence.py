from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence


CI_EVIDENCE_SCHEMA_VERSION = "sovereign.ci-evidence-receipt.v1"
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+\S{8,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN [A-Z ]+ KEY-----)"
)
_ALLOWED_STATUSES = {
    "queued",
    "in_progress",
    "completed",
    "waiting",
    "requested",
    "pending",
}
_ALLOWED_CONCLUSIONS = {
    "success",
    "failure",
    "neutral",
    "cancelled",
    "skipped",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
}
_FAILURE_CONCLUSIONS = {
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "stale",
    "startup_failure",
}


class CIEvidenceError(ValueError):
    """Raised when an external CI observation violates the evidence contract."""


def _safe_text(value: Any, label: str, *, max_length: int = 240) -> str:
    text = str(value or "").strip()
    if not text:
        raise CIEvidenceError(f"{label} must not be empty")
    if len(text) > max_length:
        raise CIEvidenceError(f"{label} exceeds {max_length} characters")
    if _SECRET_VALUE.search(text):
        raise CIEvidenceError(f"secret-shaped value is forbidden in {label}")
    return text


def _sha40(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA40.fullmatch(normalized):
        raise CIEvidenceError(f"{label} must be a SHA-40")
    return normalized


def _sha64(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _SHA64.fullmatch(normalized):
        raise CIEvidenceError(f"{label} must be a SHA-256")
    return normalized


def _image_digest(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _IMAGE_DIGEST.fullmatch(normalized):
        raise CIEvidenceError(f"{label} must be an immutable sha256 image digest")
    return normalized


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise CIEvidenceError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CIEvidenceError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise CIEvidenceError(f"{label} must be a positive integer")
    return parsed


def _status(value: Any, label: str) -> str:
    normalized = _safe_text(value, label, max_length=40).lower()
    if normalized not in _ALLOWED_STATUSES:
        raise CIEvidenceError(f"unsupported {label}: {normalized}")
    return normalized


def _conclusion(value: Any, label: str) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = _safe_text(value, label, max_length=40).lower()
    if normalized not in _ALLOWED_CONCLUSIONS:
        raise CIEvidenceError(f"unsupported {label}: {normalized}")
    return normalized


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def _normalize_steps(raw_steps: Any, *, job_id: int) -> list[dict[str, Any]]:
    if raw_steps is None:
        return []
    if not isinstance(raw_steps, Sequence) or isinstance(raw_steps, (str, bytes, bytearray)):
        raise CIEvidenceError(f"job {job_id} steps must be a list")
    if len(raw_steps) > 500:
        raise CIEvidenceError(f"job {job_id} exceeds the step bound")
    steps: list[dict[str, Any]] = []
    for raw in raw_steps:
        if not isinstance(raw, Mapping):
            raise CIEvidenceError(f"job {job_id} step must be an object")
        number = _positive_int(raw.get("number"), f"job {job_id} step number")
        steps.append(
            {
                "number": number,
                "name": _safe_text(raw.get("name"), f"job {job_id} step {number} name"),
                "status": _status(raw.get("status"), f"job {job_id} step {number} status"),
                "conclusion": _conclusion(raw.get("conclusion"), f"job {job_id} step {number} conclusion"),
            }
        )
    steps.sort(key=lambda step: (step["number"], step["name"]))
    return steps


def _normalize_jobs(raw_jobs: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_jobs, Sequence) or isinstance(raw_jobs, (str, bytes, bytearray)):
        raise CIEvidenceError("jobs must be a list")
    if len(raw_jobs) > 250:
        raise CIEvidenceError("jobs exceed the observation bound")
    jobs: list[dict[str, Any]] = []
    for raw in raw_jobs:
        if not isinstance(raw, Mapping):
            raise CIEvidenceError("job must be an object")
        job_id = _positive_int(raw.get("id"), "job id")
        jobs.append(
            {
                "id": job_id,
                "name": _safe_text(raw.get("name"), f"job {job_id} name"),
                "status": _status(raw.get("status"), f"job {job_id} status"),
                "conclusion": _conclusion(raw.get("conclusion"), f"job {job_id} conclusion"),
                "steps": _normalize_steps(raw.get("steps", []), job_id=job_id),
            }
        )
    jobs.sort(key=lambda job: (job["id"], job["name"]))
    return jobs


def _first_failure(jobs: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for job in jobs:
        for step in job["steps"]:
            if step["conclusion"] in _FAILURE_CONCLUSIONS:
                return {
                    "jobId": job["id"],
                    "jobName": job["name"],
                    "stepNumber": step["number"],
                    "stepName": step["name"],
                    "conclusion": step["conclusion"],
                }
        if job["conclusion"] in _FAILURE_CONCLUSIONS:
            return {
                "jobId": job["id"],
                "jobName": job["name"],
                "stepNumber": None,
                "stepName": None,
                "conclusion": job["conclusion"],
            }
    return None


def build_ci_evidence_receipt(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one GitHub Actions observation into deterministic, non-authoritative evidence.

    The receipt deliberately contains no wall-clock time and cannot claim runtime truth. n8n may
    retain ``stateFingerprint`` solely as a delivery cursor. Sovereign must perform an independent
    repository/runtime readback before any external effect can transition to VERIFIED.
    """

    if not isinstance(observation, Mapping):
        raise CIEvidenceError("observation must be an object")
    repository = _safe_text(observation.get("repository"), "repository", max_length=200)
    if not _REPOSITORY.fullmatch(repository):
        raise CIEvidenceError("repository must use owner/name form")
    run_id = _positive_int(observation.get("run_id"), "run_id")
    head_sha = _sha40(observation.get("head_sha"), "head_sha")
    expected_head_raw = observation.get("expected_head_sha")
    expected_head_sha = _sha40(expected_head_raw, "expected_head_sha") if expected_head_raw else None
    status = _status(observation.get("status"), "workflow status")
    conclusion = _conclusion(observation.get("conclusion"), "workflow conclusion")
    if status == "completed" and conclusion is None:
        raise CIEvidenceError("completed workflow requires a conclusion")
    if status != "completed" and conclusion is not None:
        raise CIEvidenceError("non-completed workflow must not carry a conclusion")
    jobs = _normalize_jobs(observation.get("jobs", []))

    normalized_observation = {
        "repository": repository,
        "runId": run_id,
        "headSha": head_sha,
        "expectedHeadSha": expected_head_sha,
        "status": status,
        "conclusion": conclusion,
        "jobs": jobs,
    }
    state_fingerprint = _canonical_sha256(normalized_observation)
    previous_raw = observation.get("previous_fingerprint")
    previous_fingerprint = _sha64(previous_raw, "previous_fingerprint") if previous_raw else None
    changed = previous_fingerprint != state_fingerprint
    revision_matches = expected_head_sha is None or expected_head_sha == head_sha

    if not revision_matches:
        verdict = "REVISION_DRIFT"
    elif status != "completed":
        verdict = "IN_PROGRESS"
    elif conclusion == "success":
        verdict = "SUCCESS"
    else:
        verdict = "COMPLETED_NON_SUCCESS"

    first_failure = _first_failure(jobs)
    should_notify = bool(changed and (status == "completed" or not revision_matches))
    body = {
        "schemaVersion": CI_EVIDENCE_SCHEMA_VERSION,
        "authority": "OBSERVATION_ONLY",
        "source": "sovereign-toolchain",
        "observationTransport": "n8n",
        "repository": repository,
        "runId": run_id,
        "headSha": head_sha,
        "expectedHeadSha": expected_head_sha,
        "revisionMatches": revision_matches,
        "status": status,
        "conclusion": conclusion,
        "jobs": jobs,
        "firstFailure": first_failure,
        "verdict": verdict,
        "stateFingerprint": state_fingerprint,
        "previousFingerprint": previous_fingerprint,
        "stateChanged": changed,
        "shouldNotify": should_notify,
        "requiresIndependentReadback": True,
    }
    return {**body, "receiptSha256": _canonical_sha256(body)}


def build_revision_guardian_receipt(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Compare independently supplied revision/runtime identities without promoting them to truth."""

    if not isinstance(observation, Mapping):
        raise CIEvidenceError("observation must be an object")
    repository = _safe_text(observation.get("repository"), "repository", max_length=200)
    if not _REPOSITORY.fullmatch(repository):
        raise CIEvidenceError("repository must use owner/name form")
    expected_revision = _sha40(observation.get("expected_revision"), "expected_revision")
    revisions = {
        "git": _sha40(observation.get("git_revision"), "git_revision"),
        "build": _sha40(observation.get("build_revision"), "build_revision"),
        "deploy": _sha40(observation.get("deploy_revision"), "deploy_revision"),
        "health": _sha40(observation.get("health_revision"), "health_revision"),
    }
    expected_image_digest = _image_digest(observation.get("expected_image_digest"), "expected_image_digest")
    image_digest = _image_digest(observation.get("image_digest"), "image_digest")
    health_status = _safe_text(observation.get("health_status"), "health_status", max_length=40).lower()
    schema_readback = _safe_text(observation.get("schema_readback"), "schema_readback", max_length=80).upper()

    revision_matches = {name: value == expected_revision for name, value in revisions.items()}
    image_matches = image_digest == expected_image_digest
    health_ok = health_status in {"ok", "healthy", "ready"}
    schema_matches = schema_readback == "PRESENT_SCHEMA_MATCH"
    drift = [f"{name.upper()}_REVISION_DRIFT" for name, matches in revision_matches.items() if not matches]
    if not image_matches:
        drift.append("IMAGE_DIGEST_DRIFT")
    if not health_ok:
        drift.append("HEALTH_NOT_OK")
    if not schema_matches:
        drift.append("SCHEMA_NOT_MATCHED")

    normalized_observation = {
        "repository": repository,
        "expectedRevision": expected_revision,
        "revisions": revisions,
        "expectedImageDigest": expected_image_digest,
        "imageDigest": image_digest,
        "healthStatus": health_status,
        "schemaReadback": schema_readback,
    }
    state_fingerprint = _canonical_sha256(normalized_observation)
    previous_raw = observation.get("previous_fingerprint")
    previous_fingerprint = _sha64(previous_raw, "previous_fingerprint") if previous_raw else None
    changed = previous_fingerprint != state_fingerprint
    verdict = "PASS" if not drift else "DRIFT"
    body = {
        "schemaVersion": "sovereign.revision-guardian-observation.v1",
        "authority": "OBSERVATION_ONLY",
        "source": "sovereign-toolchain",
        "observationTransport": "n8n",
        **normalized_observation,
        "revisionMatches": revision_matches,
        "imageMatches": image_matches,
        "healthOk": health_ok,
        "schemaMatches": schema_matches,
        "drift": drift,
        "verdict": verdict,
        "stateFingerprint": state_fingerprint,
        "previousFingerprint": previous_fingerprint,
        "stateChanged": changed,
        "shouldNotify": changed,
        "requiresIndependentReadback": True,
    }
    return {**body, "receiptSha256": _canonical_sha256(body)}


__all__ = [
    "CI_EVIDENCE_SCHEMA_VERSION",
    "CIEvidenceError",
    "build_ci_evidence_receipt",
    "build_revision_guardian_receipt",
]
