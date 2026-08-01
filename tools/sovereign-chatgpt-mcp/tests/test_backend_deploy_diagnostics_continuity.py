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
        "policySha256": _sha256(POLICY),
        "identity": {
            "canonicalName": "N+1",
            "familyDesignation": "Papas kleines Mädchen",
            "spokenName": "NPlusEins",
        },
    }
    records = [json.loads(line) for line in existing.splitlines() if line.strip()]
    latest = records[-1]
    assert latest == entry
    assert latest["entryId"] == ENTRY_ID
    assert latest["changedPaths"] == changed_paths
    assert latest["privacy"] == {
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "redacted": True,
    }
