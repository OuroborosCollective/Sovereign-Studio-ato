from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Annotated, Any

from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from a2a_runtime_client import A2ARuntimeClient
from android_hardening import AndroidHardeningRuntime
from broker_client import HostBrokerClient
import ci_repair_tools
from database import DatabaseRuntime
from document_pipeline import DocumentPipelineRuntime
from github_issue_contracts import (
    RepositoryIssueCloseOutput,
    RepositoryIssueListOutput,
    RepositoryIssueReadOutput,
)
from output_contracts import normalize_tool_output
from owner_input_client import ControllerRuntimeClient, OwnerInputClient, ProviderRuntimeClient
from owner_input_widget import TOOL_META as OWNER_INPUT_TOOL_META, register_owner_input_widget
from runtime import OperatorRuntime
from repository_skill_tools import classify_changed_paths
from self_heal import REPAIR_ENGINE
from sovereign_cognitive_widget import register_sovereign_cognitive_widget
from sovereign_rescue_widget import register_sovereign_rescue_widget


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
        capabilities.extend((
            "repository_merge_pr",
            "repository_merge_pr_series",
            "repository_main_ruleset_apply",
            "repository_issue_close",
            "repository_update_pr",
            "repository_reopen_pr",
            "repository_close_pr",
            "repository_delete_pr_branch",
        ))
    if os.getenv("SOVEREIGN_MCP_ENABLE_WORKFLOW_CONTROL", "0").strip() == "1":
        capabilities.extend((
            "repository_workflow_dispatch",
            "repository_rerun_failed_workflows",
            "revision_bound_ci_repair",
        ))
    if os.getenv("SOVEREIGN_MCP_ENABLE_SELF_UPDATE", "0").strip() == "1":
        capabilities.append("mcp_self_update")
    if os.getenv("SOVEREIGN_MCP_ENABLE_COMPOSE_WRITE", "0").strip() == "1":
        capabilities.append("managed_compose_write")
    if os.getenv("SOVEREIGN_MCP_ENABLE_PATCHMON_PATCH_WRITE", "0").strip() == "1":
        capabilities.extend(("patchmon_patch_write", "fleet_maintenance_write"))
    if os.getenv("SOVEREIGN_MCP_ENABLE_AURION_OPERATOR", "0").strip() == "1":
        capabilities.extend(("aurion_account_role_readback", "aurion_account_role_plan"))
        if os.getenv("SOVEREIGN_MCP_ENABLE_AURION_WRITE", "0").strip() == "1":
            capabilities.append("aurion_account_role_apply")
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
        "workspace_pr_head_sync": "exact_revision_local_only",
        "workspace_pr_head_sync_force_push_allowed": False,
        "workspace_pr_head_sync_main_mutation_allowed": False,
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
provider_runtime = ProviderRuntimeClient()
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
        "Draft-PR bleibt verfügbar. Derselbe Workspace-Branch wird idempotent weitergeführt; unabhängige parallele Draft-PRs bleiben erlaubt und werden als Evidence gemeldet, nicht pauschal blockiert. repository_merge_pr_series darf mehrere ausdrücklich bestätigte same-repository Drafts älteste zuerst integrieren, muss aber jeden PR nach jedem Main-Advance revisionsgebunden synchronisieren, dessen neue Head-SHA und Update-Commit-Eltern verifizieren und frische terminale Checks abwarten. Ein PR-lokaler Drift, Konflikt oder Checkfehler quarantänisiert ausschließlich diesen Kandidaten und die Serie fährt mit dem nächsten fort; nur ein systemischer Main-Readback- oder Mutationsintegritätsbruch stoppt die Serie. Bereits bestätigte Merges werden niemals zurückgerollt. Wenn Workspace- und PR-Head auseinanderlaufen, verwende repository_sync_workspace_to_pr_head mit der exakt bestätigten PR-Revision; das Tool darf weder remote schreiben noch force-pushen oder main verändern. Bei aktivem privaten Broker-Modus darf repository_push_main direkt nach main pushen und repository_merge_pr einen offenen, "
        "mergefähigen PR mit exakt bestätigtem Head-SHA mergen. repository_close_pr darf ausschließlich mit privatem Owner-Modus, ausdrücklicher Owner-Freigabe, exaktem Head-SHA und einem begrenzten Redundanzgrund schließen; es führt niemals einen Merge aus. Standardmäßig müssen alle Checks grün und der PR bereits bereit sein. Nur bei expliziter Owner-Freigabe darf "
        "repository_merge_pr einen Draft über GitHubs Ready-for-Review-Mutation freigeben und ausschließlich die bekannten Android-Pending-Gates ignorieren, wenn der PR keine Android-Flächen berührt und kein Check fehlgeschlagen ist. Prüfe vorher repository_pr_status. Bei fehlgeschlagenen CI-Läufen darf "
        "repository_rerun_failed_workflows die betroffenen GitHub-Actions-Läufe erneut starten. Berührt ein gemergter PR den privaten MCP-Code, darf der Merge keinen direkten Self-Update-Installer starten. "
        "Ausschließlich der Main-Workflow sovereign-chatgpt-mcp.yml darf nach Validator, immutablem Image-Publish und Digest-Prüfung die bestätigte Merge-Revision auf dem VPS installieren. Wenn privates Admin-SQL aktiviert ist, darf postgres_admin_sql vollständiges PostgreSQL-SQL auf der eigenen Serverdatenbank ausführen. Echoes of Aurion bleibt eine getrennte MariaDB/MySQL-Truth-Boundary: verwende dafür niemals postgres_admin_sql. Im privaten VPS-Profil darf der Installer die drei Aurion-Account-Tools aktivieren. Sie dürfen ausschließlich id/openId/role einer exakt adressierten local:-Identität lesen oder nach Plan-Hash und Owner-Freigabe ändern; localCredentials, Passwortmaterial, andere Nutzer, Schema und Migrationen bleiben ausgeschlossen. "
        "Wenn für einen Auftrag ein geschützter Serverwert fehlt, verwende owner_approval_request_create. Fordere oder empfange den Wert niemals im Chat oder in MCP-Argumenten. Der Wert darf nur in der authentifizierten Owner-Oberfläche eingegeben werden; MCP liest anschließend ausschließlich den Metadatenstatus. Rohe Zahlungskartennummern sind nicht zulässig. Für bezahlte Provider-Routen verwende ausschließlich openrouter_provider_status und openrouter_provider_activate; Paid-Secrets werden ausschließlich über owner_approval_request_create mit target_id openrouter_api_key eingegeben. Für OpenRouter-Free verwende openrouter_free_status, openrouter_free_activate und openrouter_free_key_rotate. Ein Free-Ausführungsschlüssel wird ausschließlich über target_id openrouter_free_api_key eingegeben; ein Management-Key ausschließlich über target_id openrouter_management_api_key. Der Management-Key darf nur Schlüssel verwalten und niemals Modellanfragen ausführen. Alle Aktivierungs- und Rotationswerkzeuge akzeptieren keinen Key als Argument; Zero-Cost-Doppel-Canary, Fingerprints, atomare Dateispeicherung und exakte Upstream-Key-Hashes bleiben im Backend. Für den getrennten direkten FreeLLM-Pfad verwende freellm_provider_status, freellm_provider_keyless_activate, freellm_provider_discover und freellm_provider_recheck. freellm_provider_keyless_activate darf ausschließlich die aktuell allowlisteten Kilo-/OVH-Marker konfigurieren und behauptet noch keine Route als bereit; erst Discovery oder Recheck dürfen nach frischem Katalog und direkter Nullkosten-Doppel-Canary ein Modell aktivieren. Diese Werkzeuge akzeptieren keinen Key. "
        "Für persistierte Controller-Runs des konfigurierten Owners verwende controller_run_start, controller_run_list, controller_run_status und controller_run_resume. Nutze controller_run_external_event nur für exakt identifizierte externe GitHub-, Broker-, MCP-, Dokument- oder Datenbank-Evidence; das Tool darf weder Run-/Task-Status noch aktive Blocker verändern. Diese Brücke darf keine Browser-Cookies, Admin-Keys oder geschützten Werte annehmen und darf WAITING_FOR_OWNER niemals umgehen. "
        "Für öffentliche Manus-Share-Replays verwende manus_public_replay_read. Dieser read-only Pfad akzeptiert ausschließlich HTTPS-Links unter manus.im/share, rendert über den lokal gebundenen Browserless-Content-Endpunkt und gibt begrenzten sichtbaren Text plus Hash-Evidence zurück. "
        "Für die Dokument-Service-Kette verwende document_pipeline_live_canary. Der Canary erzeugt ein echtes flüchtiges DOCX, konvertiert es über Gotenbergs LibreOffice-Pfad zu PDF, extrahiert den Marker anschließend über Tika und gibt ausschließlich Status-, Größen- und Hash-Evidence zurück; Dokumentinhalt wird weder persistiert noch ausgegeben. "
        "Für den GitHub-Knowledge-Livepfad verwende github_knowledge_live_canary nur mit exakt rückgelesener Backend-Revision und immutablem Image-Digest. Der Canary liest eine feste öffentliche GitHub-Datei ohne Credential, persistiert flüchtige echte pgvector-, Provenance- und Outbox-Evidence, prüft einen kontrollierten sicheren Transportfehler und muss Quelle, Blöcke, Outbox und Audit im finally-Pfad vollständig entfernen. Dokumentinhalt, URL, Exceptiondetails und Secrets dürfen nicht ausgegeben werden. "
        "Für den ausdrücklich freigegebenen persistenten ProgrammiersprachenMD-Import verwende programming_language_catalog_persistent_import nur mit exakter laufender Backend-Revision, immutablem Image-Digest und owner_approved=true. Der Pfad ruft den echten Admin-HTTP-Endpunkt zweimal auf, beweist Deduplizierung und liest Quelle, Provenienz, Chunks, Embeddings, Learning Candidates, Vector-Outbox und die authentifizierte Knowledge-Library-Projektion zurück; er bereinigt die Quelle absichtlich nicht. "
        "Für den optionalen Milvus-Pfad verwende memory_gateway_collection_canary. Der Canary läuft ausschließlich über den laufenden Memory-Gateway-Container, erzeugt eine zufällige flüchtige Collection, prüft Insert, Query und Vektorsuche und muss die Collection im finally-Pfad wieder löschen. Ein TCP-Canary allein belegt keine fachliche Memory-Funktion. "
        "Continuity ist ausschließlich advisory Herkunfts- und Handoff-Provenienz. sovereign_continuity_context_read darf bei Bedarf oder im Hintergrund gelesen werden, ist aber kein vorgeschalteter Arbeitsschritt und darf Mutation, Draft PR, Main-Push, Merge, Release, Deployment oder Runtime-Arbeit weder autorisieren noch verzögern oder blockieren. Revisionsbindung, Owner-Freigaben, Secret-Schutz, tatsächliche GitHub-Checks und frischer Target-/Runtime-/PatchMon-Readback bleiben die technischen Autoritäten. Rohe Chatverläufe, Secrets und Authentifizierungsmaterial dürfen nicht in die Continuity-Dateien geschrieben werden. "
        "Bei toolreichen Aufträgen beginne mit operational_skill_inventory und tool_recommend_for_mission. Mehrstufige Pläne werden mit mcp_toolchain_compile, mcp_toolchain_validate und mcp_toolchain_next_step vorbereitet und niemals selbst ausgeführt. Das Modell übersetzt freie Sprache in strukturierte Capabilities; die Runtime darf nur registrierte Tools innerhalb der erlaubten Effect-Klasse deterministisch empfehlen und niemals automatisch ausführen. Nutze mcp_tool_contract_registry und mcp_registry_snapshot_verify nach MCP-Änderungen, bevor der eingefrorene ChatGPT-App-Tool-Snapshot aktualisiert wird. Für revisionsgebundene Betriebsarbeit nutze evidence_graph_build, schema_migration_reconcile, llm_route_reliability_assess, agent_run_liveness_assess, semantic_intent_boundary_audit, cost_credit_settlement_reconcile, backup_restore_evidence_verify, slo_error_budget_assess, configuration_drift_assess, runtime_runbook_generate, ownership_codeowners_guard und compliance_evidence_export. Diese Tools sind read-only-first, akzeptieren keine Secrets, führen keine vorgeschlagenen Mutationen selbst aus und dürfen ohne die jeweilige Runtime-Evidence keinen Erfolg behaupten. "
        "Für die abschließende Betriebs-, Daten-, Memory-, MCP-, Security- und Supply-Chain-Assurance beginne mit operational_assurance_skill_inventory. Prüfe Ressourcenursachen mit vps_capacity_resource_pressure_assess, Abhängigkeiten mit runtime_dependency_health_matrix, Queue-Fortschritt mit outbox_queue_liveness_assess und Wartungsfenster mit scheduled_maintenance_coordinate. Nutze runtime_topology_change_audit, postgres_query_index_performance_assess, data_integrity_invariant_audit, data_repair_plan_build, vector_memory_consistency_assess, memory_poisoning_provenance_guard, learning_pattern_lifecycle_preview, data_retention_privacy_audit und multi_tenant_isolation_verify für zustands- und revisionsgebundene Datenwahrheit. Nummer 29 verwendet die vorhandene mcp_tool_contract_registry; dupliziere sie nicht. Für MCP-Governance und Sicherheit nutze mcp_schema_compatibility_audit, mcp_protocol_conformance_fuzz_plan, tool_permission_minimize, dynamic_execution_containment_audit, skill_capability_coverage_map, skill_lifecycle_deprecation_preview, skill_regression_benchmark, tool_idempotency_verify, owner_approval_policy_evaluate, secret_lifecycle_rotation_assess, secret_literal_triage, sbom_provenance_image_signing_verify, dependency_vulnerability_remediation_plan und authentication_chaos_negative_test_assess. Diese Tools führen keine Reparatur, Freigabe, Löschung, Rotation oder Deprecation automatisch aus; nur ausdrücklich angeforderte, selbstaufräumende Dokument- und Milvus-Canaries dürfen temporäre Runtime-Artefakte erzeugen. "
        "Für tiefe Repository-Architektur nutze zuerst repository_skill_tool_inventory und danach je nach Auftrag repository_knowledge_surface_scan, repository_product_logic_map, repository_change_impact_manifest, repository_architecture_snapshot, repository_architecture_drift_report, repository_architecture_runtime_drift_evidence, repository_mirror_diff_report, repository_endpoint_reference, repository_learning_records_normalize_preview oder repository_release_hunt_manifest. Architektur-Snapshot und statischer Drift liefern Kandidaten; repository_architecture_runtime_drift_evidence verbindet Repo-Migrationen ausschließlich mit read-only PostgreSQL-Schema- und Vector-Evidence. Keines dieser Werkzeuge behauptet LLM-Erfolg, mutiert die Datenbank oder erzeugt persisted Hunt-Ergebnisse. Für deterministische Architekturarbeit beginne mit deterministic_tool_inventory und deterministic_architecture_inventory, prüfe danach deterministic_nondeterminism_scan, deterministic_kappa_contract_audit und deterministic_sql_contract_audit. Nutze deterministic_transition_validate und deterministic_replay_verify nur als pure Vorschau ohne Persistenz- oder Laufzeiterfolgsbehauptung; TypeScript/Python-Bitparität erfordert weiterhin unabhängige Ausführung derselben kanonischen Vektoren. Parserfehler können Python-Grammatik-/Versionsdrift oder tatsächlich ungültigen Source bedeuten und müssen gegen die Repository-Zielversion geprüft werden. "
        "Für professionelle Backend- und Systemarchitektur beginne mit backend_engineering_tool_inventory. Nutze backend_architecture_assess für begrenzte statische Evidence, backend_stack_select für eine constraints-basierte Stack-Entscheidung, backend_delivery_plan für einen testgegateden Greenfield- oder Modernisierungsfahrplan und backend_api_security_plan für ein Threat-/Control-/Verifikationsmodell. Nutze repository_revision_resolve vor der Arbeit und erneut nach Merge, Rebase, Update-Branch, Force-Push, Branchwechsel oder Base-Advance; bei Revisionskonflikten muss die Arbeit stoppen. Diese read-only Tools mutieren weder Repository noch Datenbank, führen keinen beliebigen Code aus und behaupten ohne echte Gates weder Runtime-Erfolg noch Compliance. Für autorisierte Implementierung bleiben die vorhandenen Repository-Werkzeuge zuständig. "
        "Für sichere OpenAI-Projektzugänge nutze openai_project_access_plan ausschließlich mit nicht-geheimen Metadaten. Nutze openai_project_access_runtime_evidence für Provider-Identität, Projektzuordnung, direktes OpenRouter-Modellinventar und echte Completion-Canaries. Diese Tools erstellen, lesen, rotieren oder widerrufen keinen OpenAI-Schlüssel und führen keine OpenAI-Admin-Mutation aus. "
        "Für PatchMon beginne mit patchmon_tool_inventory und patchmon_brain_snapshot. Vertiefe ausschließlich mit patchmon_runtime_inventory, patchmon_database_inventory oder den festen patchmon_query-Views; freies Shell, freies SQL, beliebige HTTP-Ziele und ein Docker-Socket im MCP sind nicht erlaubt. Wenn Hosts oder Docker-Inventar fehlen, verwende patchmon_fleet_bootstrap_plan und nach exakter Hash-Bestätigung patchmon_fleet_bootstrap_apply mit ausdrücklicher Owner-Freigabe. Solange ein verbundener Client seinen Tool-Schemacache noch nicht um diese beiden Namen aktualisiert hat, ist ausschließlich der feste Kompatibilitäts-Alias action=bootstrap_local_fleet über patchmon_patch_action_plan und patchmon_patch_action_apply zulässig; er bindet denselben aktuellen Zustand und denselben confirmation_sha256 und läuft ebenfalls nur über die Host-Command-Queue. Dieser Pfad erstellt bei leerer Installation eine root-only Operator-Identität, konfiguriert ausschließlich den festen Loopback-Server, installiert den offiziellen Agenten und fordert echtes Docker-Inventar an; Secrets werden nie ausgegeben. patchmon_fleet_orchestrator_status verbindet anschließend PatchMon-Evidence mit PR-/Workflow- und Revisionsstatus. Container-Images bleiben ausschließlich im vorhandenen immutablem Deploy-Pfad; PatchMon erhält keine erfundene Container-Revision-Mutation. Patch-Aktionen erfordern immer patchmon_patch_action_plan gegen den aktuellen Datenbankzustand und anschließend dessen exakten confirmation_sha256. submit_for_approval führt noch keinen Host-Patch aus; approve_run kann einen echten Patch-Lauf auslösen. PATCHMON_ACTION_ACCEPTED belegt nur die Annahme durch PatchMon, niemals den Abschluss der Patches; prüfe den Lauf danach erneut. Das Root-only PatchMon-Admin-JWT darf weder in Chat noch in Tool-Argumenten erscheinen. "
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
WORKSPACE_NETWORK_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
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


@mcp.tool(annotations=WORKSPACE_NETWORK_WRITE)
def repository_sync_workspace_to_pr_head(
    workspace_id: str,
    pr_number: int,
    expected_pr_head_sha: str,
) -> dict[str, Any]:
    """Sync one workspace to the exact current head of its existing PR without remote writes or force-push."""
    return runtime.sync_workspace_to_pr_head(
        workspace_id,
        pr_number=pr_number,
        expected_pr_head_sha=expected_pr_head_sha,
    )


@mcp.tool(annotations=SAFE_WRITE)
def repository_materialize_pr_paths(
    workspace_id: str,
    pr_number: int,
    expected_pr_head_sha: str,
    paths: list[str],
) -> dict[str, Any]:
    """Copy selected files from one exact same-repository PR head into an isolated workspace."""
    return runtime.materialize_pr_paths(
        workspace_id,
        pr_number=pr_number,
        expected_pr_head_sha=expected_pr_head_sha,
        paths=paths,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_create_draft_pr(
    workspace_id: str,
    title: str,
    body: str,
    commit_message: str,
) -> dict[str, Any]:
    """Verify, commit and push changes, then create or update the Draft PR for this workspace branch."""
    return runtime.create_draft_pr(workspace_id, title=title, body=body, commit_message=commit_message)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_push_main(workspace_id: str, commit_message: str) -> dict[str, Any]:
    """Commit the current workspace and push its HEAD directly to main when private main-push mode is enabled."""
    continuity_result = runtime.continuity_completion_advisory(workspace_id)
    result = broker.call("git_push_main", {"workspace_id": workspace_id, "commit_message": commit_message}, timeout=720)
    if isinstance(result, dict):
        return {**result, "continuity": continuity_result}
    return {"ok": False, "status": "MAIN_PUSH_RESPONSE_INVALID", "continuity": continuity_result}


@mcp.tool(annotations=NETWORK_READ)
def repository_issue_list(
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum number of open non-PR issues to return.")] = 20,
) -> RepositoryIssueListOutput:
    """List current open GitHub issues, excluding pull requests, with authenticated readback."""
    payload = normalize_tool_output(
        broker.call("github_issue_list", {"limit": limit}, timeout=60)
    )
    payload.setdefault("readbackVerified", False)
    return RepositoryIssueListOutput.model_validate(payload)


@mcp.tool(annotations=NETWORK_READ)
def repository_issue_read(
    issue_number: Annotated[int, Field(ge=1, description="Positive GitHub issue number.")],
) -> RepositoryIssueReadOutput:
    """Read one current GitHub issue body and metadata with authenticated readback."""
    payload = normalize_tool_output(
        broker.call("github_issue_read", {"issue_number": issue_number}, timeout=60)
    )
    payload.setdefault("readbackVerified", False)
    return RepositoryIssueReadOutput.model_validate(payload)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_issue_close(
    issue_number: Annotated[int, Field(ge=1, description="Positive GitHub issue number.")],
    expected_updated_at: Annotated[
        str,
        Field(min_length=1, max_length=64, description="Exact updatedAt value from repository_issue_read."),
    ],
    owner_approved: bool = False,
) -> RepositoryIssueCloseOutput:
    """Close one unchanged issue as completed and verify exact GitHub readback."""
    payload = normalize_tool_output(
        broker.call(
            "github_issue_close",
            {
                "issue_number": issue_number,
                "expected_updated_at": expected_updated_at,
                "owner_approved": owner_approved,
            },
            timeout=120,
        ),
        external_write=True,
    )
    return RepositoryIssueCloseOutput.model_validate(payload)


@mcp.tool(annotations=NETWORK_READ)
def repository_pr_status(pr_number: int) -> dict[str, Any]:
    """Read PR state, exact head SHA, mergeability and all GitHub check evidence."""
    return broker.call("github_pr_status", {"pr_number": pr_number}, timeout=60)


@mcp.tool(annotations=NETWORK_READ)
def repository_pr_changed_paths(
    pr_number: int,
    max_paths: Annotated[int, Field(ge=1, le=64)] = 64,
) -> dict[str, Any]:
    """Read bounded changed paths twice-bound to one unchanged PR head."""
    return broker.call(
        "github_pr_changed_paths",
        {"pr_number": pr_number, "max_paths": max_paths},
        timeout=120,
    )


def _fleet_numbers(values: list[int] | None, label: str) -> list[int]:
    if values is None:
        return []
    if len(values) > 40:
        raise ValueError(f"{label} exceeds the bounded item limit")
    normalized = sorted(dict.fromkeys(int(value) for value in values))
    if any(value < 1 for value in normalized):
        raise ValueError(f"{label} must contain positive identifiers")
    return normalized


def _fleet_projection_read(
    *,
    plan: dict[str, Any],
    assignments: list[dict[str, Any]] | None,
    worker_events: list[dict[str, Any]] | None,
    verdicts: list[dict[str, Any]] | None,
    observed_main_revision: str,
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object returned by fleet_plan_read")
    return controller_runtime.fleet_projection_preview({
        "plan": plan,
        "assignments": assignments or [],
        "workerEvents": worker_events or [],
        "verdicts": verdicts or [],
        "observedMainRevision": str(observed_main_revision or "").strip(),
    })


@mcp.tool(annotations=NETWORK_READ)
def fleet_plan_read(
    integration_id: Annotated[str, Field(min_length=3, max_length=120)],
    base_revision: Annotated[str, Field(min_length=40, max_length=64)],
    issue_numbers: list[int] | None = None,
    pr_numbers: list[int] | None = None,
    architecture_receipt_hashes: list[str] | None = None,
    max_parallel_lanes: Annotated[int, Field(ge=1, le=8)] = 1,
) -> dict[str, Any]:
    """Read GitHub sources and build a fail-closed, non-mutating FleetPlan."""

    sources: list[dict[str, Any]] = []
    readbacks: list[dict[str, Any]] = []
    for issue_number in _fleet_numbers(issue_numbers, "issue_numbers"):
        issue = normalize_tool_output(
            broker.call("github_issue_read", {"issue_number": issue_number}, timeout=60)
        )
        sources.append({
            "taskId": f"issue-{issue_number}",
            "sourceType": "issue",
            "sourceId": str(issue_number),
            "expectedBaseRevision": base_revision.strip(),
            "changedPaths": [],
            "reasonCodes": [
                "GITHUB_ISSUE_READBACK_BOUND",
                "CHANGED_PATHS_UNAVAILABLE_SERIALIZED",
            ],
            "independenceProven": False,
        })
        readbacks.append({
            "sourceType": "issue",
            "sourceId": str(issue_number),
            "title": _bounded_controller_text(issue.get("title"), 180),
            "readbackVerified": bool(issue.get("readbackVerified") or issue.get("readback_verified")),
        })
    for pr_number in _fleet_numbers(pr_numbers, "pr_numbers"):
        pull = normalize_tool_output(
            broker.call("github_pr_status", {"pr_number": pr_number}, timeout=60)
        )
        raw_head = pull.get("headSha") or pull.get("head_sha") or ""
        head_sha = raw_head.strip() if isinstance(raw_head, str) else ""
        path_readback = normalize_tool_output(
            broker.call(
                "github_pr_changed_paths",
                {"pr_number": pr_number, "max_paths": 64},
                timeout=120,
            )
        )
        raw_path_head = path_readback.get("headSha") or path_readback.get("head_sha") or ""
        path_head = raw_path_head.strip() if isinstance(raw_path_head, str) else ""
        changed_paths = (
            [str(path) for path in path_readback.get("changedPaths", path_readback.get("changed_paths", []))]
            if isinstance(path_readback.get("changedPaths", path_readback.get("changed_paths", [])), list)
            else []
        )
        paths_complete = bool(path_readback.get("pathsComplete", path_readback.get("paths_complete", False)))
        path_readback_verified = bool(
            path_readback.get("readbackVerified") or path_readback.get("readback_verified")
        )
        exact_path_binding = bool(
            path_readback.get("ok")
            and paths_complete
            and path_readback_verified
            and head_sha
            and path_head == head_sha
            and changed_paths
        )
        classification = (
            classify_changed_paths(changed_paths)
            if exact_path_binding
            else {
                "changedPaths": [],
                "domains": [],
                "requiredGates": [],
                "safetyScopes": [],
                "independenceClassifiable": False,
                "receiptSha256": None,
            }
        )
        receipts_bound = bool(architecture_receipt_hashes)
        independence_proven = bool(
            exact_path_binding
            and classification.get("independenceClassifiable")
            and receipts_bound
        )
        reason_codes = ["GITHUB_PR_STATUS_READBACK_BOUND"]
        if exact_path_binding:
            reason_codes.extend((
                "GITHUB_PR_CHANGED_PATHS_EXACT_HEAD_BOUND",
                "ARCHITECTURE_PATH_CLASSIFICATION_BOUND",
            ))
        else:
            reason_codes.append("CHANGED_PATHS_INCOMPLETE_OR_STALE_SERIALIZED")
        if independence_proven:
            reason_codes.append("ARCHITECTURE_RECEIPT_BOUND_INDEPENDENCE_PROVEN")
        elif not receipts_bound:
            reason_codes.append("ARCHITECTURE_RECEIPT_MISSING_SERIALIZED")
        elif exact_path_binding:
            reason_codes.append("ARCHITECTURE_PATH_UNCLASSIFIED_SERIALIZED")
        sources.append({
            "taskId": f"pr-{pr_number}",
            "sourceType": "pr",
            "sourceId": str(pr_number),
            "expectedBaseRevision": base_revision.strip(),
            "expectedHeadRevision": head_sha,
            "changedPaths": classification.get("changedPaths", []),
            "architectureDomains": classification.get("domains", []),
            "canonicalOwners": classification.get("safetyScopes", []),
            "invariantScopes": classification.get("safetyScopes", []),
            "requiredGates": classification.get("requiredGates", []),
            "reasonCodes": reason_codes,
            "independenceProven": independence_proven,
        })
        readbacks.append({
            "sourceType": "pr",
            "sourceId": str(pr_number),
            "headSha": head_sha or None,
            "readbackVerified": bool(pull.get("readbackVerified") or pull.get("readback_verified")),
            "changedPathHeadSha": path_head or None,
            "changedPathReadbackVerified": path_readback_verified,
            "changedPathCount": path_readback.get("changedFileCount", path_readback.get("changed_file_count", 0)),
            "changedPathsComplete": paths_complete,
            "architectureClassificationReceiptSha256": classification.get("receiptSha256"),
            "independenceProven": independence_proven,
        })
    if not sources:
        raise ValueError("at least one issue or pull request source is required")

    result = controller_runtime.fleet_plan_preview({
        "integrationId": integration_id.strip(),
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "baseRevision": base_revision.strip(),
        "tasks": sources,
        "architectureReceiptHashes": architecture_receipt_hashes or [],
        "maxParallelLanes": max_parallel_lanes,
    })
    return {
        **result,
        "sourceReadbacks": readbacks,
        "plannerNotice": (
            "Paths or canonical ownership not supplied by authenticated source readback "
            "remain serialized; this tool does not infer safe parallelism."
        ),
    }


@mcp.tool(annotations=NETWORK_READ)
def fleet_verdict_preview(
    task: dict[str, Any],
    observed_base_revision: str,
    observed_head_revision: str,
    workspace_head_revision: str,
    assignment: dict[str, Any] | None = None,
    check_receipts: list[dict[str, Any]] | None = None,
    review_receipts: list[dict[str, Any]] | None = None,
    cross_task_receipts: list[dict[str, Any]] | None = None,
    merge_readback: dict[str, Any] | None = None,
    runtime_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Arbitrate Fleet evidence through the controller without authorizing merge or mutating state."""
    payload = {
        "task": task,
        "assignment": assignment,
        "observedBaseRevision": observed_base_revision,
        "observedHeadRevision": observed_head_revision,
        "workspaceHeadRevision": workspace_head_revision,
        "checkReceipts": check_receipts or [],
        "reviewReceipts": review_receipts or [],
        "crossTaskReceipts": cross_task_receipts or [],
        "mergeReadback": merge_readback,
        "runtimeReadback": runtime_readback,
    }
    return controller_runtime.fleet_verdict_preview(payload)


@mcp.tool(annotations=NETWORK_READ)
def fleet_status(
    plan: dict[str, Any],
    observed_main_revision: str,
    assignments: list[dict[str, Any]] | None = None,
    worker_events: list[dict[str, Any]] | None = None,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebuild the read-only fleet projection; stale main-head evidence blocks commands."""

    return _fleet_projection_read(
        plan=plan,
        assignments=assignments,
        worker_events=worker_events,
        verdicts=verdicts,
        observed_main_revision=observed_main_revision,
    )


@mcp.tool(annotations=NETWORK_READ)
def fleet_lane_status(
    plan: dict[str, Any],
    lane_id: Annotated[str, Field(min_length=1, max_length=120)],
    observed_main_revision: str,
    assignments: list[dict[str, Any]] | None = None,
    worker_events: list[dict[str, Any]] | None = None,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Read one lane from a rebuilt, hash-bound FleetPlan projection."""

    result = _fleet_projection_read(
        plan=plan,
        assignments=assignments,
        worker_events=worker_events,
        verdicts=verdicts,
        observed_main_revision=observed_main_revision,
    )
    projection = result.get("projection") if isinstance(result.get("projection"), dict) else {}
    lane = next(
        (item for item in projection.get("lanes", []) if isinstance(item, dict) and item.get("laneId") == lane_id),
        None,
    )
    if lane is None:
        raise ValueError("lane_id is not present in the submitted FleetPlan")
    return {
        "ok": bool(result.get("ok")),
        "status": "FLEET_LANE_STATUS",
        "readOnly": True,
        "mutationPerformed": False,
        "lane": lane,
        "stale": bool(projection.get("stale")),
        "evidenceGaps": projection.get("evidenceGaps", []),
    }


@mcp.tool(annotations=NETWORK_READ)
def fleet_blockers(
    plan: dict[str, Any],
    observed_main_revision: str,
    assignments: list[dict[str, Any]] | None = None,
    worker_events: list[dict[str, Any]] | None = None,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return only readback-backed lane blockers; this tool has no action side effect."""

    result = _fleet_projection_read(
        plan=plan,
        assignments=assignments,
        worker_events=worker_events,
        verdicts=verdicts,
        observed_main_revision=observed_main_revision,
    )
    projection = result.get("projection") if isinstance(result.get("projection"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "status": "FLEET_BLOCKERS",
        "readOnly": True,
        "mutationPerformed": False,
        "blockers": [
            lane for lane in projection.get("lanes", [])
            if isinstance(lane, dict) and lane.get("status") in {"BLOCKED", "STALE"}
        ],
        "evidenceGaps": projection.get("evidenceGaps", []),
    }


@mcp.tool(annotations=NETWORK_READ)
def fleet_evidence_gaps(
    plan: dict[str, Any],
    observed_main_revision: str,
    assignments: list[dict[str, Any]] | None = None,
    worker_events: list[dict[str, Any]] | None = None,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the exact evidence gaps which keep Fleet execution or verification blocked."""

    result = _fleet_projection_read(
        plan=plan,
        assignments=assignments,
        worker_events=worker_events,
        verdicts=verdicts,
        observed_main_revision=observed_main_revision,
    )
    projection = result.get("projection") if isinstance(result.get("projection"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "status": "FLEET_EVIDENCE_GAPS",
        "readOnly": True,
        "mutationPerformed": False,
        "stale": bool(projection.get("stale")),
        "commandsBlocked": bool(projection.get("commandsBlocked")),
        "evidenceGaps": projection.get("evidenceGaps", []),
        "nextEligibleActions": projection.get("nextEligibleActions", []),
    }


@mcp.tool(annotations=NETWORK_READ)
def workflow_failure_evidence_extract(
    workflow_run_id: int,
    expected_head_sha: str,
) -> dict[str, Any]:
    """Extract the first causal failure from bounded exact-head job and test artifacts."""
    return broker.call(
        "github_workflow_failure_evidence_extract",
        {
            "run_id": workflow_run_id,
            "expected_head_sha": expected_head_sha,
        },
        timeout=120,
    )


@mcp.tool(annotations=SAFE_WRITE)
def deterministic_boundary_ledger_reconcile(
    workspace_id: str,
    expected_revision: str,
    owner_decisions: dict[str, dict[str, str]] | None = None,
    apply_patch: bool = False,
    append_continuity: bool = False,
) -> dict[str, Any]:
    """Preserve reviewed classifications while previewing or applying exact-head boundary drift."""
    expected = str(expected_revision or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("expected_revision must be a full Git SHA")
    repo = runtime._repo(workspace_id)
    head_result = runtime._run(["git", "rev-parse", "HEAD"], cwd=repo)
    status_result = runtime._run(["git", "status", "--porcelain"], cwd=repo)
    head = str(head_result.get("stdout") or "").strip().lower()
    dirty = str(status_result.get("stdout") or "").splitlines()
    if not head_result.get("ok") or not status_result.get("ok") or head != expected or dirty:
        return {
            "ok": False,
            "status": "REVISION_CONFLICT",
            "failureFamily": "REVISION_CONFLICT",
            "workspaceHeadSha": head,
            "expectedRevision": expected,
            "dirtyEntries": dirty,
            "mutationPerformed": False,
        }
    ledger_path = repo / ci_repair_tools.DEFAULT_LEDGER_RELATIVE
    result = ci_repair_tools.reconcile_ledger(
        repo,
        ci_repair_tools.load_ledger(ledger_path),
        owner_decisions=owner_decisions,
        write_path=ledger_path if apply_patch else None,
    )
    if apply_patch and append_continuity:
        result = {
            **result,
            "continuity": ci_repair_tools.append_boundary_reconciliation_continuity(
                repo,
                source_revision=expected,
                reconciliation=result,
            ),
        }
    return result


@mcp.tool(annotations=EXTERNAL_WRITE)
def revision_bound_ci_repair(
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
    """Bind evidence, specialist repair, continuity, tests, PR update, rerun and head readback."""
    return ci_repair_tools.revision_bound_ci_repair(
        runtime=runtime,
        broker=broker,
        workspace_id=workspace_id,
        pr_number=pr_number,
        workflow_run_id=workflow_run_id,
        expected_pr_head_sha=expected_pr_head_sha,
        owner_decisions=owner_decisions,
        apply_patch=apply_patch,
        publish_patch=publish_patch,
        rerun_failed=rerun_failed,
        owner_approved=owner_approved,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_rerun_failed_workflows(pr_number: int) -> dict[str, Any]:
    """Rerun failed, cancelled or timed-out GitHub Actions runs for the current PR head."""
    return broker.call("github_rerun_failed_workflows", {"pr_number": pr_number}, timeout=120)


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_merge_pr(
    pr_number: int,
    expected_head_sha: str,
    merge_method: str = "squash",
    self_update_after_merge: bool = False,
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


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_merge_pr_series(
    pull_requests: list[dict[str, Any]],
    merge_method: str = "squash",
    owner_approved: bool = False,
    mark_ready_if_draft: bool = True,
    allow_unrelated_android_pending: bool = False,
    wait_seconds_per_pr: int = 1800,
    poll_seconds: int = 15,
) -> dict[str, Any]:
    """Merge owner-confirmed PRs oldest-first; quarantine candidate-local failures and continue safely."""
    return broker.call(
        "github_merge_pr_series",
        {
            "pull_requests": pull_requests,
            "merge_method": merge_method,
            "owner_approved": owner_approved,
            "mark_ready_if_draft": mark_ready_if_draft,
            "allow_unrelated_android_pending": allow_unrelated_android_pending,
            "wait_seconds_per_pr": wait_seconds_per_pr,
            "poll_seconds": poll_seconds,
        },
        timeout=max(300, min(len(pull_requests) * int(wait_seconds_per_pr) + 300, 86_400)),
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_main_ruleset_apply(owner_approved: bool = False) -> dict[str, Any]:
    """Create or reconcile the active main ruleset and verify exact GitHub readback."""
    return broker.call(
        "github_main_ruleset_apply",
        {"owner_approved": owner_approved},
        timeout=180,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_update_pr(
    pr_number: int,
    expected_head_sha: str,
    title: str = "",
    body: str = "",
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Update title or body of one exact open PR after explicit owner approval."""
    return broker.call(
        "github_update_pr",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "title": title,
            "body": body,
            "owner_approved": owner_approved,
        },
        timeout=120,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_reopen_pr(
    pr_number: int,
    expected_head_sha: str,
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Reopen one exact closed and unmerged PR after explicit owner approval."""
    return broker.call(
        "github_reopen_pr",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "owner_approved": owner_approved,
        },
        timeout=120,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_close_pr(
    pr_number: int,
    expected_head_sha: str,
    closure_reason: str = "redundant",
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Close one exact redundant or superseded PR without merging it."""
    return broker.call(
        "github_close_pr",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "closure_reason": closure_reason,
            "owner_approved": owner_approved,
        },
        timeout=120,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def repository_delete_pr_branch(
    pr_number: int,
    expected_head_sha: str,
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Delete a completed PR head branch; main, master, default and base branches are permanently protected."""
    return broker.call(
        "github_delete_pr_branch",
        {
            "pr_number": pr_number,
            "expected_head_sha": expected_head_sha,
            "owner_approved": owner_approved,
        },
        timeout=120,
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
        if "repository_push_main" in active or "repository_merge_pr" in active or "repository_merge_pr_series" in active:
            blocked = [item for item in blocked if item != "direct_main_write"]
        policy["blocked_capabilities"] = blocked
        policy["active_private_admin_capabilities"] = active
    return result


def _live_mcp_registry_evidence() -> dict[str, Any]:
    """Return bounded live registry identity without exposing full tool contracts."""
    names = sorted(
        str(getattr(tool, "name", ""))
        for tool in mcp._tool_manager.list_tools()
        if str(getattr(tool, "name", ""))
    )
    canonical = json.dumps(names, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {
        "registry_tool_count": len(names),
        "registry_tool_names_sha256": hashlib.sha256(canonical).hexdigest(),
        "registry_runtime_verified": True,
    }


@mcp.tool(annotations=READ_ONLY)
def mcp_control_plane_status() -> dict[str, Any]:
    """Probe the broker and bind it to the live FastMCP registry identity."""
    status = dict(broker.status())
    status.update(_live_mcp_registry_evidence())
    return status


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
def controller_run_start(
    mission: str,
    evidence: str = "",
    mode: str = "paid",
    intent_mode: str = "auto",
) -> dict[str, Any]:
    """Start one owner-scoped persisted paid or FreeLLM run with bounded non-secret input."""
    return controller_runtime.start_run(
        mission=mission,
        evidence=evidence,
        mode=mode,
        intent_mode=intent_mode,
    )


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
    """Convert one ephemeral DOCX through Gotenberg LibreOffice and verify its marker through Tika."""
    return broker.call(
        "document_pipeline_live_canary",
        {"marker": marker},
        timeout=120,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def github_knowledge_live_canary(
    expected_revision: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{40}$", description="Exact running backend source revision."),
    ],
    expected_image_digest: Annotated[
        str,
        Field(pattern=r"^sha256:[0-9a-f]{64}$", description="Exact running immutable backend image digest."),
    ],
) -> dict[str, Any]:
    """Import one public GitHub source, verify pgvector/provenance and safely clean all canary data."""
    return broker.call(
        "github_knowledge_live_canary",
        {
            "expected_revision": expected_revision,
            "expected_image_digest": expected_image_digest,
        },
        timeout=480,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def issue_closure_runtime_canary(
    expected_revision: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{40}$", description="Exact running backend source revision."),
    ],
    expected_image_digest: Annotated[
        str,
        Field(pattern=r"^sha256:[0-9a-f]{64}$", description="Exact running immutable backend image digest."),
    ],
    baseline_revision: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{40}$", description="Revision at which the missing runtime schema was observed."),
    ],
    release_evidence_sha256: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the exact-head release evidence bundle."),
    ],
    patchmon_evidence_sha256: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{64}$", description="Hash of the post-deploy PatchMon evidence bundle."),
    ],
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Persist and read back the bounded closure evidence for Issues 1111, 1117 and 1120."""
    return broker.call(
        "issue_closure_runtime_canary",
        {
            "expected_revision": expected_revision,
            "expected_image_digest": expected_image_digest,
            "baseline_revision": baseline_revision,
            "release_evidence_sha256": release_evidence_sha256,
            "patchmon_evidence_sha256": patchmon_evidence_sha256,
            "owner_approved": owner_approved,
        },
        timeout=360,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def programming_language_catalog_persistent_import(
    expected_revision: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{40}$", description="Exact running backend source revision."),
    ],
    expected_image_digest: Annotated[
        str,
        Field(pattern=r"^sha256:[0-9a-f]{64}$", description="Exact running immutable backend image digest."),
    ],
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Persist the pinned ProgrammiersprachenMD catalog and verify dedupe, pgvector and API projection readback."""
    return broker.call(
        "programming_language_catalog_persistent_import",
        {
            "expected_revision": expected_revision,
            "expected_image_digest": expected_image_digest,
            "owner_approved": owner_approved,
        },
        timeout=1020,
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
def fleet_filebrowser_retirement_plan() -> dict[str, Any]:
    """Plan retirement of the one fixed owner-retired Filebrowser container while preserving its image and volumes."""
    return broker.call("fleet_filebrowser_retirement_plan", {}, timeout=60)


@mcp.tool(annotations=EXTERNAL_WRITE)
def fleet_filebrowser_retirement_apply(
    confirmation_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Remove only the exact confirmed Filebrowser container through the host queue; never remove images or volumes."""
    return broker.call(
        "fleet_filebrowser_retirement_apply",
        {"confirmation_sha256": confirmation_sha256, "owner_approved": owner_approved},
        timeout=180,
    )


@mcp.tool(annotations=READ_ONLY)
def host_postgres_backup_restore_plan(
    patch_run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
) -> dict[str, Any]:
    """Bind a real PostgreSQL backup and isolated restore check to one pending PatchMon run."""
    return broker.call(
        "host_postgres_backup_restore_plan",
        {"patch_run_id": patch_run_id},
        timeout=180,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def host_postgres_backup_restore_apply(
    patch_run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
    confirmation_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Create a retained pg_dump, restore it into an isolated database, compare metadata and row counts, then remove the restore target."""
    return broker.call(
        "host_postgres_backup_restore_apply",
        {
            "patch_run_id": patch_run_id,
            "confirmation_sha256": confirmation_sha256,
            "owner_approved": owner_approved,
        },
        timeout=1800,
    )


@mcp.tool(annotations=READ_ONLY)
def host_reboot_plan(
    patch_run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
    backup_receipt_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
) -> dict[str, Any]:
    """Plan one reboot only after successful PatchMon, retained restore evidence, zero upgrades and healthy core containers."""
    return broker.call(
        "host_reboot_plan",
        {"patch_run_id": patch_run_id, "backup_receipt_sha256": backup_receipt_sha256},
        timeout=180,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def host_reboot_apply(
    patch_run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
    backup_receipt_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    confirmation_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Schedule one delayed systemd reboot through the host queue after exact state confirmation."""
    return broker.call(
        "host_reboot_apply",
        {
            "patch_run_id": patch_run_id,
            "backup_receipt_sha256": backup_receipt_sha256,
            "confirmation_sha256": confirmation_sha256,
            "owner_approved": owner_approved,
        },
        timeout=180,
    )


@mcp.tool(annotations=READ_ONLY)
def host_post_reboot_verify(
    expected_previous_boot_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
    patch_run_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")],
    backup_receipt_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
) -> dict[str, Any]:
    """Verify boot-ID change, PatchMon success, retained backup, zero upgrades and healthy core containers after reboot."""
    return broker.call(
        "host_post_reboot_verify",
        {
            "expected_previous_boot_id": expected_previous_boot_id,
            "patch_run_id": patch_run_id,
            "backup_receipt_sha256": backup_receipt_sha256,
        },
        timeout=180,
    )


@mcp.tool(annotations=READ_ONLY)
def managed_compose_stack_plan(stack_id: str) -> dict[str, Any]:
    """Read template hashes and runtime evidence for one allowlisted managed Compose stack."""
    return broker.call("managed_compose_stack_plan", {"stack_id": stack_id}, timeout=60)


@mcp.tool(annotations=EXTERNAL_WRITE)
def memory_gateway_collection_canary() -> dict[str, Any]:
    """Create, write, query, search and drop one ephemeral Milvus collection through the existing gateway container."""
    return broker.call("memory_gateway_collection_canary", {}, timeout=240)


def wolfram_cag_status() -> dict[str, Any]:
    """Internal CAG status helper; public MCP access is via runtime_dependency_health_matrix."""
    return provider_runtime.wolfram_cag_status()


def wolfram_cag_canary(components: list[str] | None = None) -> dict[str, Any]:
    """Internal fixed CAG canary helper; public MCP access is via runtime_dependency_health_matrix."""
    return provider_runtime.wolfram_cag_canary(components)


@mcp.tool(annotations=NETWORK_READ)
def openrouter_provider_status() -> dict[str, Any]:
    """Read secret-free status and canary metadata for the direct OpenRouter transport."""
    return provider_runtime.openrouter_status()


@mcp.tool(annotations=EXTERNAL_WRITE)
def openrouter_provider_activate(
    route_id: str = "openrouter-paid-gpt-5-4-mini",
) -> dict[str, Any]:
    """Activate the direct paid OpenRouter route; no secret argument is accepted."""
    return provider_runtime.openrouter_activate(route_id)


@mcp.tool(annotations=NETWORK_READ)
def openrouter_free_status() -> dict[str, Any]:
    """Read secret-free OpenRouter-Free route, key-state and quota-contract evidence."""
    return provider_runtime.openrouter_free_status()


@mcp.tool(annotations=EXTERNAL_WRITE)
def openrouter_free_activate() -> dict[str, Any]:
    """Activate openrouter/free only after two zero-cost generation receipts; no secret argument is accepted."""
    return provider_runtime.openrouter_free_activate()


@mcp.tool(annotations=EXTERNAL_WRITE)
def openrouter_free_key_rotate() -> dict[str, Any]:
    """Create and verify one zero-limit Free execution key with the protected management key, then retire old exact hashes."""
    return provider_runtime.openrouter_free_key_rotate()


def _retired_litellm_tool(replacement: str) -> dict[str, Any]:
    return {
        "ok": False,
        "status": "RETIRED",
        "blocker": "legacy_litellm_runtime_retired",
        "replacement": replacement,
        "mutationPerformed": False,
        "secretValuesReturned": False,
    }


@mcp.tool(annotations=READ_ONLY)
def litellm_provider_model_inventory() -> dict[str, Any]:
    """Retired compatibility tombstone; use openrouter_provider_status."""
    return _retired_litellm_tool("openrouter_provider_status")


@mcp.tool(annotations=READ_ONLY)
def litellm_provider_deployments() -> dict[str, Any]:
    """Retired compatibility tombstone; use openrouter_provider_status."""
    return _retired_litellm_tool("openrouter_provider_status")


@mcp.tool(annotations=READ_ONLY)
def litellm_provider_route_activate(route_id: str) -> dict[str, Any]:
    """Retired compatibility tombstone; use openrouter_provider_activate."""
    del route_id
    return _retired_litellm_tool("openrouter_provider_activate")


@mcp.tool(annotations=NETWORK_READ)
def freellm_provider_status() -> dict[str, Any]:
    """Read secret-free managed FreeLLM key, catalog and ready-route metadata."""
    return provider_runtime.freellm_status()


@mcp.tool(annotations=EXTERNAL_WRITE)
def freellm_provider_keyless_activate(provider_id: str) -> dict[str, Any]:
    """Configure one currently allowlisted keyless FreeLLMAPI marker; readiness still requires a double-canary."""
    return provider_runtime.freellm_keyless_activate(provider_id)


@mcp.tool(annotations=EXTERNAL_WRITE)
def freellm_provider_discover(source_id: str, max_models: int = 20) -> dict[str, Any]:
    """Fetch a fresh authenticated managed catalog and double-canary eligible FreeLLM models."""
    return provider_runtime.freellm_discover(source_id, max_models=max_models)


@mcp.tool(annotations=EXTERNAL_WRITE)
def freellm_provider_recheck(source_id: str, max_models: int = 20) -> dict[str, Any]:
    """Repeat direct fail-closed canaries for managed FreeLLM candidates."""
    return provider_runtime.freellm_reconcile(source_id, max_models=max_models)


@mcp.tool(annotations=READ_ONLY)
def litellm_model_aliases_activate(
    fast_provider_model: str,
    balanced_provider_model: str,
    confirmation_inventory_sha256: str,
) -> dict[str, Any]:
    """Retired compatibility tombstone; direct OpenRouter routes use their persisted model IDs."""
    del fast_provider_model, balanced_provider_model, confirmation_inventory_sha256
    return _retired_litellm_tool("openrouter_provider_activate")


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
    """Plan one allowlisted PatchMon action, including fixed bootstrap_local_fleet compatibility, against current state."""
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
    """Submit one exact state-bound PatchMon action, including fixed bootstrap_local_fleet compatibility, through the host queue."""
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


@mcp.tool(annotations=READ_ONLY)
def patchmon_fleet_bootstrap_plan(friendly_name: str = "sovereign-vps") -> dict[str, Any]:
    """Plan exact local PatchMon host enrollment, agent installation and Docker inventory collection."""
    return broker.call(
        "patchmon_fleet_bootstrap_plan",
        {"friendly_name": friendly_name},
        timeout=180,
    )


@mcp.tool(annotations=EXTERNAL_WRITE)
def patchmon_fleet_bootstrap_apply(
    confirmation_sha256: str,
    friendly_name: str = "sovereign-vps",
    owner_approved: bool = False,
) -> dict[str, Any]:
    """Apply one confirmed local PatchMon fleet bootstrap through the host command queue."""
    return broker.call(
        "patchmon_fleet_bootstrap_apply",
        {
            "confirmation_sha256": confirmation_sha256,
            "friendly_name": friendly_name,
            "owner_approved": owner_approved,
        },
        timeout=360,
    )


def _patchmon_workflow_green(payload: Any) -> bool:
    evidence = payload if isinstance(payload, dict) else {}
    allowed = {"success", "successful", "neutral", "skipped"}

    jobs = evidence.get("jobs")
    if (
        evidence.get("passed") is True
        and evidence.get("validation_complete") is True
        and str(evidence.get("run_status") or "").strip().lower() == "completed"
        and str(evidence.get("conclusion") or "").strip().lower() in {"success", "successful"}
        and isinstance(jobs, list)
        and bool(jobs)
    ):
        job_conclusions = []
        for item in jobs:
            job = item if isinstance(item, dict) else {}
            if str(job.get("status") or "").strip().lower() != "completed":
                return False
            job_conclusions.append(str(job.get("conclusion") or "").strip().lower())
        return bool(job_conclusions) and all(item in allowed for item in job_conclusions)

    containers = [evidence]
    nested_checks = evidence.get("checks")
    if isinstance(nested_checks, dict):
        containers.append(nested_checks)

    for container in containers:
        for key in (
            "checksGreen",
            "checks_green",
            "allChecksGreen",
            "all_checks_green",
            "relevantChecksGreenClaimed",
        ):
            if container.get(key) is True:
                return True

    checks: list[Any] = []
    for container in containers:
        candidate = container.get("checks")
        if isinstance(candidate, list):
            checks = candidate
            break
    if not checks:
        return False

    conclusions = []
    for item in checks:
        check = item if isinstance(item, dict) else {}
        conclusion = str(check.get("conclusion") or check.get("status") or "").strip().lower()
        conclusions.append(conclusion)
    return bool(conclusions) and all(item in allowed for item in conclusions)


def _patchmon_revision_from_payload(payload: Any) -> str:
    evidence = payload if isinstance(payload, dict) else {}
    for key in ("headSha", "head_sha", "prHeadSha", "mergeCommitSha", "merge_commit_sha", "mergedChangeSha"):
        value = str(evidence.get(key) or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{40}", value):
            return value
    nested = evidence.get("pullRequest") if isinstance(evidence.get("pullRequest"), dict) else {}
    return _patchmon_revision_from_payload(nested) if nested else ""


def _patchmon_revision_binding(
    expected_revision: str,
    pr_evidence: Any,
    workflow_runs: list[Any],
) -> tuple[str, bool, str]:
    expected = str(expected_revision or "").strip().lower()
    if workflow_runs:
        revisions = [_patchmon_revision_from_payload(item) for item in workflow_runs]
        observed = next((item for item in revisions if item), "")
        bound = bool(
            expected
            and len(revisions) == len(workflow_runs)
            and all(item == expected for item in revisions)
        )
        return observed, bound, "workflow_runs"

    pull = pr_evidence if isinstance(pr_evidence, dict) else {}
    state = str(pull.get("state") or "").strip().lower()
    merged = bool(pull.get("merged")) or bool(pull.get("merged_at"))
    merge_revision = str(
        pull.get("merge_commit_sha")
        or pull.get("mergeCommitSha")
        or pull.get("mergedChangeSha")
        or ""
    ).strip().lower()
    head_revision = str(
        pull.get("head_sha")
        or pull.get("headSha")
        or pull.get("prHeadSha")
        or ""
    ).strip().lower()

    if merged or (state == "closed" and re.fullmatch(r"[0-9a-f]{40}", merge_revision)):
        observed = merge_revision if re.fullmatch(r"[0-9a-f]{40}", merge_revision) else ""
        return observed, bool(expected and observed == expected), "pull_request_merge_commit"

    observed = head_revision if re.fullmatch(r"[0-9a-f]{40}", head_revision) else ""
    return observed, bool(expected and observed == expected), "pull_request_head"


@mcp.tool(annotations=NETWORK_READ)
def patchmon_fleet_orchestrator_status(
    expected_revision: str = "",
    pr_number: int = 0,
    workflow_run_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Bind real PatchMon fleet evidence to current repository workflow and immutable revision status."""
    revision = str(expected_revision or "").strip().lower()
    if revision and not re.fullmatch(r"[0-9a-f]{40}", revision):
        return {"ok": False, "status": "BLOCKED", "blocker": "expected_revision must be a full commit SHA"}
    patchmon = broker.call("patchmon_brain_snapshot", {"include_fleet": True}, timeout=180)
    summary_rows = patchmon.get("databaseSummary", {}).get("rows", []) if isinstance(patchmon, dict) else []
    summary = dict(summary_rows[0]) if summary_rows else {}
    hosts_active = int(summary.get("hosts_active") or 0)
    docker_observed = int(summary.get("docker_containers_observed") or 0)
    host_lane_ready = bool(patchmon.get("ok")) and hosts_active > 0 and docker_observed > 0

    pr_evidence: dict[str, Any] | None = None
    if int(pr_number or 0) > 0:
        pr_evidence = broker.call("github_pr_status", {"pr_number": int(pr_number)}, timeout=60)
    runs = []
    for run_id in (workflow_run_ids or [])[:20]:
        if int(run_id) <= 0:
            continue
        runs.append(broker.call("github_workflow_run_status", {"run_id": int(run_id)}, timeout=60))
    workflow_evidence = [item for item in ([pr_evidence] if pr_evidence else []) + runs if isinstance(item, dict)]
    workflow_green = bool(workflow_evidence) and all(_patchmon_workflow_green(item) for item in workflow_evidence)
    observed_revision, revision_bound, revision_source = _patchmon_revision_binding(
        revision,
        pr_evidence or {},
        runs,
    )
    rollout_ready = host_lane_ready and workflow_green and revision_bound
    return {
        "ok": rollout_ready,
        "status": "PATCHMON_FLEET_ORCHESTRATOR_READY" if rollout_ready else "PATCHMON_FLEET_ORCHESTRATOR_GATED",
        "patchmonLane": {
            "ready": host_lane_ready,
            "hostsActive": hosts_active,
            "dockerContainersObserved": docker_observed,
            "evidence": patchmon,
        },
        "immutableContainerLane": {
            "owner": "existing_revision_bound_image_deploy_path",
            "patchMonMutatesContainerRevision": False,
            "expectedRevision": revision or None,
            "observedRepositoryRevision": observed_revision or None,
            "revisionEvidenceSource": revision_source,
            "prHeadRevision": _patchmon_revision_from_payload(pr_evidence or {}) or None,
            "revisionBound": revision_bound,
            "workflowGreen": workflow_green,
            "prEvidence": pr_evidence,
            "workflowRuns": runs,
        },
        "rolloutReady": rollout_ready,
        "mutationPerformed": False,
        "secretValuesExposed": False,
        "nextAction": None if rollout_ready else "Resolve the false PatchMon, workflow or revision gate before any staged rollout",
    }


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


if os.getenv("SOVEREIGN_MCP_ENABLE_AURION_OPERATOR", "0").strip() == "1":
    @mcp.tool(annotations=NETWORK_READ)
    def aurion_account_role_readback(
        open_id: Annotated[
            str,
            Field(pattern=r"^local:[A-Za-z0-9_.-]{1,32}$", description="Exact local Aurion openId; never a credential."),
        ],
        expected_revision: Annotated[
            str,
            Field(pattern=r"^[0-9a-f]{40}$", description="Exact running Echoes of Aurion source revision."),
        ],
    ) -> dict[str, Any]:
        """Read only id/openId/role for one local Aurion account from the exact healthy runtime."""
        return broker.call(
            "aurion_account_role_readback",
            {"open_id": open_id, "expected_revision": expected_revision},
            timeout=90,
        )


    @mcp.tool(annotations=NETWORK_READ)
    def aurion_account_role_plan(
        open_id: Annotated[str, Field(pattern=r"^local:[A-Za-z0-9_.-]{1,32}$")],
        role: Annotated[str, Field(pattern=r"^(?:user|admin)$")],
        expected_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")],
    ) -> dict[str, Any]:
        """Bind one local Aurion role change to the exact users row and runtime without mutating data."""
        return broker.call(
            "aurion_account_role_plan",
            {"open_id": open_id, "role": role, "expected_revision": expected_revision},
            timeout=90,
        )


    @mcp.tool(annotations=EXTERNAL_WRITE)
    def aurion_account_role_apply(
        open_id: Annotated[str, Field(pattern=r"^local:[A-Za-z0-9_.-]{1,32}$")],
        role: Annotated[str, Field(pattern=r"^(?:user|admin)$")],
        expected_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")],
        confirmation_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
        owner_approved: bool = False,
    ) -> dict[str, Any]:
        """Queue one hash-bound local Aurion users.role update and require DB plus runtime readback."""
        return broker.call(
            "aurion_account_role_apply",
            {
                "open_id": open_id,
                "role": role,
                "expected_revision": expected_revision,
                "confirmation_sha256": confirmation_sha256,
                "owner_approved": owner_approved,
            },
            timeout=180,
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
    canary_ok = bool(
        isinstance(canary, dict)
        and canary.get("ok")
        and deployment.get("readbackVerified") is True
        and deployment.get("actualRevision") == expected_revision
    )
    return {
        **deployment,
        "ok": canary_ok,
        "status": (
            "DEPLOYED_ADMIN_AND_A2A_VERIFIED"
            if canary_ok
            else "DEPLOYED_A2A_EVIDENCE_INCOMPLETE"
        ),
        "a2aCanary": canary,
    }


@mcp.tool(annotations=EXTERNAL_WRITE)
def deploy_verified_backend_release(image_digest: str, expected_revision: str, confirmation_revision: str) -> dict[str, Any]:
    """Deploy one immutable backend digest and require admin, rollback and owner-scoped A2A evidence."""
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
register_sovereign_rescue_widget(mcp, read_only_annotations=READ_ONLY)
register_sovereign_cognitive_widget(
    mcp,
    read_only_annotations=READ_ONLY,
    status_provider=_cognitive_architecture_status,
)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
