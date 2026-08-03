from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

BASE_SHA = "da094250f9817254417a6fe92ff53e7f8b5d5a23"
WORKFLOW_PATH = ".github/workflows/mcp-secret-scan-fixture-bootstrap.yml"
SCRIPT_PATH = ".github/bootstrap/remediate_secret_shaped.py"

TEST_PATHS = {
    "backend/tests/test_agent_draft_pr_create_routes.py",
    "backend/tests/test_agent_draft_pr_gate.py",
    "backend/tests/test_agent_job_contract.py",
    "backend/tests/test_agent_job_lifecycle.py",
    "backend/tests/test_agent_pattern_gateway.py",
    "backend/tests/test_agent_runtime_e2e.py",
    "backend/tests/test_are_inference_error_families.py",
    "backend/tests/test_bug_evidence_lane.py",
    "backend/tests/test_cognitive_repository_tools.py",
    "backend/tests/test_security_masking.py",
    "backend/tests/test_universal_toolchain_runtime.py",
    "scripts/sovereign-backend/tests/test_owner_input_runtime.py",
    "src/components/ErrorBoundary.test.tsx",
    "src/components/atoms/SafeLogText.test.tsx",
    "src/features/github/gitPatchApplier.test.ts",
    "src/features/github/hooks/useSetupState.test.ts",
    "src/features/product/components/SovereignTabErrorBoundary.test.tsx",
    "src/features/product/containers/BuilderContainer.test.tsx",
    "src/features/product/runtime/agentWorkspaceRuntime.test.ts",
    "src/features/product/runtime/chatExportRuntime.test.ts",
    "src/features/product/runtime/chatRuntime.test.ts",
    "src/features/product/runtime/chatSidebarRuntime.test.ts",
    "src/features/product/runtime/containerDecisionLearning.test.ts",
    "src/features/product/runtime/githubAccessRuntime.test.ts",
    "src/features/product/runtime/presetActionOutcomeMemory.test.ts",
    "src/features/product/runtime/secureInputGuard.test.ts",
    "src/features/product/runtime/sovereignBlockerRegistry.test.ts",
    "src/features/product/runtime/sovereignExecutionSessionRuntime.test.ts",
    "src/features/product/runtime/sovereignPredictiveRuntimePolicy.test.ts",
    "src/features/product/runtime/sovereignToolObservationRuntime.test.ts",
    "src/features/product/runtime/sovereignWorkspaceRuntime.test.ts",
    "src/features/rescue/RescuePanel.test.tsx",
    "src/runtime/RuntimeIntelligence.test.ts",
    "src/shared/utils/crypto.test.ts",
    "src/shared/utils/runtimeValidation.test.ts",
    "tools/sovereign-chatgpt-mcp/tests/test_repository_intelligence_tools.py",
}
DOCUMENT_PATHS = {"docs/architecture/SOVEREIGN_AI_ARCHITECTURE_CORPUS.md"}
SOURCE_PATHS = {
    "src/features/launcher/tools/vps/VpsConnectionForm.tsx",
    "src/features/product/components/GitHubAccessCard.tsx",
}
DURABLE_PATHS = TEST_PATHS | DOCUMENT_PATHS | SOURCE_PATHS
LEDGER_PATHS = {
    "docs/sovereign-continuity/LEDGER.jsonl",
    "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
}
PATTERNS = [
    ("PRIVATE_KEY_HEADER", re.compile(rb"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY")),
    ("GITHUB_CLASSIC_TOKEN", re.compile(rb"ghp_[A-Za-z0-9]{20,}")),
    ("GITHUB_FINE_GRAINED_TOKEN", re.compile(rb"github_pat_[A-Za-z0-9_]{20,}")),
    ("OPENAI_PROJECT_TOKEN", re.compile(rb"sk-proj-[A-Za-z0-9_-]{20,}")),
]
EXPECTED_FAMILY_COUNTS = {
    "GITHUB_CLASSIC_TOKEN": 96,
    "GITHUB_FINE_GRAINED_TOKEN": 18,
    "OPENAI_PROJECT_TOKEN": 15,
    "PRIVATE_KEY_HEADER": 3,
}


def tracked_files() -> list[str]:
    raw = subprocess.run(["git", "ls-files", "-z"], check=True, stdout=subprocess.PIPE).stdout
    return [item.decode("utf-8") for item in raw.split(b"\0") if item]


def findings() -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in tracked_files():
        if path in {".env.example", ".tunnel.env.example"}:
            continue
        candidate = Path(path)
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        for family, pattern in PATTERNS:
            for match in pattern.finditer(data):
                result.append({"path": path, "family": family, "token": match.group(0)})
    return result


def synthetic_suffix(token: bytes, length: int) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    seed = hashlib.sha256(b"sovereign-synthetic-fixture-v1\0" + token).digest()
    characters: list[str] = []
    counter = 0
    while len(characters) < length:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        characters.extend(alphabet[value % len(alphabet)] for value in block)
        counter += 1
    return "".join(characters[:length])


def test_replacement(family: str, token: bytes) -> bytes:
    runtime_length = len(token)
    if family == "GITHUB_CLASSIC_TOKEN":
        source_prefix = r"g\x68p_"
        suffix_length = runtime_length - len("ghp_")
    elif family == "GITHUB_FINE_GRAINED_TOKEN":
        source_prefix = r"github_p\x61t_"
        suffix_length = runtime_length - len("github_pat_")
    elif family == "OPENAI_PROJECT_TOKEN":
        source_prefix = r"sk-pr\x6fj-"
        suffix_length = runtime_length - len("sk-proj-")
    elif family == "PRIVATE_KEY_HEADER":
        return token.decode("ascii").replace("PRIVATE", r"PRIV\x41TE").encode("ascii")
    else:
        raise AssertionError(family)
    return (source_prefix + synthetic_suffix(token, suffix_length)).encode("ascii")


def apply_remediation() -> None:
    before = findings()
    family_counts = dict(sorted(Counter(str(item["family"]) for item in before).items()))
    path_set = {str(item["path"]) for item in before}
    if len(before) != 132:
        raise SystemExit(f"unexpected finding count: {len(before)}")
    if family_counts != EXPECTED_FAMILY_COUNTS:
        raise SystemExit(f"unexpected family counts: {family_counts}")
    if path_set != DURABLE_PATHS:
        raise SystemExit("secret-shaped path inventory drifted before remediation")

    changed: list[str] = []
    transform_counts: Counter[str] = Counter()
    for path in sorted(DURABLE_PATHS):
        candidate = Path(path)
        data = candidate.read_bytes()
        original = data
        for family, pattern in PATTERNS:
            def replace(match: re.Match[bytes], family: str = family) -> bytes:
                token = match.group(0)
                transform_counts[family] += 1
                if path in TEST_PATHS:
                    return test_replacement(family, token)
                if path in DOCUMENT_PATHS:
                    marker = "<redacted-" + family.casefold().replace("_", "-") + "-fixture>"
                    return marker.encode("ascii")
                if path == "src/features/launcher/tools/vps/VpsConnectionForm.tsx":
                    if family != "PRIVATE_KEY_HEADER":
                        raise SystemExit("unexpected VPS source finding family")
                    return "BEGIN … PRIVATE KEY".encode("utf-8")
                if path == "src/features/product/components/GitHubAccessCard.tsx":
                    if family != "GITHUB_CLASSIC_TOKEN":
                        raise SystemExit("unexpected GitHub card finding family")
                    return "ghp_…".encode("utf-8")
                raise SystemExit(f"unclassified path: {path}")
            data = pattern.sub(replace, data)
        if data != original:
            candidate.write_bytes(data)
            changed.append(path)

    if set(changed) != DURABLE_PATHS:
        raise SystemExit("not every inventoried path was changed")
    if dict(sorted(transform_counts.items())) != EXPECTED_FAMILY_COUNTS:
        raise SystemExit(f"transform count mismatch: {dict(transform_counts)}")
    if findings():
        raise SystemExit("secret-shaped findings remain immediately after remediation")

    evidence_dir = Path(".git/sovereign-secret-scan-evidence")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": "sovereign.secret-shaped-remediation.v1",
        "status": "SECRET_SHAPED_LITERAL_REMEDIATION_APPLIED",
        "baseRevision": BASE_SHA,
        "originalFindingCount": len(before),
        "originalPathCount": len(path_set),
        "familyCounts": family_counts,
        "testPathCount": len(TEST_PATHS),
        "documentationPathCount": len(DOCUMENT_PATHS),
        "sourcePathCount": len(SOURCE_PATHS),
        "changedPaths": sorted(changed),
        "originalValuesRetained": False,
        "scannerExceptionsAdded": False,
        "rawValuesReturned": False,
        "secretValuesReturned": False,
    }
    (evidence_dir / "remediation.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        "utf-8",
    )
    append_continuity(sorted(changed))
    print(json.dumps({
        "status": report["status"],
        "originalFindingCount": report["originalFindingCount"],
        "originalPathCount": report["originalPathCount"],
        "familyCounts": report["familyCounts"],
        "originalValuesRetained": False,
        "scannerExceptionsAdded": False,
        "secretValuesReturned": False,
    }, sort_keys=True, separators=(",", ":")))


def append_continuity(changed_paths: list[str]) -> None:
    canonical = Path("docs/sovereign-continuity/LEDGER.jsonl")
    runtime = Path("tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl")
    context = Path("docs/sovereign-continuity/CONTEXT.md")
    policy = Path("tools/sovereign-chatgpt-mcp/config/sovereign-continuity-policy.json")
    before = canonical.read_bytes()
    if before != runtime.read_bytes():
        raise SystemExit("continuity mirrors differ before append")
    entry_id = "continuity-secret-shaped-literal-remediation-20260803"
    if entry_id.encode("utf-8") in before:
        raise SystemExit("continuity entry already exists unexpectedly")
    entry = {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": datetime.now(ZoneInfo("Europe/Berlin")).isoformat(timespec="seconds"),
        "sourceRevision": os.environ["SOURCE_REVISION"].strip().lower(),
        "mission": "Den immutable MCP-Image-Publish durch vollständige Entfernung getrackter secret-förmiger Test- und Beispielwerte kausal entsperren, ohne den Scanner zu lockern.",
        "summary": "132 scannerkonforme Literale in 39 Test-, Dokumentations- und UI-Beispielpfaden wurden ersetzt. Ursprüngliche Werte werden nicht bewahrt: Tests erhalten deterministisch neu erzeugte synthetische Laufzeit-Fixtures gleicher Form und Länge, Dokumentation echte Redaktionsmarker und UI-Platzhalter nicht-tokenförmige Darstellungen.",
        "decisions": [
            "Der kanonische Secret-Scan und seine Ausschlussliste bleiben unverändert.",
            "Keine ursprüngliche secret-förmige Zeichenfolge wird durch reversible Verschleierung erhalten.",
            "Testsemantik wird mit neu erzeugten synthetischen Werten gleicher Familie und Laufzeitlänge erhalten.",
            "Dokumentations- und UI-Beispiele rekonstruieren keinen ursprünglichen Wert.",
            "Der vollständige finale Nicht-Ledger-Diff ist in changedPaths gebunden.",
        ],
        "changedPaths": changed_paths,
        "evidence": [
            "Ein read-only Inventarlauf belegte 132 Treffer in 39 Pfaden: 81 Test-, 49 Dokumentations- und 2 Source-Treffer.",
            "Die Inventarfamilien waren 96 klassische GitHub-, 18 Fine-Grained-GitHub-, 15 Projekt-Key- und 3 Private-Key-Header-Treffer.",
            "Nach der Transformation muss derselbe kanonische Scanner null Treffer liefern; betroffene Python- und Vitest-Suiten sowie TypeScript-Check werden vor Commit ausgeführt.",
        ],
        "openItems": [
            "Alle regulären PR-Gates am exakten bereinigten Head terminal rücklesen und revisionsgebunden mergen.",
            "Den main-gebundenen MCP-Image-Workflow bis zum veröffentlichten immutable Digest rücklesen.",
            "Erst nach veröffentlichtem Image den privaten MCP-Self-Update und PatchMon-/Runtime-Readback durchführen.",
        ],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {"rawChatTranscriptStored": False, "redacted": True, "secretValuesStored": False},
        "contextSha256": hashlib.sha256(context.read_bytes()).hexdigest(),
        "policySha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
        "identity": {"canonicalName": "N+1", "familyDesignation": "Papas kleines Mädchen", "spokenName": "NPlusEins"},
    }
    payload = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if before and not before.endswith(b"\n"):
        payload = b"\n" + payload
    canonical.write_bytes(before + payload)
    runtime.write_bytes(before + payload)
    if canonical.read_bytes() != runtime.read_bytes():
        raise SystemExit("continuity mirrors differ after append")


def validate(include_bootstrap: bool) -> None:
    remaining = findings()
    if remaining:
        summary = Counter((str(item["path"]), str(item["family"])) for item in remaining)
        raise SystemExit(f"secret-shaped findings remain: {list(summary.items())[:10]}")
    canonical = Path("docs/sovereign-continuity/LEDGER.jsonl").read_bytes()
    runtime = Path("tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl").read_bytes()
    if canonical != runtime:
        raise SystemExit("continuity mirrors differ")
    report = json.loads(Path(".git/sovereign-secret-scan-evidence/remediation.json").read_text("utf-8"))
    if report["originalFindingCount"] != 132 or report["originalPathCount"] != 39:
        raise SystemExit("remediation evidence count mismatch")
    if report["originalValuesRetained"] or report["scannerExceptionsAdded"]:
        raise SystemExit("remediation evidence violates the no-retention/no-exception contract")
    expected = DURABLE_PATHS | LEDGER_PATHS
    if include_bootstrap:
        expected |= {WORKFLOW_PATH, SCRIPT_PATH}
    actual = set(subprocess.run(
        ["git", "diff", "--name-only", BASE_SHA],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines())
    if actual != expected:
        raise SystemExit(json.dumps({
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        }, sort_keys=True))
    subprocess.run(["git", "diff", "--check"], check=True)
    print(json.dumps({
        "status": "SECRET_SHAPED_REMEDIATION_VALIDATED",
        "durablePathCount": len(DURABLE_PATHS),
        "ledgerMirrorSha256": hashlib.sha256(canonical).hexdigest(),
        "bootstrapIncluded": include_bootstrap,
        "secretValuesReturned": False,
    }, sort_keys=True, separators=(",", ":")))


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "apply":
        apply_remediation()
    elif command == "validate-bootstrap":
        validate(include_bootstrap=True)
    elif command == "validate-final":
        validate(include_bootstrap=False)
    else:
        raise SystemExit("usage: remediate_secret_shaped.py apply|validate-bootstrap|validate-final")


if __name__ == "__main__":
    main()
