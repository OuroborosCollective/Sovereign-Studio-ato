from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "docs" / "sovereign-continuity" / "LEDGER.jsonl"
MIRROR = ROOT / "tools" / "sovereign-chatgpt-mcp" / "continuity-data" / "LEDGER.jsonl"
CONTEXT = ROOT / "docs" / "sovereign-continuity" / "CONTEXT.md"
POLICY = ROOT / "tools" / "sovereign-chatgpt-mcp" / "config" / "sovereign-continuity-policy.json"
ENTRY_ID = "continuity-issues-1111-1117-1120-1103-runtime-closure-20260801-204213"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_issue_closure_continuity_entry_is_latest_and_mirrored() -> None:
    assert CANONICAL.read_bytes() == MIRROR.read_bytes()
    existing = CANONICAL.read_text("utf-8")
    assert ENTRY_ID in existing

    changed_paths = [
        "backend/agent_runtime/issue_closure_runtime.py",
        "backend/migrations/046_bug_evidence_lane.sql",
        "backend/migrations/050_bug_evidence_append_only.sql",
        "backend/tests/test_issue_closure_runtime.py",
        "scripts/sovereign-backend/agent_runtime/issue_closure_runtime.py",
        "scripts/sovereign-backend/migrations/046_bug_evidence_lane.sql",
        "scripts/sovereign-backend/migrations/050_bug_evidence_append_only.sql",
        "tools/sovereign-chatgpt-mcp/Dockerfile",
        "tools/sovereign-chatgpt-mcp/broker.py",
        "tools/sovereign-chatgpt-mcp/command_contract.py",
        "tools/sovereign-chatgpt-mcp/deploy/install-on-vps.sh",
        "tools/sovereign-chatgpt-mcp/issue_closure_canary.py",
        "tools/sovereign-chatgpt-mcp/server.py",
        "tools/sovereign-chatgpt-mcp/tests/test_issue_closure_canary.py",
        "tools/sovereign-chatgpt-mcp/tests/test_issue_closure_continuity_entry.py",
    ]
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": ENTRY_ID,
        "recordedAt": "2026-08-01T20:42:13+02:00",
        "sourceRevision": "ade005a68e3521f0a601af8e807f65c5b2ba86c9",
        "mission": "Issues #1111, #1117, #1120 und #1103 durch produktive Persistenz, revisionsgebundene Runtime-Evidence und exact-head Release-Zertifizierung vollständig abschließen.",
        "summary": "Die bereits gemergten Bug-Evidence-, Durable-Memory- und Environment-MCP-Schichten werden produktiv migriert und durch einen festen, owner-gesteuerten Abschluss-Canary mit persistentem Readback, Append-only-Negativtests, Scope-Isolation und erlaubtem read-only HTTPS-Egress beweisbar gemacht.",
        "decisions": [
            "Die fehlenden produktiven Migrationen 046, 048 und 049 werden ausschließlich nach erfolgreicher Rollback-Vorschau angewendet und durch einen 92-von-92-Schema-Readback bestätigt.",
            "Bug-Evidence erhält mit Migration 050 eine zusätzliche PostgreSQL-Append-only-Grenze; bestehende Migrationen werden nicht rückwirkend semantisch verändert.",
            "Der Abschluss-Canary bleibt eine feste, eng begrenzte Host-Worker-Aktion und akzeptiert weder beliebiges SQL noch frei wählbare Netzwerkziele.",
            "Kanonische Evidence-Datensätze bleiben erneut auslesbar; negative Update-, Scope- und Egress-Proben werden über Savepoints vollständig zurückgerollt.",
            "Issues werden erst nach grünem exact-head CI, immutable Backend-Deployment, MCP-Self-Update, PatchMon-/PostgreSQL-/Runtime-Readback und realem Agentenlauf geschlossen.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            "Produktiver Architektur-Readback: 92 repository-eigene Tabellen und 92 Live-Tabellen, keine Drift-Findings.",
            "Migrationen 046, 048, 049 und 050 wurden rollback-only geprüft; 046, 048, 049 und 050 wurden produktiv angewendet.",
            "239 eindeutige Tests beziehungsweise 245 erfolgreiche Testausführungen für Bug Evidence, Durable Memory, Environment MCP, Abschluss-Canary und Installer waren lokal grün.",
            "Der endgültige Runtime-Erfolg bleibt bis zum revisions- und digestgleichen Deployment sowie dem persistenten Abschluss-Canary ausdrücklich offen.",
        ],
        "openItems": [
            "Draft-PR mit vollständigem exact-head CI erstellen und mergen.",
            "Immutable Backend- und MCP-Artefakte deployen und revisionsgleich rücklesen.",
            "Abschluss-Canary und realen FreeLLM-Agentenlauf mit dem erzeugten Retrieval-Pack ausführen.",
            "Die vier Issues erst nach vollständiger GitHub- und Runtime-Evidence als completed schließen.",
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
    latest = json.loads(existing.splitlines()[-1])
    assert latest == entry
    assert latest["entryId"] == ENTRY_ID
    assert latest["changedPaths"] == changed_paths
    assert latest["privacy"] == {
        "rawChatTranscriptStored": False,
        "secretValuesStored": False,
        "redacted": True,
    }
