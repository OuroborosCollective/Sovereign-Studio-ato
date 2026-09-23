from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS = REPO_ROOT / "AGENTS.md"
CONSENT = REPO_ROOT / ".agents" / "skills" / "consent-gate-pattern" / "SKILL.md"
AGENT_SKILL = REPO_ROOT / ".agents" / "skills" / "evidence-flywheel" / "SKILL.md"
RUNTIME_SKILL = (
    REPO_ROOT
    / "tools"
    / "sovereign-chatgpt-mcp"
    / "skills"
    / "sovereign-evidence-flywheel"
    / "SKILL.md"
)
ASSURANCE = (
    REPO_ROOT
    / "tools"
    / "sovereign-chatgpt-mcp"
    / "skills"
    / "sovereign-operational-assurance"
    / "SKILL.md"
)
INSTALLER = (
    REPO_ROOT
    / "tools"
    / "sovereign-chatgpt-mcp"
    / "deploy"
    / "install-on-vps.sh"
)
ARCH_DOC = REPO_ROOT / "docs" / "architecture" / "SOVEREIGN_EVIDENCE_FLYWHEEL.v1.md"


def test_evidence_flywheel_skill_is_present_and_mirrored() -> None:
    assert AGENT_SKILL.is_file()
    assert RUNTIME_SKILL.is_file()
    assert AGENT_SKILL.read_text(encoding="utf-8") == RUNTIME_SKILL.read_text(
        encoding="utf-8"
    )


def test_evidence_flywheel_contract_contains_required_boundaries() -> None:
    content = AGENT_SKILL.read_text(encoding="utf-8")
    for required in (
        "exact revision",
        "baseline",
        "bounded execution",
        "causal failure-family analysis",
        "minimal fix",
        "regression",
        "independent target readback",
        "Action Preview",
        "Authority / scope resolution",
        "Action Receipt",
        "independent readback",
    ):
        assert required in content

    for forbidden in (
        "lower an evaluation threshold",
        "skip a flaky case",
        "self-grading",
        "fake snapshot",
        "reintroduce Swarm",
        "reintroduce LiteLLM",
    ):
        assert forbidden in content


def test_consent_skill_has_preview_receipt_and_revocation_contract() -> None:
    content = CONSENT.read_text(encoding="utf-8")
    for required in (
        "Evidence-bound Consent 2.0",
        "Action Preview",
        "Action Receipt",
        "Revocation",
        "SUPERSEDED",
        "idempotency",
        "receipt exists only after the real effect",
        "independent readback",
    ):
        assert required in content


def test_repository_and_assurance_docs_point_to_the_same_method() -> None:
    agents = AGENTS.read_text(encoding="utf-8")
    assurance = ASSURANCE.read_text(encoding="utf-8")
    doc = ARCH_DOC.read_text(encoding="utf-8")

    for content in (agents, assurance, doc):
        assert "Evidence Flywheel" in content
        assert "independent" in content.lower()
        assert "readback" in content.lower()

    assert "Action Preview" in agents
    assert "Action Receipt" in assurance
    assert "threshold" in doc.lower()


def test_runtime_installer_verifies_the_method_skill() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    assert (
        "docker exec sovereign-chatgpt-mcp test -f "
        "/app/skills/sovereign-evidence-flywheel/SKILL.md"
    ) in installer
