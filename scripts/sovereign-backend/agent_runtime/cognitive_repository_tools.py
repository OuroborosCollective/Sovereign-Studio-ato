"""Bounded repository tools exposed to the OpenAI Agents SDK workers.

Natural-language understanding remains in the routed model. This module owns only
capability, workspace, path, evidence and write boundaries. Every tool call runs
against the linked Sovereign Agent Job and persists sanitized runtime evidence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import importlib
import json
from pathlib import Path, PurePosixPath
import re
from threading import Lock
import uuid
from typing import Any, Final

from .cognitive_run_store import (
    create_agent_task,
    finish_agent_tool_call,
    start_agent_tool_call,
)
from .cognitive_swarm_manifest import WORKER_ROLES
from .job_store import read_agent_job
from .tool_events import append_tool_result_to_job
from .tool_runner import run_agent_job_tool
from .tools.base import ToolResult


ConnectionFactory = Callable[[], Any]

ROLE_WORK_PACKAGES: Final[dict[str, str]] = {
    "free_single_agent": "Implement one bounded coding mission in the isolated Code-Server workspace; read before writing and preserve diff plus test evidence.",
    "data_storage": "Inspect SQL, Agent Job persistence, pattern candidates and pgvector learning; accept learning only after tool and test evidence.",
    "business_core": "Inspect intent, ARE inference and evidence-gate semantics; model output must never create runtime success.",
    "endpoint_bridge": "Inspect route, job, workspace and executor handoff; prove every state transition from real tool evidence.",
    "chat_cognitive": "Inspect natural-language understanding and Agents SDK orchestration; remove local language interpretation from online execution paths.",
    "ui_accessibility": "Inspect Controller and chat surfaces; visible status must mirror persisted tasks, events, blockers and approvals.",
    "predictive_qa": "Inspect predictive signals, test gates and capability boundaries; derive follow-up failures to depth three and verify reruns.",
}

ROLE_PATH_PREFIXES: Final[dict[str, tuple[str, ...]]] = {
    "free_single_agent": ("__workspace_all__",),
    "data_storage": (
        "scripts/sovereign-backend/migrations/",
        "scripts/sovereign-backend/knowledge_library.py",
        "scripts/sovereign-backend/agent_runtime/job_store.py",
        "scripts/sovereign-backend/agent_runtime/pattern_gateway.py",
        "scripts/sovereign-backend/agent_runtime/pattern_vector_memory.py",
        "backend/agent_runtime/job_store.py",
        "backend/agent_runtime/pattern_gateway.py",
        "backend/agent_runtime/pattern_vector_memory.py",
    ),
    "business_core": (
        "scripts/sovereign-backend/are_inference.py",
        "scripts/sovereign-backend/agent_runtime/contracts.py",
        "scripts/sovereign-backend/agent_runtime/evidence_gate.py",
        "backend/agent_runtime/contracts.py",
        "backend/agent_runtime/evidence_gate.py",
    ),
    "endpoint_bridge": (
        "scripts/sovereign-backend/app.py",
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_routes.py",
        "scripts/sovereign-backend/agent_runtime/routes.py",
        "backend/agent_runtime/cognitive_swarm_routes.py",
        "backend/agent_runtime/routes.py",
    ),
    "chat_cognitive": (
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_agents.py",
        "scripts/sovereign-backend/agent_runtime/cognitive_swarm_manifest.py",
        "scripts/sovereign-backend/agent_runtime/skills/",
        "backend/agent_runtime/cognitive_swarm_agents.py",
        "backend/agent_runtime/cognitive_swarm_manifest.py",
        "backend/agent_runtime/skills/",
    ),
    "ui_accessibility": (
        "scripts/sovereign-backend/controller_board.py",
        "src/",
        "apps/",
        "packages/",
    ),
    "predictive_qa": (
        ".github/workflows/",
        "scripts/sovereign-backend/tests/",
        "backend/tests/",
        "scripts/sovereign-backend/agent_runtime/tool_events.py",
        "scripts/sovereign-backend/agent_runtime/tool_runner.py",
        "scripts/sovereign-backend/agent_runtime/tools/",
        "backend/agent_runtime/tool_events.py",
        "backend/agent_runtime/tool_runner.py",
        "backend/agent_runtime/tools/",
    ),
}

READ_REPOSITORY_TOOL_NAMES: Final[tuple[str, ...]] = (
    "read_repository_file",
    "scan_repository_family",
    "inspect_repository_status",
    "inspect_repository_diff",
    "run_repository_test",
)
WRITE_REPOSITORY_TOOL_NAMES: Final[tuple[str, ...]] = (
    "apply_exact_repository_patch",
    "write_repository_file",
)

_SECRET_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"github_pat_[A-Za-z0-9_]{16,}", re.IGNORECASE),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.IGNORECASE),
)


def _close(conn: Any) -> None:
    close = getattr(conn, "close", None)
    if callable(close):
        close()


def _safe_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or ".." in pure.parts
        or any(part in {".git", ".env", "node_modules", "__pycache__", ".pytest_cache"} for part in pure.parts)
    ):
        raise ValueError("repository path is unsafe")
    return pure.as_posix()


def _path_in_role_scope(role: str, path: str) -> bool:
    for prefix in ROLE_PATH_PREFIXES.get(role, ()):
        if prefix == "__workspace_all__":
            return True
        if prefix.endswith("/") and path.startswith(prefix):
            return True
        if path == prefix:
            return True
    return False


def _redact(text: str, limit: int = 40_000) -> str:
    bounded = str(text or "")[:limit]
    for pattern in _SECRET_VALUE_PATTERNS:
        bounded = pattern.sub("[REDACTED]", bounded)
    return bounded


def _merge_job_evidence(job: Any, result: ToolResult) -> ToolResult:
    return ToolResult(
        tool=result.tool,
        allowed=result.allowed,
        status=result.status,
        stdout=result.stdout,
        stderr=result.stderr,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
        changed_files=result.changed_files or job.changed_files,
        diff_summary=result.diff_summary or job.diff_summary,
        test_summary=result.test_summary or job.test_summary,
        blocker=result.blocker,
        exit_code=result.exit_code,
        events=result.events,
        predictive_signal=result.predictive_signal,
    )


def create_repository_swarm_tasks(
    conn: Any,
    *,
    run_id: str,
    evidence_id: str,
    write_confirmed: bool,
) -> dict[str, str]:
    """Persist dispatcher, six worker and judge tasks for one repository-backed swarm run."""

    task_ids: dict[str, str] = {}
    forbidden = (
        "persist or reveal secrets",
        "write outside the assigned role paths",
        "merge a pull request",
        "deploy to production",
        "claim success without tool, diff and test evidence",
    )
    dispatcher_id = f"task-dispatcher-{uuid.uuid4().hex}"
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=dispatcher_id,
        agent_id="dispatcher",
        specialist_role="orchestration",
        work_package="Interpret the mission plan already classified by the routed LLM and assign exactly six bounded repository work packages.",
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="CREATE_SIX_ROLE_PLAN",
        acceptance_criteria=("Exactly six worker packages are ordered.", "No repository mutation is claimed by the dispatcher."),
        forbidden_actions=forbidden,
        max_tool_calls=0,
        commit=False,
    )
    task_ids["dispatcher"] = dispatcher_id

    allowed_tools = (*READ_REPOSITORY_TOOL_NAMES, *(WRITE_REPOSITORY_TOOL_NAMES if write_confirmed else ()))
    for role in WORKER_ROLES:
        task_id = f"task-{role}-{uuid.uuid4().hex}"
        create_agent_task(
            conn,
            run_id=run_id,
            task_id=task_id,
            agent_id=role,
            specialist_role=role,
            work_package=ROLE_WORK_PACKAGES[role],
            evidence_id=evidence_id,
            status="QUEUED",
            next_action="WAIT_FOR_DISPATCHER_PLAN",
            allowed_files=ROLE_PATH_PREFIXES[role],
            allowed_tools=allowed_tools,
            acceptance_criteria=(
                "At least one real repository tool call is persisted for this role.",
                "Every finding names evidence from the linked isolated workspace.",
                "Any mutation is exact, SHA-bound and followed by status, diff and relevant test evidence.",
                "Predictive follow-up failures are derived to depth three when a finding exists.",
            ),
            forbidden_actions=forbidden,
            max_tool_calls=30,
            max_retries=2,
            commit=False,
        )
        task_ids[role] = task_id

    judge_id = f"task-judge-{uuid.uuid4().hex}"
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=judge_id,
        agent_id="judge",
        specialist_role="evidence_controller",
        work_package="Reject unsupported claims and accept readiness only after all six roles used tools and the linked job has changed-file, diff and test evidence.",
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="WAIT_FOR_SIX_WORKER_REPORTS",
        acceptance_criteria=(
            "All six role task states and tool-call records are present.",
            "The linked Agent Job passes the repository evidence gate.",
            "Learning remains pending until validated solution or blocker evidence exists.",
            "At most one Draft PR is allowed and auto-merge is disabled.",
        ),
        forbidden_actions=forbidden,
        max_tool_calls=0,
        commit=False,
    )
    task_ids["judge"] = judge_id
    conn.commit()
    return task_ids


def create_repository_single_agent_task(
    conn: Any,
    *,
    run_id: str,
    evidence_id: str,
    write_confirmed: bool,
) -> str:
    """Persist exactly one coding task for the free single-agent profile."""
    task_id = f"free-agent-work-{uuid.uuid4().hex}"
    allowed_tools = (
        *READ_REPOSITORY_TOOL_NAMES,
        *(WRITE_REPOSITORY_TOOL_NAMES if write_confirmed else ()),
    )
    create_agent_task(
        conn,
        run_id=run_id,
        task_id=task_id,
        agent_id="free_single_agent",
        specialist_role="free_single_agent",
        work_package=ROLE_WORK_PACKAGES["free_single_agent"],
        evidence_id=evidence_id,
        status="QUEUED",
        next_action="EXECUTE_SINGLE_AGENT_WORKSPACE_MISSION",
        allowed_files=("isolated_code_server_workspace",),
        allowed_tools=allowed_tools,
        acceptance_criteria=(
            "The single agent uses real workspace tools before making repository claims.",
            "Every write remains inside the isolated Agent Job repository clone.",
            "Status, diff and at least one relevant test are read after mutation.",
            "No background agent, production deploy, merge or auto-merge is started.",
        ),
        forbidden_actions=(
            "persist or reveal secrets",
            "write outside the isolated workspace",
            "start background agents",
            "merge a pull request",
            "deploy to production",
            "claim success without tool, diff and test evidence",
        ),
        max_tool_calls=40,
        max_retries=2,
        commit=True,
    )
    return task_id


def _require_function_tool() -> Callable[..., Any]:
    module = importlib.import_module("agents")
    factory = getattr(module, "function_tool", None)
    if not callable(factory):
        raise RuntimeError("OpenAI Agents SDK function_tool API is unavailable")
    return factory


@dataclass
class BoundRepositoryToolset:
    get_connection: ConnectionFactory
    user_id: str
    run_id: str
    job_id: str
    task_ids_by_agent: dict[str, str]
    workspace_root: Path | None
    write_confirmed: bool = False
    _call_counts: dict[str, int] = field(default_factory=dict)
    _mutation_counts: dict[str, int] = field(default_factory=dict)
    _consecutive_failures: dict[str, int] = field(default_factory=dict)
    _open_circuits: set[str] = field(default_factory=set)
    _lock: Lock = field(default_factory=Lock)

    def allowed_paths(self, role: str) -> tuple[str, ...]:
        if role == "free_single_agent":
            return (".",)
        return ROLE_PATH_PREFIXES.get(role, ())

    def allowed_tool_names(self, role: str) -> tuple[str, ...]:
        return (
            (*READ_REPOSITORY_TOOL_NAMES, *WRITE_REPOSITORY_TOOL_NAMES)
            if self.write_confirmed
            else READ_REPOSITORY_TOOL_NAMES
        )

    def _validate_role_path(self, role: str, path: str) -> str:
        normalized = _safe_path(path)
        if role not in ROLE_PATH_PREFIXES:
            raise ValueError("unknown repository worker role")
        if not _path_in_role_scope(role, normalized):
            raise ValueError("repository path is outside the worker role boundary")
        return normalized

    def _record_call(self, role: str, *, mutation: bool, failed: bool) -> None:
        with self._lock:
            self._call_counts[role] = self._call_counts.get(role, 0) + 1
            if mutation:
                self._mutation_counts[role] = self._mutation_counts.get(role, 0) + 1
            if failed:
                failures = self._consecutive_failures.get(role, 0) + 1
                self._consecutive_failures[role] = failures
                if failures >= 3:
                    self._open_circuits.add(role)
            else:
                self._consecutive_failures[role] = 0

    def _assert_circuit_closed(self, role: str) -> None:
        with self._lock:
            if role in self._open_circuits:
                raise RuntimeError("repository tool circuit is open after three consecutive failures")

    def _execute(self, role: str, action: str, parameters: dict[str, Any], *, mutation: bool = False) -> str:
        self._assert_circuit_closed(role)
        task_id = self.task_ids_by_agent.get(role)
        if not task_id:
            raise LookupError("repository worker task is missing")
        conn = self.get_connection()
        tool_call_id = ""
        try:
            tool_call_id = start_agent_tool_call(
                conn,
                run_id=self.run_id,
                task_id=task_id,
                agent_id=role,
                tool_name=action,
                arguments=parameters,
                mutating=mutation,
            )
            job = read_agent_job(conn, user_id=self.user_id, job_id=self.job_id)
            if not job:
                raise LookupError("linked Sovereign Agent Job was not found")
            result = run_agent_job_tool(job, action, parameters, self.workspace_root)
            merged = _merge_job_evidence(job, result)
            gate = append_tool_result_to_job(conn, self.job_id, merged)
            finish_agent_tool_call(
                conn,
                tool_call_id=tool_call_id,
                status=(
                    "COMPLETED"
                    if result.status == "done"
                    else "BLOCKED"
                    if result.status == "blocked"
                    else "FAILED_RECOVERABLE"
                ),
                result_summary={
                    "status": result.status,
                    "predictiveSignal": result.predictive_signal,
                    "changedFiles": list(merged.changed_files),
                    "hasDiff": bool(merged.diff_summary),
                    "hasTests": bool(merged.test_summary),
                    "evidencePassed": gate.passed,
                },
                failure_family=(
                    None if result.status == "done" else "AGENT_REPOSITORY_TOOL_BLOCKED"
                    if result.status == "blocked" else "AGENT_REPOSITORY_TOOL_FAILED"
                ),
            )
        except Exception as exc:
            self._record_call(role, mutation=False, failed=True)
            if tool_call_id:
                try:
                    finish_agent_tool_call(
                        conn,
                        tool_call_id=tool_call_id,
                        status="FAILED_RECOVERABLE",
                        result_summary={"errorType": type(exc).__name__},
                        failure_family="AGENT_REPOSITORY_TOOL_EXECUTION_FAILED",
                    )
                except Exception:
                    pass
            raise
        finally:
            _close(conn)
        self._record_call(
            role,
            mutation=mutation and result.status == "done",
            failed=result.status != "done",
        )
        safe_metadata = {
            key: result.metadata.get(key)
            for key in ("path", "bytes", "sha256", "count", "mode", "family", "recommendedTestCommand")
            if isinstance(result.metadata, dict) and key in result.metadata
        }
        payload = {
            "tool": action,
            "status": result.status,
            "output": _redact(result.output or result.stdout or ""),
            "error": _redact(result.error or result.stderr or "", 2_000),
            "blocker": _redact(result.blocker or "", 2_000),
            "changedFiles": list(merged.changed_files),
            "diffSummary": _redact(merged.diff_summary or "", 20_000),
            "testSummary": _redact(merged.test_summary or "", 20_000),
            "predictiveSignal": result.predictive_signal,
            "metadata": safe_metadata,
            "evidence": {
                "passed": gate.passed,
                "reason": _redact(gate.reason, 2_000),
                "canPrepareDraftPr": gate.can_prepare_draft_pr,
                "canLearnPattern": gate.can_learn_pattern,
            },
        }
        findings = result.metadata.get("findings") if isinstance(result.metadata, dict) else None
        if isinstance(findings, list):
            payload["findings"] = findings[:20]
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def tools_for_role(self, role: str) -> list[Any]:
        if role not in ROLE_PATH_PREFIXES:
            return []
        function_tool = _require_function_tool()
        allowed_paths = self.allowed_paths(role)

        def read_repository_file(path: str, max_bytes: int = 120_000) -> str:
            """Read one UTF-8 repository file inside this worker's assigned path boundary."""
            target = self._validate_role_path(role, path)
            bounded = max(1_000, min(int(max_bytes), 300_000))
            return self._execute(role, "file", {"mode": "read", "path": target, "maxBytes": bounded})

        def scan_repository_family(family: str) -> str:
            """Run the deterministic Janitor scan only inside this worker's assigned repository paths."""
            return self._execute(role, "janitor", {
                "mode": "scan",
                "family": str(family or "runtime evidence handoff")[:300],
                "paths": list(allowed_paths),
                "maxFindings": 18,
                "maxFiles": 300,
                "includeDocs": role == "chat_cognitive",
                "explainWithLocalModel": False,
            })

        def inspect_repository_status() -> str:
            """Read real Git status evidence from the linked isolated workspace."""
            return self._execute(role, "git-status", {})

        def inspect_repository_diff(path: str = "") -> str:
            """Read the current Git diff, optionally restricted to one role-scoped file."""
            parameters: dict[str, Any] = {"stat": False, "staged": False}
            if str(path or "").strip():
                parameters["file"] = self._validate_role_path(role, path)
            return self._execute(role, "diff", parameters)

        def run_repository_test(command: str) -> str:
            """Run one allowlisted repository test command and persist its result as runtime evidence."""
            bounded = str(command or "").strip()[:500]
            if not bounded:
                raise ValueError("test command is required")
            return self._execute(role, "test", {"command": bounded, "timeout": 600, "verbose": True})

        tools = [
            function_tool(read_repository_file),
            function_tool(scan_repository_family),
            function_tool(inspect_repository_status),
            function_tool(inspect_repository_diff),
            function_tool(run_repository_test),
        ]
        if self.write_confirmed:
            def write_repository_file(path: str, content: str) -> str:
                """Create or fully replace one UTF-8 file inside the assigned workspace boundary."""
                target = self._validate_role_path(role, path)
                bounded_content = str(content or "")
                if len(bounded_content.encode("utf-8")) > 500_000:
                    raise ValueError("repository file content exceeds the bounded write limit")
                return self._execute(
                    role,
                    "file",
                    {"mode": "write", "path": target, "content": bounded_content, "append": False},
                    mutation=True,
                )

            def apply_exact_repository_patch(
                path: str,
                search_text: str,
                replacement_text: str,
                expected_sha256: str,
            ) -> str:
                """Apply one exact SHA-bound SEARCH/REPLACE inside this worker's assigned path boundary."""
                target = self._validate_role_path(role, path)
                return self._execute(role, "janitor", {
                    "mode": "apply",
                    "path": target,
                    "searchText": search_text,
                    "replacementText": replacement_text,
                    "expectedSha256": expected_sha256,
                    "confirm": True,
                }, mutation=True)

            tools.extend((
                function_tool(write_repository_file),
                function_tool(apply_exact_repository_patch),
            ))
        return tools

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "runId": self.run_id,
                "jobId": self.job_id,
                "writeConfirmed": self.write_confirmed,
                "callsByRole": dict(self._call_counts),
                "mutationsByRole": dict(self._mutation_counts),
                "consecutiveFailuresByRole": dict(self._consecutive_failures),
                "openCircuits": sorted(self._open_circuits),
                "rolesWithCalls": sorted(role for role, count in self._call_counts.items() if count > 0),
                "rolesWithMutations": sorted(role for role, count in self._mutation_counts.items() if count > 0),
            }
