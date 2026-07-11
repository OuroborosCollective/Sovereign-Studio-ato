"""Pattern Learning Gateway for Sovereign Agent Runtime.

The gateway turns validated agent outcomes into local pattern candidates. It does
not write to Remote Memory directly. Remote/shared memory may only ingest payloads
that passed this gateway.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import uuid
from typing import Any, Literal

from .contracts import normalize_agent_paths, sanitize_agent_text
from .evidence_gate import EvidenceGateInput, evaluate_agent_evidence
from .job_store import StoredSovereignAgentJob

PatternDecision = Literal["accepted", "blocked"]
PatternKind = Literal["solution", "blocker"]

_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{10,}", re.IGNORECASE),
    re.compile(r"sk-proj-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9_-]{10,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
    re.compile(r"(?:token|password|secret|api[_-]?key)\s*[=:]\s*[^\s\n]+", re.IGNORECASE),
)


@dataclass(frozen=True)
class PatternLearningInput:
    job_id: str
    source: str
    mission: str
    changed_files: tuple[str, ...] = ()
    diff_summary: str | None = None
    test_summary: str | None = None
    blocker: str | None = None
    evidence_passed: bool = False
    can_learn_pattern: bool = False
    draft_pr_ready: bool = False


@dataclass(frozen=True)
class PatternLearningResult:
    allowed: bool
    decision: PatternDecision
    kind: PatternKind | None
    summary: str
    payload: dict[str, Any]
    blockers: tuple[str, ...] = ()
    predictive_signal: str = "agent_pattern_learning_blocked"
    remote_memory_allowed: bool = False


def _contains_secret(*values: str | None) -> bool:
    text = "\n".join(value or "" for value in values)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def _safe_payload(input_value: PatternLearningInput, kind: PatternKind | None) -> dict[str, Any]:
    return {
        "jobId": sanitize_agent_text(input_value.job_id, 120),
        "source": sanitize_agent_text(input_value.source, 80),
        "kind": kind,
        "mission": sanitize_agent_text(input_value.mission, 600),
        "changedFiles": list(normalize_agent_paths(input_value.changed_files))[:50],
        "diffSummary": sanitize_agent_text(input_value.diff_summary or "", 2000),
        "testSummary": sanitize_agent_text(input_value.test_summary or "", 2000),
        "blocker": sanitize_agent_text(input_value.blocker or "", 1000),
        "draftPrReady": input_value.draft_pr_ready,
    }


def pattern_input_from_job(job: StoredSovereignAgentJob, *, source: str = "agent-runtime") -> PatternLearningInput:
    evidence = evaluate_agent_evidence(EvidenceGateInput(
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        blocker=job.blocker,
        tool_status="done" if job.status in ("running", "validating", "completed") else job.status,
    ))
    return PatternLearningInput(
        job_id=job.job_id,
        source=source,
        mission=job.mission,
        changed_files=job.changed_files,
        diff_summary=job.diff_summary,
        test_summary=job.test_summary,
        blocker=job.blocker,
        evidence_passed=evidence.passed,
        can_learn_pattern=evidence.can_learn_pattern,
        draft_pr_ready=(getattr(job, "pr_state", None) == "ready") or bool(getattr(job, "draft_pr_preparation", None)),
    )


def evaluate_pattern_learning(input_value: PatternLearningInput) -> PatternLearningResult:
    blockers: list[str] = []
    if _contains_secret(
        input_value.mission,
        input_value.diff_summary,
        input_value.test_summary,
        input_value.blocker,
        "\n".join(input_value.changed_files),
    ):
        blockers.append("pattern payload contains secret-like material")

    has_solution_evidence = bool(input_value.evidence_passed and input_value.can_learn_pattern and input_value.changed_files and input_value.diff_summary and input_value.test_summary)
    has_blocker_evidence = bool(input_value.blocker and len(input_value.blocker.strip()) >= 8)

    if has_solution_evidence and not blockers:
        payload = _safe_payload(input_value, "solution")
        return PatternLearningResult(
            allowed=True,
            decision="accepted",
            kind="solution",
            summary="Validated solution pattern candidate accepted.",
            payload=payload,
            predictive_signal="agent_pattern_solution_ready",
            remote_memory_allowed=True,
        )

    if has_blocker_evidence and not blockers:
        payload = _safe_payload(input_value, "blocker")
        return PatternLearningResult(
            allowed=True,
            decision="accepted",
            kind="blocker",
            summary="Validated blocker pattern candidate accepted.",
            payload=payload,
            predictive_signal="agent_pattern_blocker_ready",
            remote_memory_allowed=True,
        )

    if not has_solution_evidence and not has_blocker_evidence:
        blockers.append("no validated solution or blocker evidence for pattern learning")

    return PatternLearningResult(
        allowed=False,
        decision="blocked",
        kind=None,
        summary="Pattern learning blocked.",
        payload=_safe_payload(input_value, None),
        blockers=tuple(dict.fromkeys(blockers)),
        predictive_signal="agent_pattern_learning_blocked",
        remote_memory_allowed=False,
    )


def pattern_learning_signal(result: PatternLearningResult) -> dict[str, Any]:
    return {
        "allowed": result.allowed,
        "decision": result.decision,
        "kind": result.kind,
        "summary": result.summary,
        "payload": result.payload,
        "blockers": list(result.blockers),
        "remoteMemoryAllowed": result.remote_memory_allowed,
        "signal": result.predictive_signal,
    }


def persist_pattern_learning_candidate(conn: Any, *, user_id: str, result: PatternLearningResult) -> str:
    """Persist a pattern gateway decision locally.

    This is a local runtime record only. It is not a Remote Memory write.
    """
    candidate_id = f"pattern-{uuid.uuid4().hex}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sovereign_agent_pattern_candidates (
                candidate_id,
                user_id,
                job_id,
                decision,
                kind,
                summary,
                payload,
                remote_memory_allowed,
                predictive_signal
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                candidate_id,
                user_id,
                result.payload.get("jobId"),
                result.decision,
                result.kind,
                sanitize_agent_text(result.summary, 600),
                json.dumps(result.payload, ensure_ascii=False),
                result.remote_memory_allowed,
                result.predictive_signal,
            ),
        )
    conn.commit()
    return candidate_id
