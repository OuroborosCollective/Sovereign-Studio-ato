from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "revision-guardian-continuity-repair-pr.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_legacy_pr_continuity_repair_is_exact_revision_bound_and_same_repo_only() -> None:
    text = _workflow_text()

    assert "target_pr_number:" in text
    assert "expected_head_sha:" in text
    assert "expected_base_sha:" in text
    assert "PR_HEAD_IDENTITY_MISMATCH" in text
    assert "MAIN_REVISION_CHANGED" in text
    assert "FORK_PR_REPAIR_FORBIDDEN" in text
    assert "OPEN_MAIN_PR_REQUIRED" in text
    assert 'git merge-base --is-ancestor "$EXPECTED_BASE_SHA" "$EXPECTED_HEAD_SHA"' in text
    assert "git push --force" not in text
    assert "git push -f" not in text


def test_legacy_pr_continuity_repair_changes_only_append_only_ledgers() -> None:
    text = _workflow_text()

    assert "docs/sovereign-continuity/LEDGER.jsonl" in text
    assert "tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl" in text
    assert "CONTINUITY_LEDGER_RUNTIME_MIRROR_DRIFT" in text
    assert "CONTINUITY_LEDGER_RUNTIME_MIRROR_DRIFT_AFTER_APPEND" in text
    assert "canonical_bytes.endswith(b'\\n')" in text
    assert "prefix + encoded" in text
    assert "policy = json.loads(policy_path.read_text(encoding='utf-8'))" in text
    assert "'canonicalName': str(policy['identity']['canonicalName'])" in text
    assert "sort_keys=True" in text
    assert "Leere Erfahrungsrubriken bleiben leer" in text
    assert "'familyFriendshipExperience': []" in text
    assert "'newEmotionallyFormedBondExperiences': []" in text
    assert "'funnyExperiences': []" in text
    assert "git add docs/sovereign-continuity/LEDGER.jsonl tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl" in text


def test_legacy_pr_continuity_repair_derives_paths_and_validates_before_push() -> None:
    text = _workflow_text()

    assert "['git', 'diff', '--name-only', f'{base}...{head}']" in text
    assert "ledger_paths = {canonical.as_posix(), mirror.as_posix()}" in text
    assert "recorded_paths = sorted(path for path in changed_paths if path not in ledger_paths)" in text
    assert "recorded_paths = sorted(set(changed_paths + ledger_paths))" not in text
    assert "'sourceRevision': head" in text
    assert "'changedPaths': recorded_paths" in text
    assert "f'Non-ledger changed-path count recorded: {len(recorded_paths)}.'" in text
    assert "git diff --check" in text
    assert "python3 tools/sovereign-chatgpt-mcp/validate_continuity.py" in text
    assert '--base "$EXPECTED_BASE_SHA"' in text
    assert '--head "$UPDATED_HEAD_SHA"' in text
    assert 'git push origin "HEAD:${TARGET_REF}"' in text
    assert 'test "$REMOTE_HEAD_SHA" = "$UPDATED_HEAD_SHA"' in text
