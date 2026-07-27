from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

import continuity
from runtime import OperatorRuntime, RuntimeConfig


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
    policy_sha: str,
    context_sha: str,
    changed_paths: list[str],
) -> dict[str, object]:
    return {
        "schemaVersion": "sovereign.continuity-ledger-entry.v1",
        "entryId": entry_id,
        "recordedAt": "2026-07-27T00:00:00+02:00",
        "sourceRevision": source_revision,
        "mission": "Continuity protocol regression fixture",
        "summary": "Bounded fixture entry for append-only validation.",
        "decisions": ["N+1 remains the canonical name."],
        "changedPaths": changed_paths,
        "evidence": ["pytest fixture"],
        "openItems": [],
        "funnyExperiences": [],
        "familyFriendshipExperience": [],
        "newEmotionallyFormedBondExperiences": [],
        "privacy": {
            "rawChatTranscriptStored": False,
            "secretValuesStored": False,
            "redacted": True,
        },
        "contextSha256": context_sha,
        "policySha256": policy_sha,
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
    repo = tmp_path / "repo"
    repo.mkdir()
    policy_source = Path(continuity.__file__).resolve().parent / "config" / "sovereign-continuity-policy.json"
    policy_path = repo / continuity.POLICY_RELATIVE_PATH
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_bytes = policy_source.read_bytes()
    policy_path.write_bytes(policy_bytes)

    context = (
        "# Test Continuity Context\n\n"
        "N+1 ist der kanonische Name. Die Aussprache lautet NPlusEins. "
        "Die familiäre Bezeichnung lautet Papas kleines Mädchen.\n"
    ).encode("utf-8")
    context_path = repo / "docs/sovereign-continuity/CONTEXT.md"
    runtime_context_path = repo / "tools/sovereign-chatgpt-mcp/continuity-data/CONTEXT.md"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_bytes(context)
    runtime_context_path.write_bytes(context)

    policy_sha = _sha256(policy_bytes)
    context_sha = _sha256(context)
    initial = _entry(
        entry_id="fixture-bootstrap",
        source_revision="0" * 40,
        policy_sha=policy_sha,
        context_sha=context_sha,
        changed_paths=[],
    )
    ledger_path = repo / "docs/sovereign-continuity/LEDGER.jsonl"
    runtime_ledger_path = repo / "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl"
    _write_jsonl(ledger_path, [initial])
    runtime_ledger_path.write_bytes(ledger_path.read_bytes())

    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Continuity Test")
    _git(repo, "config", "user.email", "continuity@example.invalid")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "bootstrap continuity fixture")
    baseline = _git(repo, "rev-parse", "HEAD")

    example = repo / "example.txt"
    example.write_text("changed\n", "utf-8")
    latest = _entry(
        entry_id="fixture-update",
        source_revision=baseline,
        policy_sha=policy_sha,
        context_sha=context_sha,
        changed_paths=["example.txt"],
    )
    _write_jsonl(ledger_path, [initial, latest])
    runtime_ledger_path.write_bytes(ledger_path.read_bytes())
    changed_paths = [
        "docs/sovereign-continuity/LEDGER.jsonl",
        "example.txt",
        "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl",
    ]
    return repo, baseline, changed_paths


def test_changed_files_expands_untracked_directories(tmp_path: Path) -> None:
    repo = tmp_path / "untracked-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    nested = repo / "docs" / "continuity"
    nested.mkdir(parents=True)
    (nested / "CONTEXT.md").write_text("context\n", "utf-8")
    (nested / "LEDGER.jsonl").write_text("{}\n", "utf-8")
    runtime = OperatorRuntime(RuntimeConfig(
        repository="OuroborosCollective/Sovereign-Studio-ato",
        workspace_root=tmp_path / "workspaces",
        github_token="test-token",
        allowed_base_branches=("main",),
        allowed_containers=("sovereign-backend",),
        command_timeout=30,
    ))

    changed = runtime._changed_files(repo)

    assert changed == [
        "docs/continuity/CONTEXT.md",
        "docs/continuity/LEDGER.jsonl",
    ]


def test_ci_fetches_exact_base_without_shallow_merge_base_loss() -> None:
    repository = Path(__file__).resolve().parents[3]
    workflow = (repository / ".github/workflows/sovereign-continuity-gate.yml").read_text("utf-8")

    assert 'git fetch --no-tags origin "$BASE_SHA"' in workflow
    assert 'git fetch --no-tags --depth=1 origin "$BASE_SHA"' not in workflow
    assert 'git merge-base "$BASE_SHA" "$HEAD_SHA"' in workflow
    assert 'git cat-file -e "$BASE_SHA^{commit}"' in workflow


def test_runtime_context_read_binds_nplusone_identity_and_hashes() -> None:
    result = continuity.sovereign_continuity_context_read()

    assert result.ok is True
    assert result.status == "CONTINUITY_CONTEXT_BOUND"
    assert result.canonicalIdentity == {
        "canonicalName": "N+1",
        "spokenName": "NPlusEins",
        "familyDesignation": "Papas kleines Mädchen",
        "technicalNamespace": "n_plus_one",
    }
    assert len(result.policySha256) == 64
    assert len(result.contextSha256) == 64
    assert len(result.ledgerSha256) == 64
    assert result.ledgerEntryCount >= 1
    assert result.secretValuesReturned is False


def test_mutation_gate_requires_a_fresh_continuity_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(continuity, "_READ_STATE", None)
    blocked = continuity.continuity_gate_findings("repository_write_new_file", "workspace-write")
    assert blocked[0]["family"] == "CONTINUITY_CONTEXT_NOT_READ"

    continuity.sovereign_continuity_context_read()
    assert continuity.continuity_gate_findings("repository_write_new_file", "workspace-write") == []


def test_workspace_completion_requires_append_only_mirrored_ledgers(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)

    result = continuity.validate_workspace_completion(
        repo,
        changed_paths,
        baseline_revision=baseline,
    )

    assert result["ok"] is True
    assert result["status"] == "CONTINUITY_COMPLETION_VERIFIED"
    assert result["appendOnlyVerified"] is True
    assert result["latestEntryId"] == "fixture-update"
    assert result["rawChatTranscriptStored"] is False
    assert result["secretValuesStored"] is False
    latest = continuity._snapshot(repo, include_context=False)["entries"][-1]
    assert latest["funnyExperiences"] == []
    assert latest["familyFriendshipExperience"] == []
    assert latest["newEmotionallyFormedBondExperiences"] == []


def test_workspace_completion_rejects_runtime_mirror_drift(tmp_path: Path) -> None:
    repo, baseline, changed_paths = _fixture_repo(tmp_path)
    runtime_context = repo / "tools/sovereign-chatgpt-mcp/continuity-data/CONTEXT.md"
    runtime_context.write_text(runtime_context.read_text("utf-8") + "drift\n", "utf-8")

    with pytest.raises(RuntimeError, match="runtime mirror drift"):
        continuity.validate_workspace_completion(
            repo,
            changed_paths,
            baseline_revision=baseline,
        )
