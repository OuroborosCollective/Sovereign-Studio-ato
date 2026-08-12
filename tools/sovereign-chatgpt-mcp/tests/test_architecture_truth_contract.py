from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from architecture_truth_contract import (
    ArchitectureEvidence,
    ArchitecturePolicy,
    ArchitectureTruthContractError,
    EvidenceAssertion,
    canonical_sha256,
    compile_architecture_truth_contract,
    evaluate_pre_effect,
)


ROOT = Path(__file__).resolve().parents[3]
POLICY_PATH = ROOT / "config" / "architecture" / "sovereign-architecture-truth.v1.json"


def repository_revision() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def policy() -> ArchitecturePolicy:
    return ArchitecturePolicy.from_mapping(json.loads(POLICY_PATH.read_text("utf-8")))


def evidence(kind: str, *, assertion: EvidenceAssertion = EvidenceAssertion.OBSERVED) -> ArchitectureEvidence:
    revision = repository_revision()
    return ArchitectureEvidence(
        evidence_kind=kind,
        repository="OuroborosCollective/Sovereign-Studio-ato",
        repository_revision=revision,
        evidence_sha256=canonical_sha256({"kind": kind, "revision": revision, "assertion": assertion.value}),
        assertion=assertion,
    )


def contract():
    return compile_architecture_truth_contract(
        policy=policy(),
        evidence=(
            evidence("architecture_inventory"),
            evidence("architecture_drift_report"),
            evidence("backend_assessment"),
            evidence("repository_snapshot"),
        ),
    )


def test_policy_and_compiled_contract_have_stable_canonical_hashes() -> None:
    first = contract()
    second = contract()

    assert first.contract_sha256 == second.contract_sha256
    assert first.architecture_policy_sha256 == policy().policy_sha256
    assert first.repository_revision == repository_revision()
    assert [item.evidence_kind for item in first.evidence] == [
        "architecture_drift_report",
        "architecture_inventory",
        "backend_assessment",
        "repository_snapshot",
    ]


def test_compile_rejects_missing_required_observed_evidence() -> None:
    with pytest.raises(ArchitectureTruthContractError, match="required evidence is missing"):
        compile_architecture_truth_contract(
            policy=policy(),
            evidence=(
                evidence("architecture_inventory"),
                evidence("architecture_drift_report"),
                evidence("backend_assessment"),
            ),
        )


def test_compile_rejects_cross_revision_evidence() -> None:
    current = evidence("architecture_inventory")
    stale = ArchitectureEvidence(
        evidence_kind="architecture_drift_report",
        repository=current.repository,
        repository_revision="0" * 40,
        evidence_sha256=canonical_sha256({"stale": True}),
    )

    with pytest.raises(ArchitectureTruthContractError, match="evidence revisions are not identical"):
        compile_architecture_truth_contract(
            policy=policy(),
            evidence=(
                current,
                stale,
                evidence("backend_assessment"),
                evidence("repository_snapshot"),
            ),
        )


def test_deployment_requires_same_revision_runtime_readback() -> None:
    compiled = contract()
    decision = evaluate_pre_effect(
        contract=compiled,
        effect_id="deploy-backend",
        effect_domain="deployment",
        effect_repository=compiled.repository,
        effect_revision=compiled.repository_revision,
    )

    assert decision["verdict"] == "REQUIRE_REVALIDATION"
    assert decision["findings"] == ["RUNTIME_REVISION_EVIDENCE_MISSING_OR_STALE"]

    runtime = ArchitectureEvidence(
        evidence_kind="runtime_readback",
        repository=compiled.repository,
        repository_revision=compiled.repository_revision,
        evidence_sha256=canonical_sha256({"sourceRevision": compiled.repository_revision, "status": "ready"}),
    )
    allowed = evaluate_pre_effect(
        contract=compiled,
        effect_id="deploy-backend",
        effect_domain="deployment",
        effect_repository=compiled.repository,
        effect_revision=compiled.repository_revision,
        runtime_evidence=runtime,
    )

    assert allowed["verdict"] == "ALLOW"
    assert allowed["findings"] == ["PRE_EFFECT_CONTRACT_SATISFIED"]


def test_stale_effect_revision_requires_revalidation_even_with_runtime_evidence() -> None:
    compiled = contract()
    runtime = ArchitectureEvidence(
        evidence_kind="runtime_readback",
        repository=compiled.repository,
        repository_revision=compiled.repository_revision,
        evidence_sha256=canonical_sha256({"sourceRevision": compiled.repository_revision, "status": "ready"}),
    )

    decision = evaluate_pre_effect(
        contract=compiled,
        effect_id="deploy-backend",
        effect_domain="deployment",
        effect_repository=compiled.repository,
        effect_revision="f" * 40,
        runtime_evidence=runtime,
    )

    assert decision["verdict"] == "REQUIRE_REVALIDATION"
    assert decision["findings"] == ["EFFECT_REVISION_STALE"]


def test_contradicted_contract_evidence_blocks_effect() -> None:
    compiled = compile_architecture_truth_contract(
        policy=policy(),
        evidence=(
            evidence("architecture_inventory"),
            evidence("architecture_drift_report", assertion=EvidenceAssertion.CONTRADICTED),
            evidence("backend_assessment"),
            evidence("repository_snapshot"),
        ),
    )

    decision = evaluate_pre_effect(
        contract=compiled,
        effect_id="repository-mutation",
        effect_domain="mutation",
        effect_repository=compiled.repository,
        effect_revision=compiled.repository_revision,
    )

    assert decision["verdict"] == "CONTRADICTED"
    assert decision["findings"] == ["CONTRACT_EVIDENCE_CONTRADICTED"]
