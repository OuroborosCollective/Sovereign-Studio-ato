"""Sovereign Local Runner — Background Worker for Sovereign Agent Jobs.

This module provides the sovereign-local-runner as a background thread that polls
the database for jobs in "provisioning" status and drives them to completion.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.pool
import psycopg2.extras

WORKER_AI_BASE = os.getenv(
    "WORKER_AI_PROXY_URL",
    "https://sovereign-llm-proxy.projectouroboroscollective.workers.dev",
)
WORKER_AI_TIMEOUT = 30


def _llm_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("WORKER_AI_PROXY_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def call_llm_for_next_action(
    mission: str,
    repo_url: str | None,
    branch: str,
    workspace_path: str | None,
    tool_results: list[dict[str, Any]],
    max_iterations: int = 20,
) -> tuple[dict | None, str]:
    context_lines = []
    for r in tool_results[-5:]:
        tool = r.get("tool", "?")
        status = r.get("status", "?")
        output = (r.get("output") or r.get("error") or "")[:500]
        context_lines.append(f"[{tool}] {status}: {output[:200]}")
    context_block = "\n".join(context_lines) if context_lines else "(no previous results)"

    tool_manifest = [
        {"name": "file_read", "description": "Read a file from the workspace", "params": {"path": "relative/path.md"}},
        {"name": "file_write", "description": "Write content to a file", "params": {"path": "file.py", "content": "..."}},
        {"name": "git_status", "description": "Get changed files in workspace", "params": {}},
        {"name": "git_diff", "description": "Get diff of changed files", "params": {}},
        {"name": "shell", "description": "Run a shell command", "params": {"command": "npm test"}},
        {"name": "test", "description": "Run test suite", "params": {"command": "npm test", "framework": "vitest"}},
        {"name": "done", "description": "Mark job as successfully completed", "params": {"summary": "What was accomplished"}},
        {"name": "fail", "description": "Mark job as failed with reason", "params": {"reason": "Why it failed"}},
    ]

    system_prompt = (
        "You are the sovereign-local-runner inside Sovereign Studio. "
        "You execute real file changes in an isolated workspace. "
        "You NEVER fabricate code, tests, or results. "
        "You MUST run real commands and report actual output. "
        "You can call one tool at a time. "
        "When the mission is accomplished, call 'done' with a summary. "
        "If you encounter an error you cannot resolve, call 'fail' with the reason. "
        "IMPORTANT: You must ALWAYS respond with ONLY valid JSON in this exact format: "
        '{"tool": "tool_name", "parameters": {"param1": "value1"}}'
    )

    user_prompt = (
        f"Mission: {mission}\n"
        f"Repository: {repo_url or 'no repo'}\n"
        f"Branch: {branch}\n"
        f"Workspace: {workspace_path or 'not provisioned'}\n"
        f"Iteration: {len(tool_results) + 1}/{max_iterations}\n\n"
        f"Previous results:\n{context_block}\n\n"
        f"Available tools:\n{json.dumps(tool_manifest, indent=2)}\n\n"
        "Respond with ONLY valid JSON: {\"tool\": \"tool_name\", \"parameters\": {...}}"
    )

    try:
        import requests
        resp = requests.post(
            f"{WORKER_AI_BASE.rstrip('/')}/v1/chat/completions",
            headers=_llm_headers(),
            json={
                "model": os.getenv("WORKER_AI_MODEL", "@cf/meta/llama-3.1-8b-instruct"),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 400,
                "temperature": 0.1,
            },
            timeout=WORKER_AI_TIMEOUT,
        )
        if not resp.ok:
            return None, f"LLM returned {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Handle content as dict (Worker AI returns this format)
        if isinstance(raw_content, dict):
            return raw_content if "tool" in raw_content else {"tool": raw_content.get("name", "unknown"), "parameters": raw_content}, ""

        # String content - parse normally
        content = raw_content.strip()

        # Try JSON parse first
        try:
            return json.loads(content), ""
        except Exception:
            pass
        
        # Try extract from code blocks
        import re
        for pattern in [
            r"```json\s*(\{.*?\})\s*```",
            r"```\s*(\{.*?\})\s*```",
        ]:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip()), ""
                except Exception:
                    pass
        
        # Try extract first JSON object from text
        match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
        if match:
            for start in range(len(match.group(0))):
                for end in range(start + 2, len(match.group(0)) + 1):
                    try:
                        return json.loads(match.group(0)[start:end]), ""
                    except Exception:
                        pass
        
        # Try detect tool from natural language
        tool_name = None
        params = {}
        
        cl = content.lower()
        if "done" in cl or "accomplished" in cl or "completed" in cl or "finished" in cl:
            tool_name = "done"
            # Try extract summary
            summary_match = re.search(r"(?:summary|report)[:\s]+(.+?)(?:\n|$)", content, re.IGNORECASE)
            if summary_match:
                params = {"summary": summary_match.group(1).strip()[:200]}
            else:
                params = {"summary": mission}
        elif "fail" in cl or "cannot" in cl or "error" in cl:
            tool_name = "fail"
            reason_match = re.search(r"(?:reason|error|because)[:\s]+(.+?)(?:\n|$)", content, re.IGNORECASE)
            params = {"reason": reason_match.group(1).strip()[:200] if reason_match else content[:100]}
        elif "file_read" in cl or "read" in cl and ("file" in cl or "readme" in cl):
            tool_name = "file_read"
            path_match = re.search(r"(?:path|file|read)[:\s]+[\"'](.+?)[\"']", content, re.IGNORECASE)
            if not path_match:
                path_match = re.search(r"README\.md|readme\.md|README\.md", content, re.IGNORECASE)
            params = {"path": path_match.group(1) if path_match else "README.md"}
        elif "file_write" in cl or "write" in cl or "edit" in cl:
            tool_name = "file_write"
            path_match = re.search(r"(?:path|file)[:\s]+[\"'](.+?)[\"']", content, re.IGNORECASE)
            params = {"path": path_match.group(1) if path_match else "file.txt", "content": ""}
        elif "git_status" in cl or "status" in cl:
            tool_name = "git_status"
        elif "shell" in cl or "command" in cl or "run" in cl:
            tool_name = "shell"
            cmd_match = re.search(r"(?:command|run|execute)[:\s]+[\"'](.+?)[\"']", content, re.IGNORECASE)
            params = {"command": cmd_match.group(1) if cmd_match else "ls"}
        elif "test" in cl:
            tool_name = "test"
            framework_match = re.search(r"framework[:\s]+(\w+)", content, re.IGNORECASE)
            params = {"command": "npm test", "framework": framework_match.group(1) if framework_match else "vitest"}
        else:
            # Default: try to detect any known tool
            for t in ["done", "fail", "file_read", "file_write", "git_status", "shell", "test"]:
                if t.replace("_", " ") in cl or t in cl:
                    tool_name = t
                    break
            
            if not tool_name:
                # Fallback: mark as done since we couldn't understand the response
                return None, f"LLM response is not valid JSON and could not parse tool: {content[:200]}"
        
        return {"tool": tool_name, "parameters": params}, ""
        
    except Exception as e:
        return None, f"LLM call failed: {e}"


def execute_tool_call(
    tool_name: str,
    parameters: dict[str, Any],
    workspace_path: str | None,
) -> dict[str, Any]:
    from .tool_runner import ToolRunner, ToolCall
    from .tool_events import tool_result_to_agent_events
    import uuid

    if workspace_path is None:
        return {"tool": tool_name, "status": "blocked", "output": "", "error": "No workspace path", "events": []}

    runner = ToolRunner(workspace_path)
    call = ToolCall(tool_name=tool_name, parameters=parameters, call_id=f"runner-{uuid.uuid4().hex[:8]}")
    execution = runner._execute_single(call)
    result = execution.result

    return {
        "tool": tool_name,
        "call_id": call.call_id,
        "status": result.status,
        "output": result.output or "",
        "error": result.error or "",
        "blocker": result.blocker,
        "changed_files": list(result.changed_files) if result.changed_files else [],
        "diff_summary": result.diff_summary,
        "test_summary": result.test_summary,
        "events": tool_result_to_agent_events(result),
    }


def _create_runner_pool() -> psycopg2.pool.SimpleConnectionPool:
    """Create a dedicated connection pool for the runner (separate from Flask pool)."""
    return psycopg2.pool.SimpleConnectionPool(
        1, 3,
        host=os.getenv("POSTGRES_HOST", "supabase-db"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


@dataclass
class RunnerJobState:
    job_id: str
    mission: str
    repo_url: str | None
    branch: str
    workspace_id: str
    workspace_path: str | None
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)


def _job_events(job_id: str, events: list[dict[str, Any]], conn: Any) -> None:
    from .job_store import append_agent_event as _append_event
    from .contracts import SovereignAgentEvent
    for ev in events:
        # Handle both dict and ToolEvent/object
        if isinstance(ev, dict):
            stage = str(ev.get("stage", ""))[:80]
            level = str(ev.get("level", "info"))[:20]
            message = str(ev.get("message", ""))[:1200]
            at = ev.get("at", int(time.time() * 1000))
        else:
            # ToolEvent or similar object
            stage = str(getattr(ev, "stage", ""))[:80]
            level = str(getattr(ev, "level", "info"))[:20]
            message = str(getattr(ev, "message", ""))[:1200]
            at = getattr(ev, "at", int(time.time() * 1000))
        event = SovereignAgentEvent(
            stage=stage,
            level=level,
            message=message,
            at=at,
        )
        _append_event(conn, job_id, event)


def _update_job_runner(conn: Any, job_id: str, status: str, blocker: str | None = None, workspace_id: str | None = None) -> None:
    parts = ["status = %s"]
    vals: list[Any] = [status]
    if blocker is not None:
        parts.append("blocker = %s")
        vals.append(blocker)
    if workspace_id is not None:
        parts.append("workspace_id = %s")
        vals.append(workspace_id)
    if status == "running":
        parts.append("started_at = NOW()")
    vals.append(job_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE sovereign_agent_jobs SET {', '.join(parts)} WHERE job_id = %s", vals)
    conn.commit()


def run_job_to_completion(
    job_id: str,
    runner_pool: psycopg2.pool.SimpleConnectionPool,
    workspace_root: str | None,
) -> None:
    conn = None
    try:
        conn = runner_pool.getconn()
        try:
            with conn.cursor(name="runner_cursor") as cur:
                cur.execute(
                    "SELECT job_id, user_id, mission, repo_url, branch, executor, workspace_id FROM sovereign_agent_jobs WHERE job_id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
                if not row:
                    print(f"[runner] Job {job_id} not found, skipping")
                    return
                cols = [d[0] for d in cur.description]
                job = dict(zip(cols, row))

            mission = job.get("mission") or "No mission provided"
            repo_url = job.get("repo_url") or None
            branch = job.get("branch", "main") or "main"

            ws_id = job.get("workspace_id") or job_id
            ws_root = Path(workspace_root) if workspace_root else None
            workspace_path = str(ws_root / ws_id) if ws_root else None

            _update_job_runner(conn, job_id, "running", workspace_id=ws_id)
            _job_events(job_id, [{"stage": "job_started_by_runner", "level": "info", "message": "sovereign-local-runner picked up this job."}], conn)

            if workspace_path:
                ws_path = Path(workspace_path)
                ws_path.mkdir(parents=True, exist_ok=True)
                print(f"[DEBUG] Created workspace: {ws_path} (exists={ws_path.exists()})")
            else:
                print(f"[DEBUG] workspace_path is None! workspace_root={workspace_root!r}")
            if repo_url and workspace_path:
                from .git_workspace import clone_repo_into_workspace
                clone_result = clone_repo_into_workspace(ws_id, repo_url, branch, ws_root)
                tool_results: list[dict[str, Any]] = [{
                    "tool": "git_clone",
                    "status": clone_result.status,
                    "output": clone_result.events[0].message if clone_result.events else "",
                    "error": clone_result.blocker or "",
                }]
                _job_events(job_id, [{"stage": e.stage, "level": e.level, "message": e.message, "at": e.at} for e in clone_result.events], conn)
                if clone_result.status != "done":
                    _update_job_runner(conn, job_id, "failed", blocker=clone_result.blocker or "Repository clone failed")
                    print(f"[runner] Job {job_id} failed: clone failed")
                    return
            else:
                tool_results = []

            state = RunnerJobState(
                job_id=job_id, mission=mission, repo_url=repo_url, branch=branch,
                workspace_id=ws_id, workspace_path=workspace_path,
                tool_results=tool_results, started_at=time.time(),
            )
            max_iters = 20

            for iteration in range(max_iters):
                elapsed_s = time.time() - state.started_at
                if elapsed_s > 3600:  # 1 hour timeout
                    _update_job_runner(conn, job_id, "failed", blocker=f"Job timed out after {elapsed_s/3600:.1f}h")
                    _job_events(job_id, [{"stage": "job_timeout", "level": "error", "message": f"Timed out after {elapsed_s/3600:.1f}h"}], conn)
                    print(f"[runner] Job {job_id} timed out")
                    return

                llm_response, err = call_llm_for_next_action(
                    mission=state.mission, repo_url=state.repo_url, branch=state.branch,
                    workspace_path=state.workspace_path, tool_results=state.tool_results, max_iterations=max_iters,
                )

                if err:
                    if iteration == 0:
                        _job_events(job_id, [{"stage": "llm_retry", "level": "warning", "message": f"LLM call failed ({err}), retrying..."}], conn)
                        continue
                    else:
                        _update_job_runner(conn, job_id, "failed", blocker=f"LLM unavailable: {err}")
                        _job_events(job_id, [{"stage": "job_failed_llm", "level": "error", "message": f"LLM unavailable: {err}"}], conn)
                        print(f"[runner] Job {job_id} failed: LLM unavailable")
                        return

                tool_name = llm_response.get("tool", "")
                params = llm_response.get("parameters", {})

                if tool_name == "done":
                    summary = params.get("summary", "Job completed.")
                    _update_job_runner(conn, job_id, "completed")
                    _job_events(job_id, [{"stage": "job_completed_by_runner", "level": "success", "message": summary}], conn)
                    print(f"[runner] Job {job_id} completed: {summary}")
                    return

                if tool_name == "fail":
                    reason = params.get("reason", "Job failed.")
                    _update_job_runner(conn, job_id, "failed", blocker=reason)
                    _job_events(job_id, [{"stage": "job_failed_by_runner", "level": "error", "message": reason}], conn)
                    print(f"[runner] Job {job_id} failed: {reason}")
                    return

                # Pass repo path so file_read/write/git tools resolve paths correctly
                repo_path = str(Path(state.workspace_path) / "repo") if state.workspace_path else None
                tool_result = execute_tool_call(tool_name, params, repo_path)
                state.tool_results.append(tool_result)
                _job_events(job_id, tool_result.get("events", []), conn)

                if tool_result["status"] in ("blocked", "error"):
                    blocker = tool_result.get("blocker") or tool_result.get("error") or f"Tool '{tool_name}' blocked or errored"
                    _update_job_runner(conn, job_id, "failed", blocker=blocker)
                    _job_events(job_id, [{"stage": "job_failed_tool", "level": "error", "message": blocker}], conn)
                    print(f"[runner] Job {job_id} failed (tool {tool_name}): {blocker}")
                    return

            _update_job_runner(conn, job_id, "failed", blocker=f"Job reached max iterations ({max_iters}) without completing")
            _job_events(job_id, [{"stage": "job_failed_max_iterations", "level": "error", "message": f"Max iterations ({max_iters}) reached."}], conn)
            print(f"[runner] Job {job_id} failed: max iterations")

        finally:
            if conn:
                runner_pool.putconn(conn)
    except Exception as exc:
        print(f"[runner] Job {job_id} exception: {exc}\n{traceback.format_exc()}")


POLL_INTERVAL = int(os.getenv("SOVEREIGN_RUNNER_POLL_SECS", "5"))
ENABLED = os.getenv("SOVEREIGN_RUNNER_ENABLED", "true").lower() == "true"


class SovereignRunnerDaemon(threading.Thread):
    def __init__(
        self,
        runner_pool: psycopg2.pool.SimpleConnectionPool,
        workspace_root: str | None,
    ):
        super().__init__(name="sovereign-local-runner", daemon=True)
        self._pool = runner_pool
        self._workspace_root = workspace_root
        self._running = True
        self._stop_event = threading.Event()
        self._job_threads: dict[str, threading.Thread] = {}

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        for t in list(self._job_threads.values()):
            t.join(timeout=5)
        self._pool.putconn(self._pool.getconn())
        print("[runner] sovereign-local-runner stopped")

    def run(self) -> None:
        print(f"[runner] sovereign-local-runner started (poll={POLL_INTERVAL}s, enabled={ENABLED})")
        while self._running and not self._stop_event.is_set():
            try:
                self._poll_and_dispatch()
            except Exception as exc:
                print(f"[runner] poll error: {exc}")
            self._stop_event.wait(timeout=POLL_INTERVAL)
        for t in list(self._job_threads.values()):
            t.join(timeout=5)
        print("[runner] sovereign-local-runner stopped")

    def _poll_and_dispatch(self) -> None:
        dead = [jid for jid, t in list(self._job_threads.items()) if not t.is_alive()]
        for jid in dead:
            del self._job_threads[jid]

        if not ENABLED:
            return

        try:
            conn = self._pool.getconn()
            try:
                with conn.cursor(name="runner_poll_cursor") as cur:
                    cur.execute(
                        "SELECT job_id FROM sovereign_agent_jobs "
                        "WHERE status = 'provisioning' "
                        "AND created_at < NOW() - INTERVAL '5 seconds' "
                        "AND job_id NOT IN %s "
                        "ORDER BY created_at ASC LIMIT 5",
                        (tuple(self._job_threads.keys()) or ("__empty__",),),
                    )
                    rows = [row[0] for row in cur.fetchall()]
            finally:
                self._pool.putconn(conn)

            for job_id in rows:
                if job_id in self._job_threads:
                    continue
                t = threading.Thread(
                    target=run_job_to_completion,
                    args=(job_id, self._pool, self._workspace_root),
                    name=f"runner-job-{job_id[:12]}",
                    daemon=True,
                )
                self._job_threads[job_id] = t
                t.start()
                print(f"[runner] Dispatched job {job_id} to sovereign-local-runner")

        except Exception as exc:
            print(f"[runner] dispatch error: {exc}")


_runner_daemon: SovereignRunnerDaemon | None = None


_runner_lock = threading.Lock()


def register_sovereign_runner(workspace_root: str | None = None) -> SovereignRunnerDaemon | None:
    """Register and start the sovereign-local-runner daemon.

    Creates its own DB pool to avoid conflicts with Flask's request pool.
    Thread-safe singleton: only one daemon runs even with multiple gunicorn workers.
    """
    global _runner_daemon
    with _runner_lock:
        if _runner_daemon is not None:
            print("[runner] sovereign-local-runner daemon already running")
            return _runner_daemon
        if not ENABLED:
            print("[runner] sovereign-local-runner disabled (SOVEREIGN_RUNNER_ENABLED=false)")
            return None
        try:
            pool = _create_runner_pool()
            # Use None so workspace_policy defaults to /tmp/sovereign-agent/workspaces
            # (matching what the POST /jobs endpoint creates)
            daemon = SovereignRunnerDaemon(pool, workspace_root)
            daemon.start()
            _runner_daemon = daemon
            print(f"[runner] sovereign-local-runner daemon registered")
            return daemon
        except Exception as exc:
            print(f"[runner] Failed to create runner pool: {exc}")
            import traceback
            traceback.print_exc()
            return None


def stop_sovereign_runner() -> None:
    """Stop the runner daemon."""
    global _runner_daemon
    if _runner_daemon:
        _runner_daemon.stop()
        _runner_daemon = None
