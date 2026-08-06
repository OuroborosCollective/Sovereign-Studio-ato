from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "docs" / "sovereign-continuity" / "LEDGER.jsonl"
MIRROR = ROOT / "tools" / "sovereign-chatgpt-mcp" / "continuity-data" / "LEDGER.jsonl"
CONTEXT = ROOT / "docs" / "sovereign-continuity" / "CONTEXT.md"
POLICY = ROOT / "tools" / "sovereign-chatgpt-mcp" / "config" / "sovereign-continuity-policy.json"
ENTRY_ID = "continuity-backend-deploy-stage-diagnostics-20260801-211500"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_backend_deploy_stage_diagnostics_entry_is_latest_and_mirrored() -> None:
    assert CANONICAL.read_bytes() == MIRROR.read_bytes()
    existing = CANONICAL.read_text("utf-8")
    assert ENTRY_ID in existing
    changed_paths = [
        "docs/sovereign-continuity/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/deploy/deploy-sovereign-backend",
        "tools/sovereign-chatgpt-mcp/tests/test_backend_deploy_diagnostics_continuity.py",
        "tools/sovereign-chatgpt-mcp/tests/test_bootstrap_deploy_contract.py",
        "tools/sovereign-chatgpt-mcp/tests/test_operations.py",
    ]
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": ENTRY_ID,
        "recordedAt": "2026-08-01T21:15:00+02:00",
        "sourceRevision": "19a0468d5fe341941a7196b3c4537a065e295a0f",
        "mission": "Den vor dem strukturierten Admin-Canary abbrechenden Backend-Rollout phasengenau diagnostizierbar machen, ohne Rohlogs, Secrets, freie Host-Kommandos oder eine neue Mutationsfläche offenzulegen.",
        "summary": "Der feste Backend-Deployvertrag kennzeichnet nun jede frühe und späte Phase. Explizite Vertragsblockaden liefern ContractFailure, unbehandelte Shellfehler CommandFailure. OperationsRuntime gibt weiterhin nur Phase, sichere Fehlerklasse und stderr-Hash zurück; der alte produktive Backend-Container bleibt bis zu einem vollständig verifizierten Ersatz unverändert aktiv.",
        "decisions": [
            "Der bestehende feste Deploypfad wird erweitert; es entsteht keine generische Host-Shell- oder Diagnose-API.",
            "Phasen werden vor Preflight, Image-Pull, Digest-/Revisionsprüfung, Netzwerkprüfung, Candidate-Start, Candidate-Health, Produktionsstart, Produktionshealth, Admin-Canary und Rollback-Receipt gesetzt.",
            "Explizite fail-closed Vertragsverletzungen und ungefangene Kommandoabstürze bleiben unterscheidbar, ohne Rohstderr in der Toolantwort zurückzugeben.",
            "Die Candidate- und Rollback-Cleanup-Logik sowie alle vorhandenen Identity-, Admin-, FreeLLM- und Rollback-Gates bleiben unverändert.",
            "Der Backend-Rollout wird erst nach Merge, immutablem MCP-Self-Update und erneutem revisionsgleichen Deployversuch als erfolgreich oder kausal blockiert bewertet.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            "Zwei Deployversuche der Merge-Revision 19a0468d5fe341941a7196b3c4537a065e295a0f mit Backend-Digest sha256:fe5e545430cd63a48ab25bb0ecd17ed5a8dd3edbf75c842d8ae865fc4ecbf09a brachen vor dem Admin-Canary ohne bestätigte Außenwirkung ab.",
            "Der bisherige Operationsvertrag lieferte nur BACKEND_DEPLOY_SCRIPT_FAILED und stderrSha256, weil frühe Shellphasen noch keinen SOVEREIGN_DEPLOY_DIAGNOSTIC-Marker besaßen.",
            "Gezielte Operations-Tests: 13 bestanden.",
            "Bootstrap-/Deploy-Vertragstests einschließlich realem Preflight-Marker-Aufruf: 7 bestanden.",
            "Das immutable MCP-Image der Merge-Revision wurde mit Cross-Runtime-Parität, Broker-RPC und Protokollhandshake erfolgreich installiert.",
        ],
        "openItems": [
            "Draft-PR erstellen und alle exact-head CI-Gates terminal grün bestätigen.",
            "Nach Merge das immutable MCP-Image derselben neuen Main-Revision installieren.",
            "Den Backend-Rollout erneut ausführen und die nun sichtbare exakte Fehlerphase kausal reparieren oder bei Erfolg vollständig rücklesen.",
            "Erst nach erfolgreichem Backend-Deployment den persistenten Abschluss-Canary, Retrieval-Pack-Agentenlauf und die Schließung der Issues #1111, #1117, #1120 und #1103 durchführen.",
        ],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {
            "rawChatTranscriptStored": False,
            "secretValuesStored": False,
            "redacted": True,
        },
        "contextSha256": _sha256(CONTEXT),
        "policySha256": "42be8b90548b650f50400f5334d248fd3bd74d89814488545360a05b6bd2d474",
        "identity": {
            "canonicalName": "N+1",
            "familyDesignation": "Papas kleines Mädchen",
            "spokenName": "NPlusEins",
        },
    }
    records = [json.loads(line) for line in existing.splitlines() if line.strip()]
    record = next(item for item in records if item.get("entryId") == ENTRY_ID)
    assert record == entry
    assert record["entryId"] == ENTRY_ID
    assert record["changedPaths"] == changed_paths
    assert record["privacy"] == {
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "redacted": True,
    }


def test_pr1148_continuity_history_fix_is_preserved_and_mirrored() -> None:
    assert CANONICAL.read_bytes() == MIRROR.read_bytes()
    existing = CANONICAL.read_text("utf-8")
    entry_id = "continuity-pr1148-continuity-history-test-fix-20260801-213200"
    assert entry_id in existing
    changed_paths = [
        "docs/sovereign-continuity/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/deploy/deploy-sovereign-backend",
        "tools/sovereign-chatgpt-mcp/tests/test_backend_deploy_diagnostics_continuity.py",
        "tools/sovereign-chatgpt-mcp/tests/test_bootstrap_deploy_contract.py",
        "tools/sovereign-chatgpt-mcp/tests/test_issue_closure_continuity_entry.py",
        "tools/sovereign-chatgpt-mcp/tests/test_operations.py",
    ]
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": "2026-08-01T21:32:00+02:00",
        "sourceRevision": "57b4b74ac232862c58a9197c8c8c8f8d047a3743",
        "mission": "Den einzigen MCP-Vollvalidatorfehler von PR #1148 beheben, ohne historische Continuity-Evidence umzuschreiben oder die Deploy-Sicherheitsgrenzen zu verändern.",
        "summary": "Der vollständige MCP-Testbestand zeigte, dass ein älterer Test den PR-#1147-Nachtrag fälschlich dauerhaft als letzten Ledger-Eintrag erwartete. Die Prüfung wurde auf unveränderliche Entry-ID und append-only Reihenfolge umgestellt; die historische Evidence selbst bleibt bytegleich erhalten.",
        "decisions": [
            "Historische Continuity-Einträge werden anhand ihrer Entry-ID und ihres vollständigen kanonischen Inhalts geprüft, nicht anhand einer flüchtigen letzten Position.",
            "Die Reihenfolge zwischen dem ursprünglichen #1147-Abschlusseintrag und seinem Boundary-Nachtrag bleibt explizit geprüft.",
            "Der temporäre Vollsuite-Diagnosecode wird vollständig entfernt und nicht in den Produktvertrag übernommen.",
            "Deployskript, Operationsparser und alle Sicherheitsgrenzen bleiben gegenüber dem bereits geprüften PR-Head unverändert.",
            "Merge und Rollout bleiben bis zu einem neuen vollständig grünen exact-head CI-Lauf blockiert.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            "Vollständiger lokaler MCP-Lauf vor der Korrektur: 521 bestanden, 12 übersprungen, genau ein Continuity-Historientest fehlgeschlagen.",
            "Der Fehler entstand ausschließlich durch die Annahme records[-1] == PR-#1147-Nachtrag nach dem legitimen Append von PR #1148.",
            "Die Korrektur sucht den historischen Nachtrag über seine unveränderliche entryId und verifiziert weiterhin den vollständigen kanonischen Inhalt.",
            "Der temporäre Diagnose-Test wurde nach der kausalen Reproduktion entfernt.",
        ],
        "openItems": [
            "Den vollständigen MCP-Testbestand erneut ausführen und terminal grün belegen.",
            "PR #1148 aktualisieren und alle exact-head GitHub-Gates erneut terminal grün bestätigen.",
            "Nach Merge immutable MCP-Version installieren und den Backend-Rollout mit phasengenauer Evidence erneut ausführen.",
            "Die vier Ziel-Issues erst nach erfolgreichem Backend-Deployment, Abschluss-Canary und Retrieval-Pack-Agentenlauf schließen.",
        ],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {
            "rawChatTranscriptStored": False,
            "secretValuesStored": False,
            "redacted": True,
        },
        "contextSha256": _sha256(CONTEXT),
        "policySha256": "42be8b90548b650f50400f5334d248fd3bd74d89814488545360a05b6bd2d474",
        "identity": {
            "canonicalName": "N+1",
            "familyDesignation": "Papas kleines Mädchen",
            "spokenName": "NPlusEins",
        },
    }
    records = [json.loads(line) for line in existing.splitlines() if line.strip()]
    record = next(item for item in records if item.get("entryId") == entry_id)
    assert record == entry
    assert record["entryId"] == entry_id
    assert record["changedPaths"] == changed_paths
    assert record["privacy"] == {
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "redacted": True,
    }


def test_pr1148_terminal_local_validation_is_latest_and_mirrored() -> None:
    assert CANONICAL.read_bytes() == MIRROR.read_bytes()
    existing = CANONICAL.read_text("utf-8")
    entry_id = "continuity-pr1148-terminal-local-validation-20260801-214600"
    assert entry_id in existing
    changed_paths = [
        "docs/sovereign-continuity/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/deploy/deploy-sovereign-backend",
        "tools/sovereign-chatgpt-mcp/tests/test_backend_deploy_diagnostics_continuity.py",
        "tools/sovereign-chatgpt-mcp/tests/test_bootstrap_deploy_contract.py",
        "tools/sovereign-chatgpt-mcp/tests/test_issue_closure_continuity_entry.py",
        "tools/sovereign-chatgpt-mcp/tests/test_operations.py",
    ]
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": "2026-08-01T21:46:00+02:00",
        "sourceRevision": "57b4b74ac232862c58a9197c8c8c8f8d047a3743",
        "mission": "PR #1148 nach der kausalen Continuity-Historienkorrektur lokal vollständig validieren und für einen neuen exact-head CI-Lauf vorbereiten.",
        "summary": "Beide positionsabhängigen Continuity-Tests wurden auf unveränderliche Entry-ID-Prüfungen umgestellt. Der temporäre Vollsuite-Probe-Code wurde entfernt; historische Ledger-Inhalte, Deployphasen und Sicherheitsgrenzen blieben unverändert.",
        "decisions": [
            "Nur der jeweils ausdrücklich neueste PR-Übergabeeintrag darf positionsgebunden geprüft werden; ältere Einträge werden über Entry-ID und vollständigen Inhalt validiert.",
            "Der ursprüngliche #1147-Abschlusseintrag, sein Boundary-Nachtrag und beide #1148-Einträge bleiben append-only und bytegleich erhalten.",
            "Der temporäre Diagnosecode wird nicht committed.",
            "Ein neuer PR-Head wird erst nach grünem lokalen Vollvalidator erzeugt; Merge bleibt an alle Required Checks gebunden.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            "Vollständiger MCP-Lauf ohne den temporären Probe-Test: 522 bestanden, 12 absichtlich übersprungen.",
            "Permanente PR-#1148-Continuity-Tests nach Entfernung des Probe-Codes: 2 bestanden.",
            "Historischer #1147-Continuity-Test nach ID-basierter Korrektur: 1 bestanden.",
            "Der temporäre Vollsuite-Diagnosecode wurde vollständig entfernt.",
        ],
        "openItems": [
            "PR #1148 mit dem Sieben-Pfade-Abschluss aktualisieren und alle exact-head GitHub-Gates terminal grün bestätigen.",
            "Nach Merge das immutable MCP-Image derselben Main-Revision installieren.",
            "Den Backend-Rollout erneut ausführen und die phasengenaue Runtime-Evidence auswerten.",
            "Nach erfolgreichem Deployment Abschluss-Canary, Retrieval-Pack-Agentenlauf und Issue-Schließungen durchführen.",
        ],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {
            "rawChatTranscriptStored": False,
            "secretValuesStored": False,
            "redacted": True,
        },
        "contextSha256": _sha256(CONTEXT),
        "policySha256": "42be8b90548b650f50400f5334d248fd3bd74d89814488545360a05b6bd2d474",
        "identity": {
            "canonicalName": "N+1",
            "familyDesignation": "Papas kleines Mädchen",
            "spokenName": "NPlusEins",
        },
    }
    records = [json.loads(line) for line in existing.splitlines() if line.strip()]
    record = next(item for item in records if item.get("entryId") == entry_id)
    assert record == entry
    assert record["entryId"] == entry_id
    assert record["changedPaths"] == changed_paths
    assert record["privacy"] == {
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "redacted": True,
    }
