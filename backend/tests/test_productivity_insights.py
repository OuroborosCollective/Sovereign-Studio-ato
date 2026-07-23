from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.productivity_insights import (
    _deterministic_changelog,
    deterministic_mission_validation,
)


def test_preflight_warns_for_broad_mission():
    result = deterministic_mission_validation("refactor everything")
    assert result.score < 40
    assert result.specific_enough is False
    assert result.questions
    assert result.status == "deterministic_fallback"


def test_preflight_accepts_bounded_verifiable_mission():
    result = deterministic_mission_validation(
        "Implementiere src/auth/login.ts, teste den Login-Build und ändere nichts außerhalb der Route."
    )
    assert result.score >= 40
    assert result.specific_enough is True
    assert "action" in result.evidence
    assert "target" in result.evidence


def test_changelog_groups_real_commit_subjects():
    markdown, count = _deterministic_changelog(
        "abc1234 feat: add mission validator\ndef5678 fix: prevent empty diff success\n987abcd remove legacy route",
        "",
    )
    assert count == 3
    assert "### Added" in markdown
    assert "- add mission validator" in markdown
    assert "### Fixed" in markdown
    assert "- prevent empty diff success" in markdown
    assert "### Removed" in markdown


def test_backend_and_deployment_insights_are_exact_mirrors():
    canonical = (ROOT / "backend" / "agent_runtime" / "productivity_insights.py").read_text(encoding="utf-8")
    deployed = (ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "productivity_insights.py").read_text(encoding="utf-8")
    assert canonical == deployed
