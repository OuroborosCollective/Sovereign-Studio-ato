from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any


COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

_BACKEND_CANARY_SCRIPT = r'''
from __future__ import annotations

import hashlib
import json
import sys

from agent_runtime.issue_closure_runtime import run_issue_closure_canary

expected_revision, expected_digest, baseline_revision, release_sha, patchmon_sha = sys.argv[1:6]
try:
    payload = run_issue_closure_canary(
        expected_revision=expected_revision,
        expected_image_digest=expected_digest,
        baseline_revision=baseline_revision,
        release_evidence_sha256=release_sha,
        patchmon_evidence_sha256=patchmon_sha,
    )
except Exception as exc:
    payload = {
        "ok": False,
        "status": "ISSUE_CLOSURE_RUNTIME_CANARY_FAILED",
        "sourceRevision": expected_revision,
        "imageDigest": expected_digest,
        "failure": {
            "type": type(exc).__name__,
            "messageSha256": hashlib.sha256(
                str(exc).encode("utf-8", errors="replace")
            ).hexdigest(),
        },
        "mutationPerformed": False,
        "secretValuesReturned": False,
        "rowPayloadsReturned": False,
    }
print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
raise SystemExit(0 if payload.get("ok") is True else 1)
'''


class IssueClosureCanaryRuntime:
    def __init__(self) -> None:
        self.container = os.getenv("SOVEREIGN_BACKEND_CONTAINER", "sovereign-backend").strip()

    def live_canary(
        self,
        *,
        expected_revision: str,
        expected_image_digest: str,
        baseline_revision: str,
        release_evidence_sha256: str,
        patchmon_evidence_sha256: str,
        owner_approved: bool,
    ) -> dict[str, Any]:
        revision = str(expected_revision or "").strip().lower()
        digest = str(expected_image_digest or "").strip().lower()
        baseline = str(baseline_revision or "").strip().lower()
        release_sha = str(release_evidence_sha256 or "").strip().lower()
        patchmon_sha = str(patchmon_evidence_sha256 or "").strip().lower()
        if not owner_approved:
            raise ValueError("owner_approved=true is required for persistent closure evidence")
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("expected_revision muss ein vollständiger Commit-SHA sein")
        if not IMAGE_DIGEST_RE.fullmatch(digest):
            raise ValueError("expected_image_digest muss ein vollständiger sha256-Digest sein")
        if not COMMIT_SHA_RE.fullmatch(baseline):
            raise ValueError("baseline_revision muss ein vollständiger Commit-SHA sein")
        if not SHA256_RE.fullmatch(release_sha):
            raise ValueError("release_evidence_sha256 muss ein vollständiger SHA-256 sein")
        if not SHA256_RE.fullmatch(patchmon_sha):
            raise ValueError("patchmon_evidence_sha256 muss ein vollständiger SHA-256 sein")
        if not CONTAINER_RE.fullmatch(self.container):
            raise ValueError("Backend-Containername ist ungültig")

        completed = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                self.container,
                "python3",
                "-",
                revision,
                digest,
                baseline,
                release_sha,
                patchmon_sha,
            ],
            input=_BACKEND_CANARY_SCRIPT,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get(
                    "PATH",
                    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ),
            },
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        payload: dict[str, Any] = {}
        if lines:
            try:
                candidate = json.loads(lines[-1])
                if isinstance(candidate, dict):
                    payload = candidate
            except json.JSONDecodeError:
                payload = {}

        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
        schema = evidence.get("schema") if isinstance(evidence.get("schema"), dict) else {}
        bug = evidence.get("bugEvidence") if isinstance(evidence.get("bugEvidence"), dict) else {}
        memory = evidence.get("durableMemory") if isinstance(evidence.get("durableMemory"), dict) else {}
        environment = (
            evidence.get("environmentMcpExecution")
            if isinstance(evidence.get("environmentMcpExecution"), dict)
            else {}
        )
        verified = bool(
            completed.returncode == 0
            and payload.get("ok") is True
            and payload.get("status") == "ISSUE_CLOSURE_RUNTIME_CANARY_VERIFIED"
            and payload.get("sourceRevision") == revision
            and payload.get("imageDigest") == digest
            and payload.get("baselineRevision") == baseline
            and payload.get("releaseEvidenceSha256") == release_sha
            and payload.get("patchmonEvidenceSha256") == patchmon_sha
            and SHA256_RE.fullmatch(str(payload.get("evidenceBundleSha256") or ""))
            and schema.get("complete") is True
            and schema.get("requiredTableCount") == 11
            and schema.get("presentTableCount") == 11
            and bug.get("status") == "verified"
            and bug.get("appendOnlyRejected") is True
            and memory.get("evidenceClass") == "verified"
            and memory.get("crossScopeCandidateExcluded") is True
            and memory.get("appendOnlyRejected") is True
            and environment.get("publicHttpsStatus") == 200
            and environment.get("loopbackBlocked") is True
            and environment.get("metadataIpBlocked") is True
            and environment.get("blockedExecutionBuilderRejected") is True
            and environment.get("blockedExecutionDatabaseRejected") is True
            and environment.get("appendOnlyRejected") is True
            and payload.get("persistentEvidence") is True
            and payload.get("negativeProbeWritesCommitted") is False
            and payload.get("secretValuesReturned") is False
            and payload.get("rowPayloadsReturned") is False
        )
        if verified:
            return payload
        return {
            "ok": False,
            "status": "ISSUE_CLOSURE_RUNTIME_CANARY_FAILED",
            "failureFamily": "ISSUE_CLOSURE_RUNTIME_CANARY_FAILED",
            "blocker": "Persistenz-, Scope-, Egress-, Append-only- oder Runtime-Evidence ist unvollständig",
            "sourceRevision": revision,
            "imageDigest": digest,
            "readback": payload,
            "exitCode": completed.returncode,
            "stderrType": "present" if completed.stderr.strip() else "empty",
            "secretValuesReturned": False,
            "rowPayloadsReturned": False,
        }
