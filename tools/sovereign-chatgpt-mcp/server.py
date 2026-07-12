from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from broker_client import HostBrokerClient
from database import DatabaseRuntime
from runtime import OperatorRuntime
from self_heal import REPAIR_ENGINE


def _host() -> str:
    configured = os.getenv("SOVEREIGN_MCP_HOST", "127.0.0.1").strip()
    if configured not in {"127.0.0.1", "localhost", "::1"} and os.getenv("SOVEREIGN_MCP_ALLOW_PUBLIC", "0") != "1":
        raise RuntimeError("Nicht-lokales Binding benötigt SOVEREIGN_MCP_ALLOW_PUBLIC=1 und einen vorgeschalteten Auth-/TLS-Layer")
    return configured


def _private_admin_capabilities() -> list[str]:
    capabilities: list[str] = []
    if os.getenv("SOVEREIGN_MCP_ENABLE_ADMIN_SQL", "0").strip() == "1":
        capabilities.append("postgres_admin_sql")
    if os.getenv("SOVEREIGN_MCP_ENABLE_MAIN_PUSH", "0").strip() == "1":
        capabilities.append("repository_push_main")
    return capabilities


runtime = OperatorRuntime()
database = DatabaseRuntime(runtime._repo)
broker = HostBrokerClient()

mcp = FastMCP(
    "Sovereign ChatGPT Operator",
    instructions=(
        "Arbeite ausschließlich im konfigurierten privaten Repository und VPS. Bereite für Codearbeit zuerst einen isolierten Workspace vor. "
        "Nutze exakte Search/Replace-Patches für bestehende Dateien, besonders große Live-Dateien. "
        "Installiere Abhängigkeiten reproduzierbar und führe passende Checks aus. "
        "Draft-PR ist der normale Weg; wenn der private Broker-Schalter aktiv ist, darf repository_push_main ausdrücklich direkt committen und nach main pushen. "
        "Wenn privates Admin-SQL aktiviert ist, darf postgres_admin_sql vollständiges PostgreSQL-SQL auf der eigenen Serverdatenbank ausführen. "
        "Nutze die interne Fehlerfamilien-Diagnose und setze bekannte Reparaturen selbst fort. Keine Secrets lesen oder ausgeben."
    ),
    host=_host(),
    port=int(os.getenv("SOVEREIGN_MCP_PORT", "8090")),
    stateless_http=True,
    json_response=True,
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
NETWORK_READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
SAFE_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
EXTERNAL_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


@mcp.tool(annotations=SAFE_WRITE)
def workspace_prepare(base_branch: str = "main", task_slug: str = "change") -> dict[str, Any]:
    """Create an isolated clone and a sovereign/chatgpt work branch for a code task."""
    return runtime.prepare_workspace(base_branch=base_branch, task_slug=task_slug)


@mcp.tool(annotations=READ_ONLY)
def repository_read_file(workspace_id: str, path: str, max_bytes: int = 1_000_000) -> dict[str, Any]:
    """Read one UTF-8 repository file from an isolated workspace and return its SHA-256."""
    return runtime.read_file(workspace_id, path, max_bytes)


@mcp.tool(annotations=READ_ONLY)
def repository_search_text(workspace_id: str, query: str, path: str = ".", max_results: int = 100) -> dict[str, Any]:
    """Search real repository files for exact text without relying on UI or cached snapshots."""
    return runtime.search_text(workspace_id, query, path, max_results)


@mcp.tool(annotations=SAFE_WRITE)
def repository_apply_search_replace(
    workspace_id: str,
    path: str,
    blocks: list[dict[str, str]],
    expected_sha256: str = "",
) -> dict[str, Any]:
    """Patch an existing file. Every search block must match exactly once; stale SHA values block the write."""
    return runtime.apply_search_replace(workspace_id, path, blocks, expected_sha256)


@mcp.tool(annotations=SAFE_WRITE)
def repository_write_new_file(workspace_id: str, path: str, content: str) -> dict[str, Any]:
    """Create a new repository file. Existing files cannot be overwritten by this tool."""
    return runtime.write_new_file(workspace_id, path, content)


@mcp.tool(annotations=READ_ONLY)
def repository_diff(workspace_id: str) -> dict[str, Any]:
    """Return current git status, diff and diff statistics for the isolated workspace."""
    return runtime.git_diff(workspace_id)


@mcp.tool(annotations=SAFE_WRITE)
def repository_install_dependencies(workspace_id: str) -> dict[str, Any]:
    """Install repository dependencies with pnpm and the committed lockfile."""
    repo = runtime._repo(workspace_id)
    return runtime._run(["pnpm", "install", "--frozen-lockfile"], cwd=repo, timeout=1800)


@mcp.tool(annotations=SAFE_WRITE)
def repository_run_check(workspace_id: str, check: str, target: str = "") -> dict[str, Any]:
    """Run an allowlisted verification: git_diff_check, backend_compile, pytest, typecheck, audit, build_web or vitest."""
    return runtime.run_check(workspace_id, check, target)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_create_draft_pr(
    workspace_id: str,
    title: str,
    body: str,
    commit_message: str,
) -> dict[str, Any]:
    """Verify, commit and push workspace changes, then create a Draft PR."""
    return runtime.create_draft_pr(workspace_id, title=title, body=body, commit_message=commit_message)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_push_main(workspace_id: str, commit_message: str) -> dict[str, Any]:
    """Commit the current workspace and push its HEAD directly to main when private main-push mode is enabled."""
    return broker.call(
        "git_push_main",
        {"workspace_id": workspace_id, "commit_message": commit_message},
        timeout=720,
    )


@mcp.tool(annotations=READ_ONLY)
def runtime_failure_diagnose(evidence: str) -> dict[str, Any]:
    """Classify bounded runtime evidence and report currently active private broker capabilities."""
    result = REPAIR_ENGINE.diagnose(evidence)
    policy = result.get("policy")
    if isinstance(policy, dict):
        blocked = list(policy.get("blocked_capabilities") or [])
        active = _private_admin_capabilities()
        if "postgres_admin_sql" in active:
            blocked = [item for item in blocked if item != "generic_sql"]
        if "repository_push_main" in active:
            blocked = [item for item in blocked if item != "direct_main_write"]
        policy["blocked_capabilities"] = blocked
        policy["active_private_admin_capabilities"] = active
    return result


@mcp.tool(annotations=READ_ONLY)
def vps_container_status(container: str = "sovereign-backend") -> dict[str, Any]:
    """Inspect the real state of one allowlisted Docker container through the local broker."""
    return broker.call("container_status", {"container": container})


@mcp.tool(annotations=READ_ONLY)
def vps_container_logs(container: str = "sovereign-backend", tail: int = 200) -> dict[str, Any]:
    """Read bounded logs from one allowlisted Docker container through the local broker."""
    return broker.call("container_logs", {"container": container, "tail": tail})


@mcp.tool(annotations=NETWORK_READ)
def backend_image_resolve(revision: str) -> dict[str, Any]:
    """Pull the backend image tag for a full commit SHA, verify its revision label and return the immutable digest."""
    return broker.call("resolve_backend_image", {"revision": revision}, timeout=360)


@mcp.tool(annotations=READ_ONLY)
def postgres_canary() -> dict[str, Any]:
    """Run a read-only SELECT 1 canary against the configured production PostgreSQL connection."""
    return database.canary()


@mcp.tool(annotations=READ_ONLY)
def vector_database_canary() -> dict[str, Any]:
    """Verify pgvector and list at most 100 real vector columns without modifying data."""
    return database.vector_canary()


@mcp.tool(annotations=EXTERNAL_WRITE)
def postgres_admin_sql(sql: str, database: str = "", timeout_seconds: int = 300) -> dict[str, Any]:
    """Execute complete PostgreSQL SQL with the private backend admin identity when broker admin-SQL mode is enabled."""
    return broker.call(
        "postgres_admin_sql",
        {"sql": sql, "database": database, "timeout_seconds": timeout_seconds},
        timeout=max(60, min(int(timeout_seconds) + 30, 3660)),
    )


@mcp.tool(annotations=SAFE_WRITE)
def postgres_migration_preview(workspace_id: str, path: str) -> dict[str, Any]:
    """Execute a migration in the dedicated preview database transaction and always roll it back."""
    return database.preview_migration(workspace_id, path)


@mcp.tool(annotations=EXTERNAL_WRITE)
def postgres_migration_apply(workspace_id: str, path: str, confirmation_sha256: str) -> dict[str, Any]:
    """Apply a confirmed migration and automatically retry registered schema-drift repairs through the private broker."""
    return database.apply_migration(workspace_id, path, confirmation_sha256)


@mcp.tool(annotations=EXTERNAL_WRITE)
def deploy_verified_backend_release(image_digest: str, expected_revision: str, confirmation_revision: str) -> dict[str, Any]:
    """Use the local broker to deploy an immutable image digest."""
    return broker.call(
        "deploy_verified_release",
        {
            "image_digest": image_digest,
            "expected_revision": expected_revision,
            "confirmation_revision": confirmation_revision,
        },
        timeout=960,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def rollback_backend_release(target_image_digest: str, confirmation_digest: str) -> dict[str, Any]:
    """Use the local broker to roll back to one explicitly confirmed immutable image digest."""
    return broker.call(
        "rollback_release",
        {
            "target_image_digest": target_image_digest,
            "confirmation_digest": confirmation_digest,
        },
        timeout=960,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
