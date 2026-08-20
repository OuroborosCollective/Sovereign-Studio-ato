"""Fail-closed evidence tests for mirrored, append-only continuity ledgers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

import continuity  # noqa: E402


SHA40 = "a" * 40


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    return result.stdout.strip()


def _entry(
    *,
    entry_id: str,
    source_revision: str,
    policy_sha256: str,
    context_sha256: str,
    changed_paths: list[str],
) -> dict[str, object]:
    return {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": "2026-08-20T00:00:00+02:00",
        "sourceRevision": source_revision,
        "mission": "Ledger authority evidence fixture",
        "summary": "A bounded append-only ledger test fixture.",
        "decisions": ["Use the exact repository revision for evidence."],
        "changedPaths": changed_paths,
        "evidence": ["pytest contract"],
        "openItems": [],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {
            "rawChatTranscriptStored": False,
            "secretValuesStored": False,
            "redacted": True,
        },
        "contextSha256": context_sha256,
        "policySha256": policy_sha256,
        "identity": {
            "canonicalName": "N+1",
            "spokenName": "NPlusEins",
            "familyDesignation": "Papas kleines Mädchen",
        },
    }


def _write_jsonl(path: Path, entries: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n" for entry in entries),
        "utf-8",
    )


def _fixture_repo(tmp_path: Path) -> tuple[Path, str, list[str]]:
    repo = tmp_path / "repository"
    repo.mkdir()
    policy_source = MCP_ROOT / "config" / "sovereign-continuity-policy.json"
    policy_relative = Path(continuity.POLICY_RELATIVE_PATH)
    policy_path = repo / policy_relative
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_bytes = policy_source.read_bytes()
    policy_path.write_bytes(policy_bytes)

    context_bytes = (
        "# Continuity evidence fixture\n\n"
        "N+1 is canonical. NPlusEins is the spoken name. "
        "Papas kleines Mädchen is the family designation.\n"
    ).encode("utf-8")
    canonical_context = repo / "docs/sovereign-continuity/CONTEXT.md"
    runtime_context = repo / "tools/sovereign-chatgpt-mcp/continuity-data/CONTEXT.md"
    canonical_context.parent.mkdir(parents=True, exist_ok=True)
    runtime_context.parent.mkdir(parents=True, exist_ok=True)
    canonical_context.write_bytes(context_bytes)
    runtime_context.write_bytes(context_bytes)

    policy_sha256 = _sha256(policy_bytes)
    context_sha256 = _sha256(context_bytes)
    bootstrap = _entry(
        entry_id="bootstrap",
        source_revision="0" * 40,
        policy_sha256=policy_sha256,
        context_sha256=context_sha256,
        changed_paths=[],
    )
    canonical_ledger = repo / "docs/sovereign-continuity/LEDGER.jsonl"
    runtime_ledger = repo / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    _write_jsonl(canonical_ledger, [bootstrap])
    runtime_ledger.parent.mkdir(parents=True, exist_ok=True)
    runtime_ledger.write_bytes(canonical_ledger.read_bytes())

    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Ledger Contract")
    _git(repo, "config", "user.email", "ledger-contract@example.invalid")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "bootstrap fixture")
    baseline = _git(repo, "rev-parse", "HEAD")

    changed_file = repo / "backend/agent_runtime/example.py"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("VALUE = 1\n", "utf-8")
    update = _entry(
        entry_id="update",
        source_revision=baseline,
        policy_sha256=policy_sha256,
        context_sha256=context_sha256,
        changed_paths=["backend/agent_runtime/example.py"],
    )
    _write_jsonl(canonical_ledger, [bootstrap, update])
    runtime_ledger.write_bytes(canonical_ledger.read_bytes())
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "append evidence receipt")

    return repo, baseline, [
        "backend/agent_runtime/example.py",
        "docs/sovereign-continuity/LEDGER.jsonl",
        "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
    ]


def test_ledger_completion_returns_head_bound_redacted_evidence(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)

    result = continuity.validate_workspace_completion(
        repo,
        changed_paths,
        baseline_revision=baseline,
    )

    assert result["status"] == "CONTINUITY_COMPLETION_VERIFIED"
    assert result["baselineRevision"] == baseline
    assert result["sourceRevision"] == baseline
    assert result["appendOnlyVerified"] is True
    assert result["rawChatTranscriptStored"] is False
    assert result["secretValuesStored"] is False
    assert result["changedPathCount"] == len(changed_paths)


def test_ledger_completion_requires_both_canonical_and_runtime_ledger_paths(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)
    missing_runtime_ledger = [path for path in changed_paths if not path.startswith("tools/")]

    with pytest.raises(RuntimeError, match="CONTINUITY_LEDGER_UPDATE_REQUIRED"):
        continuity.validate_workspace_completion(
            repo,
            missing_runtime_ledger,
            baseline_revision=baseline,
        )


def test_ledger_completion_rejects_runtime_ledger_mirror_drift(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)
    runtime_ledger = repo / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    runtime_ledger.write_text(runtime_ledger.read_text("utf-8") + "\n", "utf-8")

    with pytest.raises(RuntimeError, match="continuity ledger runtime mirror drift"):
        continuity.validate_workspace_completion(
            repo,
            changed_paths,
            baseline_revision=baseline,
        )


def test_ledger_completion_rejects_non_append_only_history(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)
    canonical_ledger = repo / "docs/sovereign-continuity/LEDGER.jsonl"
    runtime_ledger = repo / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    entries = [json.loads(line) for line in canonical_ledger.read_text("utf-8").splitlines() if line.strip()]
    entries[0]["summary"] = "rewritten baseline"
    _write_jsonl(canonical_ledger, entries)
    runtime_ledger.write_bytes(canonical_ledger.read_bytes())

    with pytest.raises(RuntimeError, match="CONTINUITY_LEDGER_APPEND_ONLY_VIOLATION"):
        continuity.validate_workspace_completion(
            repo,
            changed_paths,
            baseline_revision=baseline,
        )


def test_ledger_rejects_secret_shaped_content_without_echoing_value(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)
    canonical_ledger = repo / "docs/sovereign-continuity/LEDGER.jsonl"
    runtime_ledger = repo / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    entries = [json.loads(line) for line in canonical_ledger.read_text("utf-8").splitlines() if line.strip()]
    leaked_value = "ghp_" + "s" * 40
    entries[-1]["evidence"] = [f"token={leaked_value}"]
    _write_jsonl(canonical_ledger, entries)
    runtime_ledger.write_bytes(canonical_ledger.read_bytes())

    with pytest.raises(RuntimeError) as exc_info:
        continuity.validate_workspace_completion(
            repo,
            changed_paths,
            baseline_revision=baseline,
        )

    assert "secret-shaped material" in str(exc_info.value)
    assert leaked_value not in str(exc_info.value)
