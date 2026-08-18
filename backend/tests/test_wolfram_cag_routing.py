"""Regression tests for the bounded Wolfram CAG routing layer (#1461).

These tests exercise the *real* live-path implementation in
``wolfram_cag_routing`` plus its real dependencies
(``adapters.wolfram_agenttools`` and ``skills.manifest``). No production
logic is copied into the test. Mocks are used only for the secret-free
credential projection at the adapter boundary, never in a truth path.

Truth boundaries verified here:

- Positive missions route to the single strongest read-only CAG capability.
- GitHub / Docker / DB / secret / runtime intents are NEVER routed to CAG.
- Ambiguity never auto-releases a compute / open-world path.
- Missing provisioning is honestly ``UNAVAILABLE`` / ``NOT_ENTITLED``,
  never a silent success.
- CAG capabilities are always ``read_only``; a mutation can never be staged.
- ToolChain node validation requires a real CAG contract + read-only effect
  + output schema + provisioning.
- Teaching assess / simulate cannot fake a provider receipt.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

_PACKAGE = "_sovereign_cag_routing_1461"


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


# Install the package tree so relative imports in wolfram_cag_routing resolve.
_install_package(_PACKAGE, ROOT / "backend" / "agent_runtime")
_install_package(f"{_PACKAGE}.adapters", ROOT / "backend" / "agent_runtime" / "adapters")
_install_package(f"{_PACKAGE}.skills", ROOT / "backend" / "agent_runtime" / "skills")

manifest_module = _load_module(
    f"{_PACKAGE}.skills.manifest",
    ROOT / "backend" / "agent_runtime" / "skills" / "manifest.py",
)
wolfram_module = _load_module(
    f"{_PACKAGE}.adapters.wolfram_agenttools",
    ROOT / "backend" / "agent_runtime" / "adapters" / "wolfram_agenttools.py",
)
routing_module = _load_module(
    f"{_PACKAGE}.wolfram_cag_routing",
    ROOT / "backend" / "agent_runtime" / "wolfram_cag_routing.py",
)

EffectClass = manifest_module.EffectClass
WolframCagComponent = wolfram_module.WolframCagComponent
WolframCagCredential = wolfram_module.WolframCagCredential
WolframCagStatus = wolfram_module.WolframCagStatus
WOLFRAM_CAG_COMPONENT_MAP = wolfram_module.WOLFRAM_CAG_COMPONENT_MAP
provision_cag_component = wolfram_module.provision_cag_component
is_wolfram_capability = wolfram_module.is_wolfram_capability

CAG_EFFECT_CLASS = routing_module.CAG_EFFECT_CLASS
CagRouteVerdict = routing_module.CagRouteVerdict
CagIntentClassification = routing_module.CagIntentClassification
CagRouteDecision = routing_module.CagRouteDecision
CagCapabilityProjection = routing_module.CagCapabilityProjection
CagToolchainNode = routing_module.CagToolchainNode
CagToolchainValidation = routing_module.CagToolchainValidation
CagTeachingAssessment = routing_module.CagTeachingAssessment
CagTeachingSimulation = routing_module.CagTeachingSimulation
cag_capability_registry = routing_module.cag_capability_registry
classify_cag_intent = routing_module.classify_cag_intent
route_cag_intent = routing_module.route_cag_intent
validate_cag_toolchain_node = routing_module.validate_cag_toolchain_node
cag_contract_inventory = routing_module.cag_contract_inventory
teaching_package_assess = routing_module.teaching_package_assess
teaching_lesson_simulate = routing_module.teaching_lesson_simulate
_component_contract_sha256 = routing_module._component_contract_sha256

EXPECTED_CAPABILITIES = {
    "wolfram.cag.hints",
    "wolfram.cag.compute",
    "wolfram.cag.results",
    "wolfram.cag.context",
}


def _entitled_credential() -> WolframCagCredential:
    return WolframCagCredential(
        credential_hash="a" * 64,
        entitled=True,
        provider="wolfram",
    )


def _not_entitled_credential() -> WolframCagCredential:
    return WolframCagCredential(
        credential_hash="b" * 64,
        entitled=False,
        provider="wolfram",
    )


# ---------------------------------------------------------------------------
# Capability registry projection
# ---------------------------------------------------------------------------


class TestCapabilityRegistry:
    def test_projects_exactly_the_four_cag_capabilities(self):
        registry = cag_capability_registry()
        assert {p.capability_id for p in registry} == EXPECTED_CAPABILITIES

    def test_all_capabilities_are_read_only_and_non_mutating(self):
        for projection in cag_capability_registry():
            assert projection.effect_class is EffectClass.READ_ONLY
            assert projection.mutates is False

    def test_projection_is_secret_free(self):
        for projection in cag_capability_registry():
            public = projection.to_public_dict()
            assert "url" not in public
            assert "base_url" not in public
            assert "credential" not in str(public).lower()
            assert public["effectClass"] == "read_only"

    def test_registry_reuses_single_source_of_truth(self):
        # The registry must be a projection of WOLFRAM_CAG_COMPONENT_MAP, not
        # a second map. Component identity must match 1:1.
        registry = {p.capability_id: p for p in cag_capability_registry()}
        for capability_id, component in WOLFRAM_CAG_COMPONENT_MAP.items():
            assert registry[capability_id].component == component.component
            assert registry[capability_id].endpoint_id == component.endpoint_id


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


class TestIntentClassification:
    @pytest.mark.parametrize(
        "mission,expected",
        [
            ("solve the equation x^2 - 5x + 6 = 0", "wolfram.cag.compute"),
            ("compute the exact arithmetic of 2^100 + 3^50", "wolfram.cag.compute"),
            ("evaluate the integral of x^2", "wolfram.cag.compute"),
            ("give me a wolfram language hint for plotting", "wolfram.cag.hints"),
            ("convert unit 5 miles to kilometers", "wolfram.cag.results"),
            ("wolfram alpha result for the speed of light", "wolfram.cag.results"),
            ("contextualize the background knowledge for black holes", "wolfram.cag.context"),
        ],
    )
    def test_positive_cag_missions_select_single_capability(self, mission, expected):
        classification = classify_cag_intent(mission)
        assert classification.verdict is CagRouteVerdict.SELECT_CAG
        assert classification.matched_capabilities == (expected,)

    @pytest.mark.parametrize(
        "mission,family",
        [
            ("merge the pull request on main", "github"),
            ("run the GitHub actions workflow again", "github"),
            ("query the database for the user table", "database"),
            ("apply the postgres migration", "database"),
            ("restart the docker container", "container"),
            ("deploy the new registry image", "container"),
            ("read the runtime state and patchmon readback", "runtime"),
            ("rotate the api key and secret", "secrets"),
            ("show me the credential and private key", "secrets"),
        ],
    )
    def test_non_cag_intents_are_not_routed_to_cag(self, mission, family):
        classification = classify_cag_intent(mission)
        assert classification.verdict is CagRouteVerdict.NOT_CAG
        assert classification.escape_route_family == family
        assert classification.matched_capabilities == ()

    def test_database_keyword_blocks_cag_even_with_compute_word(self):
        # "compute the database migration hash" must NOT go to CAG despite
        # the word "compute": the DB escape route wins.
        classification = classify_cag_intent("compute the database migration hash")
        assert classification.verdict is CagRouteVerdict.NOT_CAG
        assert classification.escape_route_family == "database"

    def test_no_match_for_unrelated_question(self):
        classification = classify_cag_intent("what is the weather today")
        assert classification.verdict is CagRouteVerdict.NO_MATCH
        assert classification.escape_route_family == ""

    def test_empty_mission_is_no_match(self):
        assert classify_cag_intent("").verdict is CagRouteVerdict.NO_MATCH
        assert classify_cag_intent("   ").verdict is CagRouteVerdict.NO_MATCH

    def test_ambiguity_when_two_capabilities_tie(self):
        # "compute" triggers compute; "context for" triggers context. We craft
        # a mission that hits exactly one trigger in each so they tie at score 1.
        mission = "compute the context for the experiment"
        classification = classify_cag_intent(mission)
        assert classification.verdict is CagRouteVerdict.AMBIGUOUS_CAG
        assert len(classification.matched_capabilities) >= 2
        # Ambiguity never selects a single capability.
        assert len(classification.matched_capabilities) != 1


# ---------------------------------------------------------------------------
# Bounded router
# ---------------------------------------------------------------------------


class TestBoundedRouter:
    def test_select_cag_releases_compute_only_when_provisioned(self):
        creds = {"wolfram.cag.compute": _entitled_credential()}
        decision = route_cag_intent("solve the equation x^2 - 4 = 0", credentials=creds)
        assert decision.verdict is CagRouteVerdict.SELECT_CAG
        assert decision.selected_capability == "wolfram.cag.compute"
        assert decision.provision_status is WolframCagStatus.AVAILABLE
        assert decision.releases_compute is True
        assert decision.effect_class is EffectClass.READ_ONLY

    def test_select_cag_without_credential_is_honestly_unavailable(self):
        decision = route_cag_intent("solve the equation x^2 - 4 = 0")
        assert decision.verdict is CagRouteVerdict.CAG_NOT_PROVISIONED
        assert decision.selected_capability == "wolfram.cag.compute"
        assert decision.provision_status is WolframCagStatus.UNAVAILABLE
        assert decision.releases_compute is False

    def test_select_cag_with_not_entitled_credential_is_honest(self):
        creds = {"wolfram.cag.compute": _not_entitled_credential()}
        decision = route_cag_intent("solve the equation x^2 - 4 = 0", credentials=creds)
        assert decision.verdict is CagRouteVerdict.CAG_NOT_PROVISIONED
        assert decision.provision_status is WolframCagStatus.NOT_ENTITLED
        assert decision.releases_compute is False

    def test_not_cag_never_releases_compute(self):
        decision = route_cag_intent("merge the pull request on main")
        assert decision.verdict is CagRouteVerdict.NOT_CAG
        assert decision.escape_route_family == "github"
        assert decision.releases_compute is False
        assert decision.selected_capability == ""

    def test_ambiguity_never_releases_compute(self):
        decision = route_cag_intent(
            "compute the context for the experiment",
            credentials={c: _entitled_credential() for c in EXPECTED_CAPABILITIES},
        )
        assert decision.verdict is CagRouteVerdict.AMBIGUOUS_CAG
        assert decision.releases_compute is False
        assert decision.selected_capability == ""

    def test_decision_is_secret_free(self):
        creds = {"wolfram.cag.compute": _entitled_credential()}
        decision = route_cag_intent("solve the equation x^2 - 4 = 0", credentials=creds)
        public = decision.to_public_dict()
        assert "credential" not in str(public).lower()
        assert "hash" not in str(public).lower().replace("sha256", "")  # no stray hashes
        assert public["releasesCompute"] is True


# ---------------------------------------------------------------------------
# ToolChain node validation
# ---------------------------------------------------------------------------


class TestToolchainValidation:
    def _valid_node(self, capability_id="wolfram.cag.compute") -> CagToolchainNode:
        component = WOLFRAM_CAG_COMPONENT_MAP[capability_id]
        return CagToolchainNode(
            node_id="cag-node-1",
            capability_id=capability_id,
            effect="read",
            contract_sha256=_component_contract_sha256(component),
            output_schema_present=True,
        )

    def test_valid_provisioned_node_passes(self):
        node = self._valid_node()
        creds = {"wolfram.cag.compute": _entitled_credential()}
        result = validate_cag_toolchain_node(node, credentials=creds)
        assert result.ok is True
        assert result.provision_status is WolframCagStatus.AVAILABLE
        assert result.findings == ()

    def test_node_without_credential_is_unavailable_not_ok(self):
        node = self._valid_node()
        result = validate_cag_toolchain_node(node)
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.UNAVAILABLE
        assert any("UNAVAILABLE" in f for f in result.findings)

    def test_node_with_write_effect_is_rejected(self):
        node = self._valid_node()
        node = CagToolchainNode(
            node_id=node.node_id,
            capability_id=node.capability_id,
            effect="workspace-write",
            contract_sha256=node.contract_sha256,
            output_schema_present=True,
        )
        result = validate_cag_toolchain_node(node, credentials={"wolfram.cag.compute": _entitled_credential()})
        assert result.ok is False
        assert any("effect must be" in f for f in result.findings)

    def test_node_with_external_write_effect_is_rejected(self):
        node = self._valid_node()
        node = CagToolchainNode(
            node_id=node.node_id,
            capability_id=node.capability_id,
            effect="external-write",
            contract_sha256=node.contract_sha256,
            output_schema_present=True,
        )
        result = validate_cag_toolchain_node(node, credentials={"wolfram.cag.compute": _entitled_credential()})
        assert result.ok is False

    def test_node_missing_output_schema_is_rejected(self):
        node = CagToolchainNode(
            node_id="cag-node-1",
            capability_id="wolfram.cag.compute",
            effect="read",
            contract_sha256=_component_contract_sha256(WOLFRAM_CAG_COMPONENT_MAP["wolfram.cag.compute"]),
            output_schema_present=False,
        )
        result = validate_cag_toolchain_node(node, credentials={"wolfram.cag.compute": _entitled_credential()})
        assert result.ok is False
        assert any("output schema" in f for f in result.findings)

    def test_node_unknown_capability_is_rejected(self):
        node = CagToolchainNode(
            node_id="cag-node-1",
            capability_id="wolfram.cag.totally_fake",
            effect="read",
            contract_sha256="a" * 64,
            output_schema_present=True,
        )
        result = validate_cag_toolchain_node(node)
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.BLOCKED
        assert any("unknown CAG capability" in f for f in result.findings)

    def test_node_stale_contract_hash_is_rejected(self):
        node = CagToolchainNode(
            node_id="cag-node-1",
            capability_id="wolfram.cag.compute",
            effect="read",
            contract_sha256="0" * 64,  # wrong hash
            output_schema_present=True,
        )
        result = validate_cag_toolchain_node(node, credentials={"wolfram.cag.compute": _entitled_credential()})
        assert result.ok is False
        assert any("does not match canonical" in f for f in result.findings)

    def test_node_contract_method_enforces_read_only_effect(self):
        # The validate_contract helper also rejects write effects directly.
        node = CagToolchainNode(
            node_id="cag-node-1",
            capability_id="wolfram.cag.compute",
            effect="workspace-write",
            contract_sha256="a" * 64,
            output_schema_present=True,
        )
        with pytest.raises(ValueError, match="only 'read' is permitted"):
            node.validate_contract()

# ---------------------------------------------------------------------------
# Contract inventory
# ---------------------------------------------------------------------------


class TestContractInventory:
    def test_inventory_lists_all_four_capabilities_read_only(self):
        inventory = cag_contract_inventory()
        assert inventory["ok"] is True
        assert inventory["effectClass"] == "read_only"
        assert inventory["mutationPerformed"] is False
        assert inventory["secretValuesReturned"] is False
        assert inventory["runtimeVerified"] is False  # honest: repo-only
        assert {n["capabilityId"] for n in inventory["nodes"]} == EXPECTED_CAPABILITIES
        for node in inventory["nodes"]:
            assert node["effectClass"] == "read_only"
            assert node["mutates"] == "false"

    def test_inventory_contract_hashes_match_component_contracts(self):
        inventory = cag_contract_inventory()
        for node in inventory["nodes"]:
            component = WOLFRAM_CAG_COMPONENT_MAP[node["capabilityId"]]
            assert node["contractSha256"] == _component_contract_sha256(component)

    def test_inventory_is_secret_free(self):
        inventory = cag_contract_inventory()
        blob = str(inventory)
        assert "credential" not in blob.lower()
        assert "api_key" not in blob.lower()
        # base URLs are component contract metadata, not secrets; ensure no
        # token-shaped material leaks.
        assert "token" not in blob.lower()


# ---------------------------------------------------------------------------
# Teaching
# ---------------------------------------------------------------------------


class TestTeachingAssess:
    def test_assess_real_capabilities_without_credential_is_unavailable(self):
        result = teaching_package_assess(
            "cag-basics",
            ["wolfram.cag.compute", "wolfram.cag.results"],
        )
        assert result.ok is False
        assert result.assessed_capabilities == ("wolfram.cag.compute", "wolfram.cag.results")
        assert result.unknown_capabilities == ()
        assert result.provision_status is WolframCagStatus.UNAVAILABLE

    def test_assess_with_entitled_credentials_passes(self):
        creds = {
            "wolfram.cag.compute": _entitled_credential(),
            "wolfram.cag.results": _entitled_credential(),
        }
        result = teaching_package_assess("cag-basics", list(creds), credentials=creds)
        assert result.ok is True
        assert result.provision_status is WolframCagStatus.AVAILABLE

    def test_assess_rejects_unknown_capabilities(self):
        result = teaching_package_assess(
            "cag-bad",
            ["wolfram.cag.compute", "wolfram.cag.totally_fake"],
            credentials={"wolfram.cag.compute": _entitled_credential()},
        )
        assert result.ok is False
        assert "wolfram.cag.totally_fake" in result.unknown_capabilities
        assert result.assessed_capabilities == ("wolfram.cag.compute",)

    def test_assess_empty_capabilities_fails(self):
        result = teaching_package_assess("cag-empty", [])
        assert result.ok is False
        assert any("at least one" in f for f in result.findings)

    def test_assess_mixed_entitlement_reports_worst_honestly(self):
        creds = {
            "wolfram.cag.compute": _entitled_credential(),
            "wolfram.cag.results": _not_entitled_credential(),
        }
        result = teaching_package_assess("cag-mixed", list(creds), credentials=creds)
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.NOT_ENTITLED


class TestTeachingSimulate:
    def test_simulate_without_receipt_is_structural_only(self):
        creds = {"wolfram.cag.compute": _entitled_credential()}
        result = teaching_lesson_simulate(
            "lesson-1", "wolfram.cag.compute", credentials=creds
        )
        assert result.ok is False  # no real receipt -> not ok
        assert result.provision_status is WolframCagStatus.AVAILABLE
        assert result.provider_receipt == ""
        assert any("no real provider receipt" in f for f in result.findings)

    def test_simulate_with_real_receipt_passes(self):
        creds = {"wolfram.cag.compute": _entitled_credential()}
        result = teaching_lesson_simulate(
            "lesson-1",
            "wolfram.cag.compute",
            credentials=creds,
            real_provider_receipt="real-receipt-abc-123",
        )
        assert result.ok is True
        assert result.provider_receipt == "real-receipt-abc-123"

    def test_simulate_without_credential_is_unavailable_and_no_receipt(self):
        result = teaching_lesson_simulate("lesson-1", "wolfram.cag.compute")
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.UNAVAILABLE
        assert result.provider_receipt == ""

    def test_simulate_rejects_unknown_capability(self):
        result = teaching_lesson_simulate(
            "lesson-1", "wolfram.cag.totally_fake", real_provider_receipt="x"
        )
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.BLOCKED

    def test_simulate_rejects_empty_receipt(self):
        creds = {"wolfram.cag.compute": _entitled_credential()}
        result = teaching_lesson_simulate(
            "lesson-1", "wolfram.cag.compute", credentials=creds, real_provider_receipt=""
        )
        assert result.ok is False
        assert result.provider_receipt == ""
        assert any("real_provider_receipt" in f for f in result.findings)

    def test_simulate_cannot_fake_receipt_without_provisioning(self):
        # Even if a receipt string is supplied, without entitlement the
        # simulation must not report ok.
        creds = {"wolfram.cag.compute": _not_entitled_credential()}
        result = teaching_lesson_simulate(
            "lesson-1",
            "wolfram.cag.compute",
            credentials=creds,
            real_provider_receipt="real-receipt",
        )
        assert result.ok is False
        assert result.provision_status is WolframCagStatus.NOT_ENTITLED


# ---------------------------------------------------------------------------
# Mirror parity marker
# ---------------------------------------------------------------------------


MIRROR_ROUTING = ROOT / "scripts" / "sovereign-backend" / "agent_runtime" / "wolfram_cag_routing.py"


class TestMirrorParity:
    def test_mirror_copy_exists_and_matches_canonical(self):
        # The mirror must be byte-equivalent to the canonical copy per the
        # repository's mirror-ownership rule.
        canonical = (ROOT / "backend" / "agent_runtime" / "wolfram_cag_routing.py").read_text()
        assert MIRROR_ROUTING.exists(), (
            "mirror copy scripts/sovereign-backend/agent_runtime/wolfram_cag_routing.py is missing"
        )
        assert MIRROR_ROUTING.read_text() == canonical, (
            "mirror copy is not byte-equivalent to the canonical copy"
        )
