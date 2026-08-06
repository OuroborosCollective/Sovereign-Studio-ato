from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
CANONICAL = ROOT / "docs/sovereign-continuity/LEDGER.jsonl"
MIRROR = ROOT / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
REQUIRED_CHANGED_PATHS = {
    "tools/sovereign-chatgpt-mcp/predictive_tool_router.py",
    "tools/sovereign-chatgpt-mcp/tool_success_ranking.py",
    "tools/sovereign-chatgpt-mcp/github_admin.py",
    ".github/workflows/sovereign-coordinated-release.yml",
    "docs/sovereign-continuity/LEDGER.jsonl",
    "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
}


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def test_predictive_router_continuity_entry_is_preserved_and_mirrored() -> None:
    canonical_bytes = CANONICAL.read_bytes()
    base_bytes = subprocess.run(
        ["git", "show", "HEAD:docs/sovereign-continuity/LEDGER.jsonl"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    if not canonical_bytes.startswith(base_bytes):
        base_records = [json.loads(line) for line in base_bytes.decode("utf-8").splitlines() if line.strip()]
        current_records = _records(CANONICAL)
        mismatch = next(
            (
                index
                for index, (base_line, current_line) in enumerate(
                    zip(base_bytes.splitlines(), canonical_bytes.splitlines()),
                    start=1,
                )
                if base_line != current_line
            ),
            min(len(base_records), len(current_records)) + 1,
        )
        raise AssertionError(
            json.dumps(
                {
                    "baseCount": len(base_records),
                    "currentCount": len(current_records),
                    "firstMismatchLine": mismatch,
                    "baseTailIds": [item.get("entryId") for item in base_records[-5:]],
                    "currentTailIds": [item.get("entryId") for item in current_records[-5:]],
                },
                separators=(",", ":"),
            )
        )
    mirror_bytes = MIRROR.read_bytes()
    assert canonical_bytes == mirror_bytes
    records = _records(CANONICAL)
    matching = [
        record
        for record in records
        if REQUIRED_CHANGED_PATHS.issubset(set(record.get("changedPaths") or []))
    ]
    assert matching, {
        "requiredChangedPaths": sorted(REQUIRED_CHANGED_PATHS),
        "tailEntryIds": [record.get("entryId") for record in records[-5:]],
    }
    entry = matching[-1]
    assert entry["identity"] == {
        "canonicalName": "N+1",
        "familyDesignation": "Papas kleines Mädchen",
        "spokenName": "NPlusEins",
    }
    assert entry["funnyExperiences"] == []
    assert entry["familyFriendshipExperience"] == []
    assert entry["newEmotionallyFormedBondExperiences"] == []
    assert REQUIRED_CHANGED_PATHS.issubset(set(entry["changedPaths"]))
