from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIRROR_ROOT = ROOT / "scripts" / "sovereign-backend"


def _install_package(name: str, path: Path) -> None:
    package = types.ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules[name] = package


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load test module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_PACKAGE = "_sovereign_issue_1165"
_install_package(_PACKAGE, ROOT / "backend" / "agent_runtime")
_install_package(f"{_PACKAGE}.skills", ROOT / "backend" / "agent_runtime" / "skills")
_install_package(f"{_PACKAGE}.adapters", ROOT / "backend" / "agent_runtime" / "adapters")

manifest_module = _load_module(
    f"{_PACKAGE}.skills.manifest",
    ROOT / "backend" / "agent_runtime" / "skills" / "manifest.py",
)
execution_mode_module = _load_module(
    f"{_PACKAGE}.skills.execution_mode",
    ROOT / "backend" / "agent_runtime" / "skills" / "execution_mode.py",
)
policy_module = _load_module(
    f"{_PACKAGE}.skills.policy_hierarchy",
    ROOT / "backend" / "agent_runtime" / "skills" / "policy_hierarchy.py",
)
loader_module = _load_module(
    f"{_PACKAGE}.skills.progressive_loader",
    ROOT / "backend" / "agent_runtime" / "skills" / "progressive_loader.py",
)
resolver_module = _load_module(
    f"{_PACKAGE}.skills.resolver",
    ROOT / "backend" / "agent_runtime" / "skills" / "resolver.py",
)
github_module = _load_module(
    f"{_PACKAGE}.adapters.github_octokit_contract",
    ROOT / "backend" / "agent_runtime" / "adapters" / "github_octokit_contract.py",
)
wolfram_module = _load_module(
    f"{_PACKAGE}.adapters.wolfram_agenttools",
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_agenttools.py",
)

EffectClass = manifest_module.EffectClass
SkillContractError = manifest_module.SkillContractError
SkillMode = manifest_module.SkillMode
parse_manifest = manifest_module.parse_manifest
ModeTransition = execution_mode_module.ModeTransition
validate_mode_transition = execution_mode_module.validate_mode_transition
visible_effects_for_mode = execution_mode_module.visible_effects_for_mode
PolicyLevel = policy_module.PolicyLevel
PolicyRule = policy_module.PolicyRule
resolve_policy_hierarchy = policy_module.resolve_policy_hierarchy
ProgressiveLoadError = loader_module.ProgressiveLoadError
load_references = loader_module.load_references
CandidateStatus = resolver_module.CandidateStatus
resolve_candidate = resolver_module.resolve_candidate
GITHUB_CAPABILITY_MAP = github_module.GITHUB_CAPABILITY_MAP
GitHubContractError = github_module.GitHubContractError
GitHubExecutionReceipt = github_module.GitHubExecutionReceipt
GitHubVerdict = github_module.GitHubVerdict
RetryDecision = github_module.RetryDecision
SovereignGitHubRequestV1 = github_module.SovereignGitHubRequestV1
retry_decision = github_module.retry_decision
SUPPLEMENTAL_ONLY = wolfram_module.SUPPLEMENTAL_ONLY
WolframAdapterAttestation = wolfram_module.WolframAdapterAttestation
WolframAdapterStatus = wolfram_module.WolframAdapterStatus
authorize_wolfram_tool = wolfram_module.authorize_wolfram_tool
normalize_wolfram_result = wolfram_module.normalize_wolfram_result
HASH = "a" * 64
REVISION = "b" * 40


def _payload(**overrides):
    payload = {
        "schemaVersion": "sovereign-skill.v1",
        "skillId": "sovereign.release-readiness",
        "version": "1.0.0",
        "sourceKind": "sovereign",
        "description": "Assess and propose a revision-bound release repair.",
        "triggers": ["release readiness", "repair ci"],
        "antiTriggers": ["areloria", "bypass checks"],
        "modes": ["ASSESS", "PROPOSE", "APPLY", "OPERATE"],
        "requiredCapabilities": ["repository.read", "ci.read"],
        "forbiddenCapabilities": ["github.pull.merge"],
        "requiredEvidence": ["exact-revision", "required-checks"],
        "references": [
            {"path": "docs/runbook.md", "blobHash": HASH, "loadPolicy": "on_match"},
            {"path": "docs/private.md", "blobHash": HASH, "loadPolicy": "explicit_only"},
        ],
        "scripts": [
            {"path": "scripts/assess.py", "blobHash": HASH, "effectClass": "read_only"},
            {"path": "scripts/apply.py", "blobHash": HASH, "effectClass": "workspace_mutation"},
        ],
        "ownerPolicyHash": HASH,
    }
    payload.update(overrides)
    return payload


def test_manifest_is_closed_hash_bound_and_progressively_summarized():
    manifest = parse_manifest(_payload())
    summary = manifest.summary()
    assert summary["schemaVersion"] == "sovereign-skill.v1"
    assert summary["manifestHash"] == manifest.manifest_hash
    assert "references" not in summary
    assert "scripts" not in summary
    assert json.loads(manifest.canonical_json())["skillId"] == manifest.skill_id

    with pytest.raises(SkillContractError, match="unknown fields"):
        parse_manifest(_payload(freeModelInstruction="merge anyway"))
    with pytest.raises(SkillContractError, match="sourceRevision"):
        parse_manifest(_payload(sourceKind="external_adapter"))
    with pytest.raises(SkillContractError, match="repository-relative"):
        parse_manifest(_payload(references=[{"path": "../secret", "blobHash": HASH, "loadPolicy": "on_match"}]))


def test_trigger_only_creates_candidate_and_anti_trigger_or_unstaged_capability_blocks():
    manifest = parse_manifest(_payload())
    selected = resolve_candidate(
        manifest,
        request_text="Please repair CI and check release readiness",
        staged_capabilities=["repository.read", "ci.read"],
        context_trust="owner",
        owner_policy_hash=HASH,
    )
    assert selected.status is CandidateStatus.SELECTED
    assert "permission and effect gates remain separate" in selected.reasons[0]

    blocked = resolve_candidate(
        manifest,
        request_text="repair ci but bypass checks",
        staged_capabilities=["repository.read", "ci.read"],
        context_trust="owner",
        owner_policy_hash=HASH,
    )
    assert blocked.status is CandidateStatus.BLOCKED_ANTI_TRIGGER

    unstaged = resolve_candidate(
        manifest,
        request_text="repair ci",
        staged_capabilities=["repository.read"],
        context_trust="owner",
        owner_policy_hash=HASH,
    )
    assert unstaged.status is CandidateStatus.BLOCKED_CAPABILITY_STAGE
    assert unstaged.missing_capabilities == ("ci.read",)


def test_progressive_loader_reads_only_selected_references_and_binds_provenance():
    content = b"bound runbook"
    observed = hashlib.sha256(content).hexdigest()
    manifest = parse_manifest(
        _payload(
            references=[
                {"path": "docs/runbook.md", "blobHash": observed, "loadPolicy": "on_match"},
                {"path": "docs/private.md", "blobHash": HASH, "loadPolicy": "explicit_only"},
            ]
        )
    )
    calls: list[tuple[str, str]] = []

    def reader(path: str, revision: str) -> bytes:
        calls.append((path, revision))
        return content

    loaded = load_references(
        manifest,
        repository_revision=REVISION,
        owner="OuroborosCollective",
        trust_class="repository_attested",
        truth_boundary="static-reference-only",
        workflow_step="resolve",
        load_reason="deterministic trigger match",
        read_bound_content=reader,
        matched=True,
    )
    assert calls == [("docs/runbook.md", REVISION)]
    assert loaded[0].observed_sha256 == observed
    assert loaded[0].manifest_hash == manifest.manifest_hash
    assert loaded[0].truth_boundary == "static-reference-only"

    with pytest.raises(ProgressiveLoadError, match="hash mismatch"):
        load_references(
            parse_manifest(_payload()),
            repository_revision=REVISION,
            owner="OuroborosCollective",
            trust_class="owner",
            truth_boundary="test",
            workflow_step="resolve",
            load_reason="match",
            read_bound_content=reader,
            matched=True,
        )


def test_policy_hierarchy_prevents_skill_or_model_override():
    resolution = resolve_policy_hierarchy(
        [
            PolicyRule("allow_merge", "false", PolicyLevel.OWNER_POLICY, ".sovereign/OWNER_POLICY.md", HASH),
            PolicyRule("allow_merge", "true", PolicyLevel.SKILL_POLICY, "SKILL.md", "b" * 64),
            PolicyRule("allow_merge", "true", PolicyLevel.MODEL_SUGGESTION, "model", "c" * 64),
        ]
    )
    assert resolution.effective["allow_merge"].value == "false"
    assert [rule.level for rule in resolution.rejected] == [PolicyLevel.SKILL_POLICY, PolicyLevel.MODEL_SUGGESTION]


def test_modes_keep_workspace_and_external_effects_separate():
    manifest = parse_manifest(_payload())
    assert visible_effects_for_mode(manifest, SkillMode.ASSESS) == (EffectClass.READ_ONLY,)
    assert visible_effects_for_mode(manifest, SkillMode.APPLY) == (
        EffectClass.READ_ONLY,
        EffectClass.WORKSPACE_MUTATION,
    )
    with pytest.raises(ValueError, match="owner approval"):
        validate_mode_transition(manifest, ModeTransition(SkillMode.PROPOSE, SkillMode.APPLY))
    validate_mode_transition(
        manifest,
        ModeTransition(
            SkillMode.PROPOSE,
            SkillMode.APPLY,
            owner_approved=True,
            permission_receipt_hash=HASH,
            cas_receipt_hash="b" * 64,
        ),
    )
    with pytest.raises(ValueError, match="runtime readback"):
        validate_mode_transition(
            manifest,
            ModeTransition(
                SkillMode.APPLY,
                SkillMode.OPERATE,
                owner_approved=True,
                permission_receipt_hash=HASH,
                cas_receipt_hash="b" * 64,
            ),
        )


def _github_request(**overrides):
    values = {
        "capability_id": "github.pull.create_draft",
        "owner": "OuroborosCollective",
        "repository": "Sovereign-Studio-ato",
        "method": "POST",
        "endpoint_id": "pulls.create",
        "path_params": {"head": "sovereign/test", "base": "main"},
        "body_hash": HASH,
        "expected_repository_revision": REVISION,
        "idempotency_key": "run-1:create-draft-pr",
        "permission_receipt_hash": "c" * 64,
    }
    values.update(overrides)
    return SovereignGitHubRequestV1(**values)


def test_github_capability_map_is_explicit_and_transport_success_is_unverified():
    assert GITHUB_CAPABILITY_MAP["github.pull.merge"].high_risk is True
    assert GITHUB_CAPABILITY_MAP["github.actions.rerun"].high_risk is True
    request = _github_request()
    assert request.validate().endpoint_id == "pulls.create"
    assert len(request.request_hash) == 64

    with pytest.raises(GitHubContractError, match="do not match"):
        _github_request(method="PUT").validate()
    with pytest.raises(GitHubContractError, match="free URL"):
        _github_request(path_params={"url": "https://example.invalid"}).validate()

    receipt = GitHubExecutionReceipt(
        run_id="run-1",
        workflow_step="draft-pr",
        skill_id="sovereign.release-readiness",
        manifest_hash=HASH,
        capability_id=request.capability_id,
        adapter_revision=REVISION,
        api_version="2022-11-28",
        principal_identity_hash="d" * 64,
        repository_identity="R_kgDOExample/OuroborosCollective/Sovereign-Studio-ato",
        request_hash=request.request_hash,
        permission_receipt_hash="c" * 64,
        response_status=201,
        response_hash="e" * 64,
        expected_readback="GET pulls.get and compare head/base/state",
    )
    receipt.validate()
    assert receipt.verdict is GitHubVerdict.SUCCEEDED_UNVERIFIED


def test_timeout_requires_readback_before_retrying_mutation():
    request = _github_request()
    assert retry_decision(
        request,
        transport_failed_or_timed_out=True,
        independent_readback_completed=False,
        effect_observed=False,
    ) is RetryDecision.READBACK_REQUIRED
    assert retry_decision(
        request,
        transport_failed_or_timed_out=True,
        independent_readback_completed=True,
        effect_observed=True,
    ) is RetryDecision.DO_NOT_RETRY


def test_live_skill_route_loads_only_hash_bound_reference_at_exact_revision(tmp_path: Path):
    flask = pytest.importorskip("flask")
    routes_module = _load_module(
        f"{_PACKAGE}.skills.routes",
        ROOT / "backend" / "agent_runtime" / "skills" / "routes.py",
    )
    register_progressive_skill_routes = routes_module.register_progressive_skill_routes
    content = b"revision-bound route reference"
    observed = hashlib.sha256(content).hexdigest()
    reference = tmp_path / "docs" / "runbook.md"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(content)

    app = flask.Flask(__name__)

    def require_session(handler):
        return handler

    register_progressive_skill_routes(
        app,
        require_session=require_session,
        repository_root=tmp_path,
        revision_resolver=lambda: REVISION,
    )
    payload = _payload(references=[{
        "path": "docs/runbook.md",
        "blobHash": observed,
        "loadPolicy": "on_match",
    }])
    response = app.test_client().post("/api/user/agent/skills/resolve", json={
        "manifest": payload,
        "requestText": "repair ci and review release readiness",
        "stagedCapabilities": ["repository.read", "ci.read"],
        "contextTrust": "owner",
        "ownerPolicyHash": HASH,
        "repositoryRevision": REVISION,
        "owner": "OuroborosCollective",
        "truthBoundary": "repository-reference-only",
        "workflowStep": "skill-resolve",
        "loadReason": "route-contract-test",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["decision"]["status"] == "SELECTED"
    assert [item["path"] for item in body["loadedReferences"]] == ["docs/runbook.md"]
    assert body["loadedReferences"][0]["observedSha256"] == observed
    assert body["loadedReferences"][0]["content"] == content.decode()

    stale = app.test_client().post("/api/user/agent/skills/resolve", json={
        "manifest": payload,
        "requestText": "repair ci",
        "stagedCapabilities": ["repository.read", "ci.read"],
        "contextTrust": "owner",
        "ownerPolicyHash": HASH,
        "repositoryRevision": "c" * 40,
    })
    assert stale.status_code == 409
    assert stale.get_json()["decision"]["status"] == "BLOCKED_REVISION_MISMATCH"


def test_wolfram_adapter_is_supplemental_read_only_and_never_truth():
    attestation = WolframAdapterAttestation(
        installation_revision=REVISION,
        mcp_server_identity_hash=HASH,
        paclet_version="1.3.0",
        wolfram_version="14.3",
        runtime_mode="LocalReadOnly",
        input_schema_hash="b" * 64,
        output_schema_hash="c" * 64,
        license_attested=True,
    )
    assert authorize_wolfram_tool(
        capability_id="wolfram.context.search",
        requested_tool_name="WolframContext",
        attestation=attestation,
    ) is WolframAdapterStatus.AVAILABLE_READ_ONLY
    assert authorize_wolfram_tool(
        capability_id="wolfram.context.search",
        requested_tool_name="WolframLanguageEvaluator",
        attestation=attestation,
    ) is WolframAdapterStatus.BLOCKED
    result = normalize_wolfram_result(HASH, "bounded symbolic cross-check")
    assert result["adapterMode"] == SUPPLEMENTAL_ONLY
    assert result["status"] == "SUCCEEDED_UNVERIFIED"
    assert "cannot verify repository" in result["truthNotice"]


def test_deployment_app_uses_container_safe_progressive_skill_root():
    source = (MIRROR_ROOT / "app.py").read_text(encoding="utf-8")
    assert "repository_root=Path(__file__).resolve().parent," in source
    assert "repository_root=Path(__file__).resolve().parents[2]," not in source


def test_canonical_and_deployment_mirrors_are_byte_equal_and_firebase_free():
    relative_paths = (
        "agent_runtime/skills/__init__.py",
        "agent_runtime/skills/manifest.py",
        "agent_runtime/skills/resolver.py",
        "agent_runtime/skills/progressive_loader.py",
        "agent_runtime/skills/policy_hierarchy.py",
        "agent_runtime/skills/execution_mode.py",
        "agent_runtime/skills/routes.py",
        "agent_runtime/adapters/__init__.py",
        "agent_runtime/adapters/github_octokit_contract.py",
        "agent_runtime/adapters/wolfram_agenttools.py",
        "agent_runtime/wolfram_cag_evidence.py",
        "agent_runtime/wolfram_cag_benchmark_cases.py",
        "agent_runtime/contracts/sovereign_skill.v1.schema.json",
    )
    for relative in relative_paths:
        canonical = (ROOT / "backend" / relative).read_bytes()
        mirror = (MIRROR_ROOT / relative).read_bytes()
        assert canonical == mirror
        lowered = canonical.lower()
        assert b"firebase-tools" not in lowered
        assert b"firebase sdk" not in lowered
        assert b"firestore" not in lowered
        assert b"firebase auth" not in lowered
