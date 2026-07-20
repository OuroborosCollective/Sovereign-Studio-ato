from __future__ import annotations

import os
from typing import Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from a2a_runtime_client import A2ARuntimeClient
from android_hardening import AndroidHardeningRuntime
from broker_client import HostBrokerClient
from database import DatabaseRuntime
from document_pipeline import DocumentPipelineRuntime
from owner_input_client import ControllerRuntimeClient, OwnerInputClient
from owner_input_widget import TOOL_META as OWNER_INPUT_TOOL_META, register_owner_input_widget
from runtime import OperatorRuntime
from self_heal import REPAIR_ENGINE
from sovereign_cognitive_widget import register_sovereign_cognitive_widget


def _host() -> str:
    configured = os.getenv("SOVEREIGN_MCP_HOST", "127.0.0.1").strip()
    if configured not in {"127.0.0.1", "localhost", "::1"} and os.getenv("SOVEREIGN_MCP_ALLOW_PUBLIC", "0") != "1":
        raise RuntimeError("Nicht-lokales Binding benötigt SOVEREIGN_MCP_ALLOW_PUBLIC=1 und einen vorgeschalteten Auth-/TLS-Layer")
    return configured


def _private_admin_capabilities() -> list[str]:
    capabilities: list[str] = []
    if os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1":
        capabilities.append("private_owner_mode")
    if os.getenv("SOVEREIGN_MCP_ENABLE_DB_WRITES", "0").strip() == "1":
        capabilities.append("postgres_write")
    if os.getenv("SOVEREIGN_MCP_ENABLE_DEPLOY", "0").strip() == "1":
        capabilities.append("backend_deploy")
    if os.getenv("SOVEREIGN_MCP_ALLOW_DATA_BACKFILLS", "0").strip() == "1":
        capabilities.append("data_backfill")
    if os.getenv("SOVEREIGN_MCP_ENABLE_ADMIN_SQL", "0").strip() == "1":
        capabilities.append("postgres_admin_sql")
    if os.getenv("SOVEREIGN_MCP_ENABLE_MAIN_PUSH", "0").strip() == "1":
        capabilities.append("repository_push_main")
    if os.getenv("SOVEREIGN_MCP_ENABLE_PR_MERGE", "0").strip() == "1":
        capabilities.append("repository_merge_pr")
    if os.getenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "0").strip() == "1":
        capabilities.extend(("repository_workflow_dispatch", "repository_rerun_failed_workflows"))
    if os.getenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "0").strip() == "1":
        capabilities.append("mcp_self_update")
    if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1":
        capabilities.append("managed_compose_write")
    if os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() == "1":
        capabilities.append("patchmon_patch_write")
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
        "owner_protected_input_execution": "authenticated_owner_ui_only",
        "llm_can_receive_protected_values": False,
        "raw_payment_card_input_allowed": False,
        "private_owner_mode_enabled": os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1",
        "active_private_admin_capabilities": _private_admin_capabilities(),
    }


runtime = OperatorRuntime()
database = DatabaseRuntime(runtime._repo)
broker = HostBrokerClient()
android = AndroidHardeningRuntime(runtime._repo, runtime._run, runtime._record_check)
owner_input = OwnerInputClient()
controller_runtime = ControllerRuntimeClient()
a2a_runtime = A2ARuntimeClient()
document_pipeline = DocumentPipelineRuntime()


def _bounded_controller_text(value: Any, limit: int = 320) -> str:
    return str(value or "").strip()[: max(1, int(limit))]


def _controller_run_summary(payload: Any) -> dict[str, Any]:
    run = payload if isinstance(payload, dict) else {}
    return {
        "runId": _bounded_controller_text(run.get("run_id"), 80),
        "status": _bounded_controller_text(run.get("status"), 80),
        "source": _bounded_controller_text(run.get("source"), 80),
        "iterationCount": run.get("iteration_count") if isinstance(run.get("iteration_count"), int) else 0,
        "maxIterations": run.get("max_iterations") if isinstance(run.get("max_iterations"), int) else 0,
        "leaseActive": bool(run.get("lease_active")),
        "nextAction": _bounded_controller_text(run.get("next_action"), 160),
        "reason": _bounded_controller_text(run.get("reason"), 320),
        "missionSummary": _bounded_controller_text(run.get("mission_summary"), 420),
        "updatedAt": _bounded_controller_text(run.get("updated_at"), 80),
    }


def _controller_item_summary(payload: Any) -> dict[str, Any]:
    item = payload if isinstance(payload, dict) else {}
    return {
        "taskId": _bounded_controller_text(item.get("task_id"), 100),
        "agentId": _bounded_controller_text(
            item.get("agent_id") or item.get("assigned_agent_id") or item.get("role"),
            120,
        ),
        "type": _bounded_controller_text(item.get("type"), 100),
        "status": _bounded_controller_text(item.get("status"), 80),
        "summary": _bounded_controller_text(
            item.get("summary") or item.get("title") or item.get("reason"),
            420,
        ),
        "nextAction": _bounded_controller_text(item.get("next_action"), 160),
        "createdAt": _bounded_controller_text(item.get("created_at") or item.get("updated_at"), 80),
        "family": _bounded_controller_text(item.get("family"), 120),
        "recoverable": bool(item.get("recoverable")),
        "taskLifecycle": _bounded_controller_text(item.get("taskLifecycle"), 40),
        "isCurrentTask": bool(item.get("isCurrentTask")),
        "isActiveTask": bool(item.get("isActiveTask")),
        "isActiveBlocker": bool(item.get("isActiveBlocker")),
        "resolvedByTaskId": _bounded_controller_text(item.get("resolvedByTaskId"), 100),
    }


def _controller_run_evidence(backend_configured: bool) -> dict[str, Any]:
    if not backend_configured:
        return {
            "ok": False,
            "status": "BACKEND_ENDPOINT_NOT_CONFIGURED",
            "runs": [],
            "latestRun": None,
        }
    try:
        listed = controller_runtime.list_runs(limit=5)
        raw_runs = listed.get("runs") if isinstance(listed, dict) else []
        raw_runs = raw_runs if isinstance(raw_runs, list) else []
        runs = [_controller_run_summary(run) for run in raw_runs[:5]]
        latest: dict[str, Any] | None = None
        if raw_runs:
            latest_id = _bounded_controller_text(raw_runs[0].get("run_id") if isinstance(raw_runs[0], dict) else "", 80)
            if latest_id:
                detail = controller_runtime.run_status(run_id=latest_id)
                detail = detail if isinstance(detail, dict) else {}
                detail_run = detail.get("run") if isinstance(detail.get("run"), dict) else raw_runs[0]
                release_hunt = detail.get("releaseHunt") if isinstance(detail.get("releaseHunt"), dict) else {}
                latest = {
                    "run": _controller_run_summary(detail_run),
                    "releaseHunt": {
                        "outcome": _bounded_controller_text(release_hunt.get("outcome"), 40),
                        "errorFamily": _bounded_controller_text(release_hunt.get("errorFamily"), 160),
                        "nextErrorFamily": _bounded_controller_text(release_hunt.get("nextErrorFamily"), 160),
                        "nullfindConfirmed": bool(release_hunt.get("nullfindConfirmed")),
                    },
                    "tasks": [
                        _controller_item_summary(item)
                        for item in (detail.get("tasks") if isinstance(detail.get("tasks"), list) else [])[:20]
                    ],
                    "events": [
                        _controller_item_summary(item)
                        for item in (detail.get("events") if isinstance(detail.get("events"), list) else [])[-30:]
                    ],
                    "failures": [
                        _controller_item_summary(item)
                        for item in (detail.get("failures") if isinstance(detail.get("failures"), list) else [])[-10:]
                    ],
                    "approvals": [
                        _controller_item_summary(item)
                        for item in (detail.get("approvals") if isinstance(detail.get("approvals"), list) else [])[-10:]
                    ],
                }
        return {
            "ok": True,
            "status": "CONTROLLER_EVIDENCE_READY",
            "runs": runs,
            "latestRun": latest,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "CONTROLLER_EVIDENCE_UNAVAILABLE",
            "error": type(exc).__name__,
            "runs": [],
            "latestRun": None,
        }


def _cognitive_architecture_status() -> dict[str, Any]:
    try:
        control_plane = broker.status()
    except Exception as exc:
        control_plane = {
            "ok": False,
            "status": "CONTROL_PLANE_UNAVAILABLE",
            "error": type(exc).__name__,
        }
    control_ready = control_plane.get("status") == "BROKER_READY"
    backend_configured = bool(os.getenv("SOVEREIGN_BACKEND_INTERNAL_URL", "").strip())
    controller_evidence = _controller_run_evidence(backend_configured)
    latest = controller_evidence.get("latestRun")
    latest_run = latest.get("run") if isinstance(latest, dict) and isinstance(latest.get("run"), dict) else {}
    latest_status = _bounded_controller_text(latest_run.get("status"), 80)
    agents_sdk_state = latest_status or (
        "backend_endpoint_configured" if backend_configured else "backend_endpoint_not_configured"
    )
    if control_ready and latest_status:
        summary = f"Control plane is ready; latest persisted Agents SDK run is {latest_status}."
    elif control_ready:
        summary = "Eight-role cognitive architecture is registered; control plane is ready."
    else:
        summary = "Eight-role cognitive architecture is registered, but control-plane evidence is not ready."
    return {
        "ok": control_ready,
        "status": "RUNTIME_READY" if control_ready else "DEGRADED",
        "summary": summary,
        "controlPlane": control_plane,
        "agentsSdkState": agents_sdk_state,
        "controllerRuns": controller_evidence,
        "draftPr": {"ready": False},
        "secretsExposed": False,
    }


mcp = FastMCP(
    "Sovereign ChatGPT Operator",
    instructions=(
        "Arbeite ausschließlich im konfigurierten privaten Repository und VPS. Bereite für Codearbeit zuerst einen isolierten Workspace vor. "
        "Nutze exakte Search/Replace-Patches für bestehende Dateien, besonders große Live-Dateien. Node-Abhängigkeiten, Typecheck, Vitest, Audit, Web- und Container-Builds laufen ausschließlich in GitHub Actions; starte dafür keinen pnpm-Installationsprozess im MCP oder auf dem VPS. "
        "Für Android-Produktionsarbeit beginne mit android_project_inventory, android_failure_family_scan und vorhandener Runtime-Evidence. Korrigiere zuerst die kausale Fehlerfamilie, "
        "füge Regressionstests hinzu, fahre denselben Check erneut und erweitere danach auf benachbarte Familien. android_run_validation_suite bietet fast, standard und release. "
        "Eine Release-Bereitschaft erfordert keine kritischen oder hohen Blocker, grüne relevante Tests und geprüfte APK/AAB-Evidence. "
        "Draft-PR bleibt verfügbar. Bei aktivem privaten Broker-Modus darf repository_push_main direkt nach main pushen und repository_merge_pr einen offenen, "
        "mergefähigen PR mit exakt bestätigtem Head-SHA mergen. Standardmäßig müssen alle Checks grün und der PR bereits bereit sein. Nur bei expliziter Owner-Freigabe darf "
        "repository_merge_pr einen Draft über GitHubs Ready-for-Review-Mutation freigeben und ausschließlich die bekannten Android-Pending-Gates ignorieren, wenn der PR keine Android-Flächen berührt und kein Check fehlgeschlagen ist. Prüfe vorher repository_pr_status. Bei fehlgeschlagenen CI-Läufen darf "
        "repository_rerun_failed_workflows die betroffenen GitHub-Actions-Läufe erneut starten. Berührt ein gemergter PR den privaten MCP-Code, kann der Merge automatisch die exakte "
        "Merge-Revision zur Selbstinstallation einplanen. Wenn privates Admin-SQL aktiviert ist, darf postgres_admin_sql vollständiges PostgreSQL-SQL auf der eigenen Serverdatenbank ausführen. "
        "Wenn für einen Auftrag ein geschützter Serverwert fehlt, verwende owner_approval_request_create. Fordere oder empfange den Wert niemals im Chat oder in MCP-Argumenten. Der Wert darf nur in der authentifizierten Owner-Oberfläche eingegeben werden; MCP liest anschließend ausschließlich den Metadatenstatus. Rohe Zahlungskartennummern sind nicht zulässig. "
        "Für persistierte Controller-Runs des konfigurierten Owners verwende controller_run_start, controller_run_list, controller_run_status und controller_run_resume. Nutze controller_run_external_event nur für exakt identifizierte externe GitHub-, Broker-, MCP-, Dokument- oder Datenbank-Evidence; das Tool darf weder Run-/Task-Status noch aktive Blocker verändern. Diese Brücke darf keine Browser-Cookies, Admin-Keys oder geschützten Werte annehmen und darf WAITING_FOR_OWNER niemals umgehen. "
        "Für öffentliche Manus-Share-Replays verwende manus_public_replay_read. Dieser read-only Pfad akzeptiert ausschließlich HTTPS-Links unter manus.im/share, rendert über den lokal gebundenen Browserless-Content-Endpunkt und gibt begrenzten sichtbaren Text plus Hash-Evidence zurück. "
        "Für die Dokument-Service-Kette verwende document_pipeline_live_canary. Der Canary erzeugt über Gotenberg ein echtes flüchtiges PDF, extrahiert den Marker anschließend über Tika und gibt ausschließlich Status-, Größen- und Hash-Evidence zurück; Dokumentinhalt wird weder persistiert noch ausgegeben. "
        "Für den optionalen Milvus-Pfad verwende memory_gateway_collection_canary. Der Canary läuft ausschließlich über den laufenden Memory-Gateway-Container, erzeugt eine zufällige flüchtige Collection, prüft Insert, Query und Vektorsuche und muss die Collection im finally-Pfad wieder löschen. Ein TCP-Canary allein belegt keine fachliche Memory-Funktion. "
        "Für tiefe Repository-Architektur nutze zuerst repository_skill_tool_inventory und danach je nach Auftrag repository_knowledge_surface_scan, repository_product_logic_map, repository_change_impact_manifest, repository_architecture_snapshot, repository_architecture_drift_report, repository_architecture_runtime_drift_evidence, repository_mirror_diff_report, repository_endpoint_reference, repository_learning_records_normalize_preview oder repository_release_hunt_manifest. Architektur-Snapshot und statischer Drift liefern Kandidaten; repository_architecture_runtime_drift_evidence verbindet Repo-Migrationen ausschließlich mit read-only PostgreSQL-Schema- und Vector-Evidence. Keines dieser Werkzeuge behauptet LLM-Erfolg, mutiert die Datenbank oder erzeugt persisted Hunt-Ergebnisse. Für deterministische Architekturarbeit beginne mit deterministic_tool_inventory und deterministic_architecture_inventory, prüfe danach deterministic_nondeterminism_scan, deterministic_kappa_contract_audit und deterministic_sql_contract_audit. Nutze deterministic_transition_validate und deterministic_replay_verify nur als pure Vorschau ohne Persistenz- oder Laufzeiterfolgsbehauptung; TypeScript/Python-Bitparität erfordert weiterhin unabhängige Ausführung derselben kanonischen Vektoren. Parserfehler können Python-Grammatik-/Versionsdrift oder tatsächlich ungültigen Source bedeuten und müssen gegen die Repository-Zielversion geprüft werden. "
        "Für professionelle Backend- und Systemarchitektur beginne mit backend_engineering_tool_inventory. Nutze backend_architecture_assess für begrenzte statische Evidence, backend_stack_select für eine constraints-basierte Stack-Entscheidung, backend_delivery_plan für einen testgegateden Greenfield- oder Modernisierungsfahrplan und backend_api_security_plan für ein Threat-/Control-/Verifikationsmodell. Nutze repository_revision_resolve vor der Arbeit und erneut nach Merge, Rebase, Update-Branch, Force-Push, Branchwechsel oder Base-Advance; bei Revisionskonflikten muss die Arbeit stoppen. Diese read-only Tools mutieren weder Repository noch Datenbank, führen keinen beliebigen Code aus und behaupten ohne echte Gates weder Runtime-Erfolg noch Compliance. Für autorisierte Implementierung bleiben die vorhandenen Repository-Werkzeuge zuständig. "
        "Für sichere OpenAI-Projektzugänge nutze openai_project_access_plan ausschließlich mit nicht-geheimen Metadaten. Nutze openai_project_access_runtime_evidence für Provider-Identität, Projektzuordnung, Modellinventar, private LiteLLM-Zustände und echte Completion-Canaries. Diese Tools erstellen, lesen, rotieren oder widerrufen keinen OpenAI-Schlüssel und führen keine OpenAI-Admin-Mutation aus. "
        "Für PatchMon beginne mit patchmon_tool_inventory und patchmon_brain_snapshot. Vertiefe ausschließlich mit patchmon_runtime_inventory, patchmon_database_inventory oder den festen patchmon_query-Views; freies Shell, freies SQL, beliebige HTTP-Ziele und ein Docker-Socket im MCP sind nicht erlaubt. Patch-Aktionen erfordern immer patchmon_patch_action_plan gegen den aktuellen Datenbankzustand und anschließend dessen exakten confirmation_sha256. submit_for_approval führt noch keinen Host-Patch aus; approve_run kann einen echten Patch-Lauf auslösen. PATCHMON_ACTION_ACCEPTED belegt nur die Annahme durch PatchMon, niemals den Abschluss der Patches; prüfe den Lauf danach erneut. Das Root-only PatchMon-Admin-JWT darf weder in Chat noch in Tool-Argumenten erscheinen. "
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
    owner_approved: bool = False,
    mark_ready_if_draft: bool = False,
    allow_unrelated_android_pending: bool = False,
) -> dict[str, Any]:
    """Merge one confirmed PR; owner-scoped overrides remain bounded to unrelated Android pending gates."""
    return broker.call(
        "github_merge_pr",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "merge_method": merge_method,
            "self_update_after_merge": self_update_after_merge,
            "owner_approved": owner_approved,
            "mark_ready_if_draft": mark_ready_if_draft,
            "allow_unrelated_android_pending": allow_unrelated_android_pending,
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


@mcp.tool(
    annotations=EXTERNAL_WRITE,
    meta=OWNER_INPUT_TOOL_META,
    structured_output=True,
)
def owner_approval_request_create(
    title: str,
    reason: str,
    target_id: str = "openai_api_key",
    field_label: str = "OpenAI API-Key",
    expires_in_seconds: int = 900,
) -> types.CallToolResult:
    """Create one metadata-only request and render its protected owner-input widget."""
    payload = owner_input.create_request(
        target_id=target_id,
        title=title,
        reason=reason,
        field_label=field_label,
        expires_in_seconds=expires_in_seconds,
    )
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text="Geschützte Owner-Eingabe wurde angefordert.",
            )
        ],
        structuredContent=payload,
        _meta={
            "widget": "sovereign-owner-input",
            "sensitiveValuesIncluded": False,
            "protectedValueTransport": "direct_backend_https_only",
        },
    )


@mcp.tool(annotations=NETWORK_READ)
def owner_approval_request_status(request_id: str) -> dict[str, Any]:
    """Read only lifecycle metadata for one owner request; protected values are never returned."""
    return owner_input.status(request_id)


@mcp.tool(
    annotations=NETWORK_READ,
    meta=OWNER_INPUT_TOOL_META,
    structured_output=True,
)
def owner_approval_widget_open(request_id: str) -> types.CallToolResult:
    """Render the protected owner widget for one existing metadata-only request."""
    payload = owner_input.status(request_id)
    return types.CallToolResult(
        content=[
            types.TextContent(
                type="text",
                text="Geschützte Owner-Eingabe wurde geöffnet.",
            )
        ],
        structuredContent=payload,
        _meta={
            "widget": "sovereign-owner-input",
            "sensitiveValuesIncluded": False,
            "protectedValueTransport": "direct_backend_https_only",
            "requestIdAcceptedAsMetadataOnly": True,
        },
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def controller_run_start(mission: str, evidence: str = "") -> dict[str, Any]:
    """Start one owner-scoped persisted OpenAI Agents SDK run with bounded non-secret input."""
    return controller_runtime.start_run(mission=mission, evidence=evidence)


@mcp.tool(annotations=NETWORK_READ)
def controller_run_list(limit: int = 20) -> dict[str, Any]:
    """List persisted Agents SDK runs for the configured owner without reading a browser session."""
    return controller_runtime.list_runs(limit=limit)


@mcp.tool(annotations=NETWORK_READ)
def controller_run_status(run_id: str) -> dict[str, Any]:
    """Read one owner-scoped persisted run with tasks, events, failures and approvals."""
    return controller_runtime.run_status(run_id=run_id)


@mcp.tool(annotations=EXTERNAL_WRITE)
def controller_run_external_event(
    run_id: str,
    source: str,
    external_identity: str,
    event_type: str,
    summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Append one idempotent owner-scoped external action event without changing run or task state."""
    return controller_runtime.record_external_event(
        run_id,
        source=source,
        external_identity=external_identity,
        event_type=event_type,
        summary=summary,
        payload=payload,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def controller_run_resume(run_id: str, evidence: str = "") -> dict[str, Any]:
    """Resume one eligible owner-scoped run with bounded non-secret runtime evidence."""
    return controller_runtime.resume_run(run_id=run_id, evidence=evidence)


@mcp.tool(annotations=EXTERNAL_WRITE)
def a2a_live_canary(expected_revision: str = "") -> dict[str, Any]:
    """Run one owner-scoped A2A start, stream, task and controller correlation canary."""
    return a2a_runtime.live_canary(expected_revision=expected_revision)


@mcp.tool(annotations=NETWORK_READ)
def manus_public_replay_read(share_url: str) -> dict[str, Any]:
    """Render one public manus.im/share replay and return bounded visible-text evidence."""
    return broker.call("manus_public_replay_read", {"share_url": share_url}, timeout=90)


@mcp.tool(annotations=NETWORK_READ)
def document_pipeline_live_canary(
    marker: str = "SOVEREIGN_DOCUMENT_PIPELINE_CANARY",
) -> dict[str, Any]:
    """Generate one ephemeral PDF with Gotenberg and verify its marker through Tika."""
    return broker.call(
        "document_pipeline_live_canary",
        {"marker": marker},
        timeout=120,
    )


@mcp.tool(annotations=READ_ONLY)
def vps_container_status(container: str = "sovereign-backend") -> dict[str, Any]:
    """Inspect the real state of one allowlisted Docker container through the local broker."""
    return broker.call("container_status", {"container": container})


@mcp.tool(annotations=READ_ONLY)
def vps_container_logs(container: str = "sovereign-backend", tail: int = 200) -> dict[str, Any]:
    """Read bounded logs from one allowlisted Docker container through the local broker."""
    return broker.call("container_logs", {"container": container, "tail": tail})


@mcp.tool(annotations=READ_ONLY)
def managed_compose_stack_plan(stack_id: str) -> dict[str, Any]:
    """Read template hashes and runtime evidence for one allowlisted managed Compose stack."""
    return broker.call("managed_compose_stack_plan", {"stack_id": stack_id}, timeout=60)


@mcp.tool(annotations=EXTERNAL_WRITE)
def memory_gateway_collection_canary() -> dict[str, Any]:
    """Create, write, query, search and drop one ephemeral Milvus collection through the existing gateway container."""
    return broker.call("memory_gateway_collection_canary", {}, timeout=240)


@mcp.tool(annotations=NETWORK_READ)
def litellm_provider_model_inventory() -> dict[str, Any]:
    """Return bounded model-id metadata from the protected OpenAI project without returning its key."""
    return broker.call("litellm_provider_model_inventory", {}, timeout=90)


@mcp.tool(annotations=EXTERNAL_WRITE)
def litellm_model_aliases_activate(
    fast_provider_model: str,
    balanced_provider_model: str,
    confirmation_inventory_sha256: str,
) -> dict[str, Any]:
    """Activate two fixed Sovereign aliases only against one confirmed current provider inventory."""
    return broker.call(
        "litellm_model_aliases_activate",
        {
            "fast_provider_model": fast_provider_model,
            "balanced_provider_model": balanced_provider_model,
            "confirmation_inventory_sha256": confirmation_inventory_sha256,
        },
        timeout=900,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def deploy_managed_compose_stack(stack_id: str, confirmation_sha256: str) -> dict[str, Any]:
    """Deploy one allowlisted fixed Compose template after exact bundle-hash confirmation."""
    return broker.call(
        "deploy_managed_compose_stack",
        {"stack_id": stack_id, "confirmation_sha256": confirmation_sha256},
        timeout=720,
    )


@mcp.tool(annotations=READ_ONLY)
def patchmon_tool_inventory() -> dict[str, Any]:
    """List the fixed PatchMon operator tools and their enforced safety boundaries."""
    return broker.call("patchmon_tool_inventory", {})


@mcp.tool(annotations=READ_ONLY)
def patchmon_runtime_inventory(include_fleet: bool = True, max_fleet_containers: int = 100) -> dict[str, Any]:
    """Inspect PatchMon containers, networks, loopback bindings and bounded Docker-fleet metadata without secrets."""
    return broker.call(
        "patchmon_runtime_inventory",
        {"include_fleet": include_fleet, "max_fleet_containers": max_fleet_containers},
        timeout=120,
    )


@mcp.tool(annotations=READ_ONLY)
def patchmon_database_inventory(max_tables: int = 200, max_columns: int = 2_000) -> dict[str, Any]:
    """Inspect PatchMon PostgreSQL schema, migration and approximate-size metadata without returning row data."""
    return broker.call(
        "patchmon_database_inventory",
        {"max_tables": max_tables, "max_columns": max_columns},
        timeout=120,
    )


@mcp.tool(annotations=READ_ONLY)
def patchmon_query(
    view: str,
    limit: int = 50,
    host_id: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Run one allowlisted, bounded, secret-safe PatchMon view; arbitrary SQL is never accepted."""
    return broker.call(
        "patchmon_query",
        {"view": view, "limit": limit, "host_id": host_id, "status": status},
        timeout=120,
    )


@mcp.tool(annotations=READ_ONLY)
def patchmon_brain_snapshot(include_fleet: bool = True) -> dict[str, Any]:
    """Correlate PatchMon runtime, network, database and Docker-fleet evidence into a bounded risk snapshot."""
    return broker.call("patchmon_brain_snapshot", {"include_fleet": include_fleet}, timeout=180)


@mcp.tool(annotations=READ_ONLY)
def patchmon_patch_action_plan(
    action: str,
    host_id: str = "",
    run_id: str = "",
    patch_type: str = "patch_all",
    package_names: list[str] | None = None,
    schedule_override: str = "",
) -> dict[str, Any]:
    """Plan one allowlisted PatchMon action against current database state and return an exact confirmation hash."""
    return broker.call(
        "patchmon_patch_action_plan",
        {
            "action": action,
            "host_id": host_id,
            "run_id": run_id,
            "patch_type": patch_type,
            "package_names": package_names or [],
            "schedule_override": schedule_override,
        },
        timeout=120,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def patchmon_patch_action_apply(
    action: str,
    confirmation_sha256: str,
    host_id: str = "",
    run_id: str = "",
    patch_type: str = "patch_all",
    package_names: list[str] | None = None,
    schedule_override: str = "",
) -> dict[str, Any]:
    """Submit one exact, state-bound PatchMon action through the host queue and the fixed loopback API."""
    return broker.call(
        "patchmon_patch_action_apply",
        {
            "action": action,
            "confirmation_sha256": confirmation_sha256,
            "host_id": host_id,
            "run_id": run_id,
            "patch_type": patch_type,
            "package_names": package_names or [],
            "schedule_override": schedule_override,
        },
        timeout=300,
    )


@mcp.tool(annotations=NETWORK_READ)
def backend_image_resolve(revision: str) -> dict[str, Any]:
    """Pull the backend image tag for a full commit SHA, verify its revision label and return the immutable digest."""
    return broker.call("resolve_backend_image", {"revision": revision}, timeout=360)


@mcp.tool(annotations=READ_ONLY)
def postgres_canary() -> dict[str, Any]:
    """Run a read-only SELECT 1 canary against the configured production PostgreSQL connection."""
    return database.canary()


@mcp.tool(annotations=READ_ONLY)
def postgres_schema_inventory() -> dict[str, Any]:
    """List bounded non-system PostgreSQL table metadata without returning row data."""
    return database.schema_inventory()


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


def _deploy_backend_with_a2a_evidence(
    image_digest: str,
    expected_revision: str,
    confirmation_revision: str,
) -> dict[str, Any]:
    deployment = broker.call(
        "deploy_verified_release",
        {
            "image_digest": image_digest,
            "expected_revision": expected_revision,
            "confirmation_revision": confirmation_revision,
        },
        timeout=960,
    )
    if not isinstance(deployment, dict) or not deployment.get("ok"):
        return deployment
    try:
        canary = a2a_runtime.live_canary(expected_revision=expected_revision)
    except Exception as exc:
        return {
            **deployment,
            "ok": False,
            "status": "DEPLOYED_A2A_EVIDENCE_UNAVAILABLE",
            "a2aCanary": {
                "ok": False,
                "status": "A2A_LIVE_CANARY_FAILED",
                "errorType": type(exc).__name__,
                "protectedValuesReturned": False,
            },
        }
    canary_ok = bool(isinstance(canary, dict) and canary.get("ok"))
    return {
        **deployment,
        "ok": canary_ok,
        "status": "DEPLOYED_AND_A2A_VERIFIED" if canary_ok else "DEPLOYED_A2A_EVIDENCE_INCOMPLETE",
        "a2aCanary": canary,
    }


@mcp.tool(annotations=EXTERNAL_WRITE)
def deploy_verified_backend_release(image_digest: str, expected_revision: str, confirmation_revision: str) -> dict[str, Any]:
    """Deploy one immutable backend digest and require owner-scoped A2A evidence."""
    return _deploy_backend_with_a2a_evidence(
        image_digest,
        expected_revision,
        confirmation_revision,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def rollback_backend_release(target_image_digest: str, confirmation_digest: str) -> dict[str, Any]:
    """Use the local broker to roll back to one explicitly confirmed immutable image digest."""
    return broker.call(
        "rollback_release",
        {"target_image_digest": target_image_digest, "confirmation_digest": confirmation_digest},
        timeout=960,
    )


register_owner_input_widget(mcp)
register_sovereign_cognitive_widget(
    mcp,
    read_only_annotations=READ_ONLY,
    status_provider=_cognitive_architecture_status,
)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
