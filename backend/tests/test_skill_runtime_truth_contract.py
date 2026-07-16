from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "src" / "features" / "product" / "containers" / "BuilderContainer.tsx"
STORE = ROOT / "src" / "features" / "toolchain" / "useSkillsStore.ts"
RUNTIME = ROOT / "src" / "features" / "toolchain" / "skillRuntime.ts"
PANEL = ROOT / "src" / "features" / "toolchain" / "components" / "SkillScanPanel.tsx"
MIGRATION = ROOT / "scripts" / "sovereign-backend" / "migrations" / "020_user_skills_runtime_contract.sql"
APP_SOURCES = (
    ROOT / "backend" / "app.py",
    ROOT / "scripts" / "sovereign-backend" / "app.py",
)


def _function_ast(path: Path, name: str) -> str:
    module = ast.parse(path.read_text(encoding="utf-8"))
    node = next(
        item for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.dump(node, include_attributes=False)


def test_explicit_skill_command_enters_normal_runtime_pipeline_without_fake_success():
    source = BUILDER.read_text(encoding="utf-8")

    assert "buildExplicitSkillMission" in source
    assert "await _processSubmit(skillMission, { inputAlreadyRecorded: true })" in source
    assert "Der installierte Workflow wird über die normale Sovereign-Routing- und Evidence-Pipeline ausgeführt." in source
    assert "wird ausgeführt…" not in source
    assert "command.adapted_prompt.slice(0, 600)" not in source


def test_installation_state_comes_from_persisted_backend_row():
    store = STORE.read_text(encoding="utf-8")
    assert "const newSkill: UserSkill = installed.skill" in store
    assert "created_at: new Date().toISOString()" not in store


def test_unselected_skill_prompts_are_not_injected_into_worker_messages():
    builder = BUILDER.read_text(encoding="utf-8")
    store = STORE.read_text(encoding="utf-8")

    assert "getActiveSkillContext()," not in builder
    assert "s.adapted_prompt.slice" not in store
    assert "nur bei ausdrücklichem Slash-Aufruf" in store


def test_explicit_skill_mission_contains_runtime_truth_gate():
    source = RUNTIME.read_text(encoding="utf-8")

    assert "Explicit Sovereign skill invocation." in source
    assert "do not claim execution, file changes, tests, deployment, or success" in source
    assert "Runtime truth rules" in source


def test_repository_skill_adaptation_reloads_and_verifies_the_github_blob():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert 'source_sha = str(b.get("source_sha") or "").strip()' in source
        assert 'source = _tc_read_github_file(owner, repo, path, ref)' in source
        assert 'hmac.compare_digest(source_sha, actual_source_sha)' in source
        assert '"blocker": "skill_source_sha_mismatch"' in source
        assert 'hashlib.sha256(meta["adapted_prompt"].encode("utf-8")).hexdigest()' in source
        assert '"content_sha256": content_sha256' in source


def test_mcp_apps_are_not_installed_as_prompt_skills():
    panel = PANEL.read_text(encoding="utf-8")
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert '"kind": "mcp_app" if framework == "fastmcp" else "skill"' in source
        assert source.count('"blocker": "mcp_app_requires_plugin_installation"') >= 2
    assert "found.kind === 'mcp_app'" in panel
    assert "MCP-Server werden nicht als Prompt-Skill installiert" in panel
    assert "disabled={isMcpApp ||" in panel


def test_skill_install_is_atomic_hash_verified_and_reloadable():
    for path in APP_SOURCES:
        source = path.read_text(encoding="utf-8")
        assert 'computed_content_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()' in source
        assert 'hmac.compare_digest(declared_content_sha256, computed_content_sha256)' in source
        assert '"blocker": "skill_content_hash_mismatch"' in source
        assert "ON CONFLICT (user_id, slug) WHERE btrim(slug) <> '' DO UPDATE SET" in source
        assert "RETURNING id::text, name, slug" in source
        assert "framework, adapted_prompt, source_sha, content_sha256" in source
        assert '"skill": dict(row)' in source


def test_user_skills_migration_matches_runtime_contract_without_destructive_actions():
    source = MIGRATION.read_text(encoding="utf-8")
    for column in (
        "name", "slug", "description", "source_repo", "source_path",
        "framework", "adapted_prompt", "source_sha", "content_sha256",
        "is_active", "updated_at",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in source
    assert "ALTER COLUMN skill_id DROP NOT NULL" in source
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_skills_user_slug" in source
    assert "DROP TABLE" not in source
    assert "TRUNCATE" not in source
    assert "DELETE FROM user_skills" not in source


def test_live_and_deploy_skill_functions_are_semantically_identical():
    for name in (
        "_scan_tree_for_skills",
        "tc_skills_adapt",
        "tc_skills_install",
        "tc_skills_list",
    ):
        assert _function_ast(APP_SOURCES[0], name) == _function_ast(
            APP_SOURCES[1],
            name,
        )
