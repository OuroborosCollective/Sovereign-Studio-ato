from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from android_hardening import AndroidHardeningRuntime
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
    if os.getenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "0").strip() == "1":
        capabilities.append("repository_merge_pr")
    if os.getenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "0").strip() == "1":
        capabilities.append("repository_rerun_failed_workflows")
    if os.getenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "0").strip() == "1":
        capabilities.append("mcp_self_update")
    return capabilities


def _runtime_boundaries() -> dict[str, Any]:
    return {
        "ok": True,
        "status": "RUNTIME_BOUNDARIES_VERIFIED",
        "node_build_execution": "github_actions_only",
        "local_node_dependency_install_allowed": False,
        "host_mutation_execution": "host_command_queue_only",
        "direct_broker_socket_mutation_allowed": False,
        "generic_shell_available": False,
        "workspace_changes_end_at_draft_pr": True,
        "active_private_admin_capabilities": _private_admin_capabilities(),
    }


runtime = OperatorRuntime()
database = DatabaseRuntime(runtime._repo)
broker = HostBrokerClient()
android = AndroidHardeningRuntime(runtime._repo, runtime._run, runtime._record_check)

mcp = FastMCP(
    "Sovereign ChatGPT Operator",
    instructions=(
        "Arbeite ausschließlich im konfigurierten privaten Repository und VPS. Bereite für Codearbeit zuerst einen isolierten Workspace vor. "
        "Nutze exakte Search/Replace-Patches für bestehende Dateien, besonders große Live-Dateien. Node-Abhängigkeiten, Typecheck, Vitest, Audit, Web- und Container-Builds laufen ausschließlich in GitHub Actions; starte dafür keinen pnpm-Installationsprozess im MCP oder auf dem VPS. "
        "Für Android-Produktionsarbeit beginne mit android_project_inventory, android_failure_family_scan und vorhandener Runtime-Evidence. Korrigiere zuerst die kausale Fehlerfamilie, "
        "füge Regressionstests hinzu, fahre denselben Check erneut und erweitere danach auf benachbarte Familien. android_run_validation_suite bietet fast, standard und release. "
        "Eine Release-Bereitschaft erfordert keine kritischen oder hohen Blocker, grüne relevante Tests und geprüfte APK/AAB-Evidence. "
        "Draft-PR bleibt verfügbar. Bei aktivem privaten Broker-Modus darf repository_push_main direkt nach main pushen und repository_merge_pr einen offenen, nicht als Draft markierten, "
        "mergefähigen PR mit exakt bestätigtem Head-SHA und vollständig grünen Checks mergen. Prüfe vorher repository_pr_status. Bei fehlgeschlagenen CI-Läufen darf "
        "repository_rerun_failed_workflows die betroffenen GitHub-Actions-Läufe erneut starten. Berührt ein gemergter PR den privaten MCP-Code, kann der Merge automatisch die exakte "
        "Merge-Revision zur Selbstinstallation einplanen. Wenn privates Admin-SQL aktiviert ist, darf postgres_admin_sql vollständiges PostgreSQL-SQL auf der eigenen Serverdatenbank ausführen. "
        "Mutierende Host-, GitHub-, Datenbank-, Deploy- und Self-Update-Aktionen dürfen niemals direkt über den eingehenden Broker-Socket ausgeführt werden. Der MCP stellt nur einen validierten Job ein; ein unabhängiger Host-Worker holt ihn von innen ab. Bei IN_PROGRESS lies mcp_host_command_status und reiche den Auftrag nicht erneut ein. "
        "Vor jeder brokerabhängigen Status-, Workflow-, Merge-, Deploy- oder Self-Update-Operation prüfe mcp_control_plane_status. Verwende dessen failure_family unverändert und unterscheide "
        "Socket-Namespace, Pfadtyp, Rechte, Verbindungsverweigerung, Timeout und Protokollantwort. Wiederhole nicht denselben generischen Fix, solange die vorherige Fehlerfamilie nicht durch ihre "
        "Post-Checks als behoben belegt ist. Ein fehlendes typescript/bin/tsc ist eine unvollständige Dependency-Auflösung; erst Exit -9 oder Signal 9 belegt einen getöteten Installationsprozess. "
        "Wenn eine registrierte Reparatur scheitert oder eine neue Fehlerfamilie sichtbar wird, untersuche die Engine im isolierten Workspace, ergänze eine deterministische Reparatur und "
        "Regressionstests, pushe oder merge bei aktivem privaten Modus, lade die bestätigte Revision nach und wiederhole anschließend die ursprüngliche Operation. Ein Self-Update ist nur mit "
        "Host-Socket, Container-Socket, BROKER_READY-RPC, echtem MCP-Initialize-Handshake und aktivem Tunnel erfolgreich. Keine Secrets lesen oder ausgeben."
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
    """Report the mandatory GitHub Actions dependency-build boundary without starting pnpm locally."""
    return runtime.install_dependencies(workspace_id)


@mcp.tool(annotations=SAFE_WRITE)
def repository_run_check(workspace_id: str, check: str, target: str = "") -> dict[str, Any]:
    """Run local Python/diff checks or delegate Node-dependent checks to GitHub Actions."""
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
    return broker.call("git_push_main", {"workspace_id": workspace_id, "commit_message": commit_message}, timeout=720)


@mcp.tool(annotations=NETWORK_READ)
def repository_pr_status(pr_number: int) -> dict[str, Any]:
    """Read PR state, exact head SHA, mergeability and all GitHub check evidence."""
    return broker.call("github_pr_status", {"pr_number": pr_number}, timeout=60)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_rerun_failed_workflows(pr_number: int) -> dict[str, Any]:
    """Rerun failed, cancelled or timed-out GitHub Actions runs for the current PR head."""
    return broker.call("github_rerun_failed_workflows", {"pr_number": pr_number}, timeout=120)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_merge_pr(
    pr_number: int,
    expected_head_sha: str,
    merge_method: str = "squash",
    self_update_after_merge: bool = True,
) -> dict[str, Any]:
    """Merge one confirmed non-draft PR only when GitHub reports it mergeable and all checks are green."""
    return broker.call(
        "github_merge_pr",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "merge_method": merge_method,
            "self_update_after_merge": self_update_after_merge,
        },
        timeout=180,
    )


@mcp.tool(annotations=READ_ONLY)
def android_project_inventory(workspace_id: str) -> dict[str, Any]:
    """Inventory Capacitor/Android surfaces, SDK levels, Gradle/AGP, dependencies, required files and available toolchain."""
    return android.inventory(workspace_id)


@mcp.tool(annotations=READ_ONLY)
def android_failure_family_scan(workspace_id: str) -> dict[str, Any]:
    """Scan Android, Capacitor, Gradle, manifest, release workflow, WebView and artifact contracts for production blockers."""
    return android.scan(workspace_id)


@mcp.tool(annotations=READ_ONLY)
def android_runtime_evidence_analyze(evidence: str) -> dict[str, Any]:
    """Classify bounded Gradle, logcat, WebView, crash, ANR, signing, R8 and SDK evidence into Android failure families."""
    return android.analyze_evidence(evidence)


@mcp.tool(annotations=READ_ONLY)
def android_repair_plan(workspace_id: str, evidence: str = "") -> dict[str, Any]:
    """Correlate repository findings and runtime evidence into a causal, severity-ordered Android repair plan."""
    return android.repair_plan(workspace_id, evidence)


@mcp.tool(annotations=SAFE_WRITE)
def android_run_validation_suite(workspace_id: str, profile: str = "fast") -> dict[str, Any]:
    """Run the fast, standard or release Android validation profile and preserve structured evidence."""
    return android.run_suite(workspace_id, profile)


@mcp.tool(annotations=SAFE_WRITE)
def android_workflow_artifact_import(
    workspace_id: str,
    run_id: int,
    artifact_id: int,
    destination: str = ".sovereign-artifacts/android",
) -> dict[str, Any]:
    """Import one confirmed GitHub Actions artifact into the workspace for APK/AAB inspection."""
    return runtime.import_workflow_artifact(
        workspace_id,
        run_id,
        artifact_id,
        destination,
    )


@mcp.tool(annotations=READ_ONLY)
def android_artifact_inspect(workspace_id: str, artifact_path: str) -> dict[str, Any]:
    """Inspect a workspace APK/AAB for required entries, checksum, ABI surface, signing and alignment evidence when tools exist."""
    return android.inspect_artifact(workspace_id, artifact_path)


@mcp.tool(annotations=EXTERNAL_WRITE)
def mcp_self_update_schedule(expected_revision: str, reason: str = "repair_engine_extension") -> dict[str, Any]:
    """Schedule installation of one exact confirmed main revision of the private ChatGPT MCP and broker."""
    return broker.call("mcp_self_update_schedule", {"expected_revision": expected_revision, "reason": reason}, timeout=60)


@mcp.tool(annotations=READ_ONLY)
def mcp_self_update_status() -> dict[str, Any]:
    """Read the last private MCP self-update state so the original operation can be retried after reload."""
    return broker.call("mcp_self_update_status", {}, timeout=30)


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
        if "repository_push_main" in active or "repository_merge_pr" in active:
            blocked = [item for item in blocked if item != "direct_main_write"]
        policy["blocked_capabilities"] = blocked
        policy["active_private_admin_capabilities"] = active
    return result


@mcp.tool(annotations=READ_ONLY)
def mcp_control_plane_status() -> dict[str, Any]:
    """Probe the host broker with precise socket, permission, connection and timeout evidence."""
    return broker.status()


@mcp.tool(annotations=READ_ONLY)
def mcp_runtime_boundaries() -> dict[str, Any]:
    """Report the enforced execution boundaries without reading secrets or mutating runtime state."""
    return _runtime_boundaries()


@mcp.tool(annotations=READ_ONLY)
def mcp_host_command_status(request_id: str) -> dict[str, Any]:
    """Read one queued host-command state/result without resubmitting the mutation."""
    return broker.command_status(request_id)


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
        {"image_digest": image_digest, "expected_revision": expected_revision, "confirmation_revision": confirmation_revision},
        timeout=960,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def rollback_backend_release(target_image_digest: str, confirmation_digest: str) -> dict[str, Any]:
    """Use the local broker to roll back to one explicitly confirmed immutable image digest."""
    return broker.call(
        "rollback_release",
        {"target_image_digest": target_image_digest, "confirmation_digest": confirmation_digest},
        timeout=960,
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
