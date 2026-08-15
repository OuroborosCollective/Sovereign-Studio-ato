"""Tests for idle_live_awareness -- Issue #1327.

Idle Live Awareness: read-only evidence watch with consent boundary.

Covers the issue's required gates:
- no mutation tools reachable from the idle lane (negative structural test)
- head SHA change resets PR-green state
- repeated identical evidence emits no duplicate notification
- 401/403/secret-shaped payloads are not adopted as persistable evidence state
- observe-only / Off / paused / revoked grants emit no notification
- relevance gate emits notification only, never remediation
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from agent_runtime.evidence_collectors import (
    DEGRADED,
    LOST,
    PRESERVED,
    UNVERIFIABLE,
    build_observation,
    collect_github_ci,
    collect_provider,
)
from agent_runtime.idle_live_awareness import (
    AuthorityGrant,
    FORBIDDEN_TOOL_FAMILIES,
    IdleAwarenessContractError,
    IdleMutationBlockedError,
    IdleNotification,
    MODE_OBSERVE,
    MODE_OBSERVE_NOTIFY,
    MODE_OFF,
    PERMITTED_TOOL_FAMILIES,
    RelevanceVerdict,
    TERMINAL_GREEN,
    TRIGGER_AGENT_RUN_TERMINAL,
    TRIGGER_FREELLM_DEPLETED,
    TRIGGER_PR_TERMINAL_GREEN,
    TRIGGER_REQUIRED_CHECK_RED,
    TRIGGER_REVISION_MISMATCH,
    TRIGGER_RUNTIME_DOWN,
    WatchDefinition,
    WatchState,
    assert_no_mutation_tool,
    build_watch_state,
    evaluate_relevance,
    maybe_notify,
    run_idle_watch,
)

SHA = "a" * 40
SHA2 = "b" * 40
SHA64 = "c" * 64


def _green_obs(sha: str = SHA) -> object:
    return collect_github_ci(head_sha=sha, run_id="r1", check_name="ci", conclusion="success", workflow_sha=sha)


def _red_obs(sha: str = SHA) -> object:
    return collect_github_ci(head_sha=sha, run_id="r2", check_name="ci", conclusion="failure", workflow_sha=sha)


def _grant(mode: str = MODE_OBSERVE_NOTIFY, watch_id: str = "w1") -> AuthorityGrant:
    return AuthorityGrant(
        watch_id=watch_id, mode=mode, scope=("github_read",), rate_limit_per_hour=10
    )


def _pr_watch(grant: AuthorityGrant | None = None, watch_id: str = "w1") -> WatchDefinition:
    return WatchDefinition(
        watch_id=watch_id,
        subject_type="pr",
        subject_id="1326",
        trigger=TRIGGER_PR_TERMINAL_GREEN,
        grant=grant or _grant(watch_id=watch_id),
        evidence_sources=("github_read",),
    )


# ---------------------------------------------------------------------------
# Consent / authority model
# ---------------------------------------------------------------------------

def test_invalid_mode_rejected() -> None:
    try:
        _grant(mode="always-allow")
        assert False, "always-allow mode must be rejected"
    except IdleAwarenessContractError:
        pass


def test_off_grant_is_inactive() -> None:
    g = _grant(mode=MODE_OFF)
    assert not g.is_active()
    assert not g.allows_notification()


def test_observe_only_does_not_allow_notification() -> None:
    g = _grant(mode=MODE_OBSERVE)
    assert g.is_active()
    assert not g.allows_notification()


def test_paused_and_revoked_grants_inactive() -> None:
    g_paused = AuthorityGrant(watch_id="w1", mode=MODE_OBSERVE_NOTIFY, scope=("github_read",), rate_limit_per_hour=10, paused=True)
    g_revoked = AuthorityGrant(watch_id="w1", mode=MODE_OBSERVE_NOTIFY, scope=("github_read",), rate_limit_per_hour=10, revoked=True)
    assert not g_paused.is_active()
    assert not g_revoked.allows_notification()


def test_negative_rate_limit_rejected() -> None:
    try:
        AuthorityGrant(watch_id="w1", mode=MODE_OBSERVE, scope=("github_read",), rate_limit_per_hour=-1)
        assert False
    except IdleAwarenessContractError:
        pass


# ---------------------------------------------------------------------------
# Watch definition invariants
# ---------------------------------------------------------------------------

def test_trigger_subject_mismatch_rejected() -> None:
    try:
        WatchDefinition(
            watch_id="w1", subject_type="runtime", subject_id="svc",
            trigger=TRIGGER_PR_TERMINAL_GREEN, grant=_grant(),
        )
        assert False, "runtime subject with pr trigger must be rejected"
    except IdleAwarenessContractError:
        pass


def test_grant_watch_id_must_match() -> None:
    try:
        WatchDefinition(
            watch_id="w1", subject_type="pr", subject_id="1326",
            trigger=TRIGGER_PR_TERMINAL_GREEN, grant=_grant(watch_id="other"),
        )
        assert False
    except IdleAwarenessContractError:
        pass


# ---------------------------------------------------------------------------
# Head SHA change resets PR-green state
# ---------------------------------------------------------------------------

def test_head_sha_change_resets_green_state() -> None:
    watch = _pr_watch()
    # establish green on head A
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t1", previous=None)
    assert r1.verdict.material
    assert r1.notification is not None

    # new head B, also green -> must be material again (green did not carry over)
    r2 = run_idle_watch(watch=watch, observation=_green_obs(SHA2), observed_at="t2", previous=r1.new_state)
    assert r2.verdict.material, "new head must reset green evidence and re-fire"
    assert r2.new_state.first_observed_at == "t2", "first_observed_at must reset on head change"
    assert r2.new_state.bound_revision == SHA2


def test_same_head_repeated_green_suppressed() -> None:
    watch = _pr_watch()
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t1", previous=None)
    assert r1.notification is not None
    # identical green on same head -> suppressed
    r2 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t2", previous=r1.new_state)
    assert not r2.verdict.material
    assert r2.notification is None


# ---------------------------------------------------------------------------
# Repeated identical evidence emits no duplicate notification
# ---------------------------------------------------------------------------

def test_duplicate_evidence_no_notification() -> None:
    watch = _pr_watch()
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t1", previous=None)
    assert r1.notification is not None
    r2 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t2", previous=r1.new_state)
    r3 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t3", previous=r2.new_state)
    assert r2.notification is None and r3.notification is None


# ---------------------------------------------------------------------------
# Notification only, never remediation
# ---------------------------------------------------------------------------

def test_notification_carries_evidence_and_authority_not_permission() -> None:
    watch = _pr_watch()
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t1", previous=None)
    n = r1.notification
    assert n is not None
    assert isinstance(n, IdleNotification)
    assert len(n.notification_hash) == 64
    assert n.evidence_refs
    assert "idle grant" in n.authority_basis
    # authority basis must never contain a merge/deploy/patch permission
    assert "merge" not in n.authority_basis
    assert "deploy" not in n.authority_basis


def test_observe_only_emits_no_notification_even_when_material() -> None:
    watch = _pr_watch(grant=_grant(mode=MODE_OBSERVE))
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t1", previous=None)
    assert r1.verdict.material
    assert r1.notification is None, "observe-only must never notify"


# ---------------------------------------------------------------------------
# Required check red transition
# ---------------------------------------------------------------------------

def test_required_check_red_transition_material() -> None:
    grant = _grant()
    watch = WatchDefinition(
        watch_id="w1", subject_type="pr", subject_id="1326",
        trigger=TRIGGER_REQUIRED_CHECK_RED, grant=grant,
    )
    r0 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t0", previous=None)
    assert r0.notification is None
    r1 = run_idle_watch(watch=watch, observation=_red_obs(SHA), observed_at="t1", previous=r0.new_state)
    assert r1.verdict.material
    assert r1.notification is not None
    # same red state on same head -> suppressed
    r2 = run_idle_watch(watch=watch, observation=_red_obs(SHA), observed_at="t2", previous=r1.new_state)
    assert r2.notification is None


# ---------------------------------------------------------------------------
# Runtime revision mismatch and runtime down
# ---------------------------------------------------------------------------

def test_runtime_revision_mismatch_material() -> None:
    grant = _grant()
    watch = WatchDefinition(
        watch_id="w1", subject_type="runtime", subject_id="backend",
        trigger=TRIGGER_REVISION_MISMATCH, grant=grant,
    )
    r0 = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t0", previous=None)
    r1 = run_idle_watch(watch=watch, observation=_green_obs(SHA2), observed_at="t1", previous=r0.new_state)
    assert r1.verdict.material
    assert r1.notification is not None


def test_runtime_down_transition_material() -> None:
    grant = _grant()
    watch = WatchDefinition(
        watch_id="w1", subject_type="runtime", subject_id="mcp",
        trigger=TRIGGER_RUNTIME_DOWN, grant=grant,
    )
    lost = build_observation(capability_id="runtime.health", collector="health_read", status=LOST, cause="mcp broker unreachable", source_revision=SHA)
    ok = build_observation(capability_id="runtime.health", collector="health_read", status=PRESERVED, cause="mcp broker healthy", source_revision=SHA)
    r0 = run_idle_watch(watch=watch, observation=ok, observed_at="t0", previous=None)
    assert r0.notification is None
    r1 = run_idle_watch(watch=watch, observation=lost, observed_at="t1", previous=r0.new_state)
    assert r1.verdict.material
    assert r1.notification is not None
    # repeated down on same revision -> suppressed
    r2 = run_idle_watch(watch=watch, observation=lost, observed_at="t2", previous=r1.new_state)
    assert r2.notification is None


# ---------------------------------------------------------------------------
# Provider free-LLM depletion / recovery
# ---------------------------------------------------------------------------

def test_provider_depletion_and_recovery_material() -> None:
    grant = _grant()
    watch = WatchDefinition(
        watch_id="w1", subject_type="provider", subject_id="freellm",
        trigger=TRIGGER_FREELLM_DEPLETED, grant=grant,
    )
    healthy = collect_provider(openrouter_paid_route_ok=True, free_route_revision=SHA, free_llm_revolver_ok=True, paid_truth_boundary_hash=SHA64)
    depleted = collect_provider(openrouter_paid_route_ok=False, free_route_revision=SHA, free_llm_revolver_ok=False, paid_truth_boundary_hash=SHA64)
    assert depleted.status == LOST
    r0 = run_idle_watch(watch=watch, observation=healthy, observed_at="t0", previous=None)
    assert r0.notification is None
    r1 = run_idle_watch(watch=watch, observation=depleted, observed_at="t1", previous=r0.new_state)
    assert r1.verdict.material and r1.notification is not None
    # recovery from 0 is material
    r2 = run_idle_watch(watch=watch, observation=healthy, observed_at="t2", previous=r1.new_state)
    assert r2.verdict.material and r2.notification is not None


# ---------------------------------------------------------------------------
# Agent run terminal
# ---------------------------------------------------------------------------

def test_agent_run_terminal_material_once() -> None:
    grant = _grant()
    watch = WatchDefinition(
        watch_id="w1", subject_type="agent-run", subject_id="run-9",
        trigger=TRIGGER_AGENT_RUN_TERMINAL, grant=grant,
    )
    running = build_observation(capability_id="agent.run", collector="runtime_read", status=UNVERIFIABLE, cause="run still in progress", source_revision=SHA)
    done = build_observation(capability_id="agent.run", collector="runtime_read", status=PRESERVED, cause="run completed terminal", source_revision=SHA)
    r0 = run_idle_watch(watch=watch, observation=running, observed_at="t0", previous=None)
    assert r0.notification is None
    r1 = run_idle_watch(watch=watch, observation=done, observed_at="t1", previous=r0.new_state)
    assert r1.verdict.material and r1.notification is not None
    r2 = run_idle_watch(watch=watch, observation=done, observed_at="t2", previous=r1.new_state)
    assert r2.notification is None


# ---------------------------------------------------------------------------
# Secret / 401-shaped payload rejection
# ---------------------------------------------------------------------------

def test_secret_shaped_cause_rejected() -> None:
    watch = _pr_watch()
    secret_obs = build_observation(
        capability_id="ci.check", collector="github_ci", status=PRESERVED,
        cause="ok github_pat_11B7O43JQ0TYSECRETVALUE", source_revision=SHA,
    )
    try:
        build_watch_state(watch=watch, observation=secret_obs, observed_at="t", previous=None)
        assert False, "secret-shaped cause must be rejected"
    except IdleAwarenessContractError:
        pass


def test_secret_shaped_detail_rejected() -> None:
    watch = _pr_watch()
    secret_obs = build_observation(
        capability_id="ci.check", collector="github_ci", status=PRESERVED,
        cause="ok", source_revision=SHA,
        detail={"token": "ghp_AAAAAAAAAAAAAAABBBBBBBBBBBBBB"},
    )
    try:
        build_watch_state(watch=watch, observation=secret_obs, observed_at="t", previous=None)
        assert False, "secret-shaped detail must be rejected"
    except IdleAwarenessContractError:
        pass


def test_unverifiable_observation_not_promoted_to_green() -> None:
    watch = _pr_watch()
    unver = build_observation(
        capability_id="ci.check", collector="github_ci", status=UNVERIFIABLE,
        cause="401 unauthorized -- no credentials", source_revision=SHA,
    )
    r0 = run_idle_watch(watch=watch, observation=unver, observed_at="t0", previous=None)
    assert not r0.verdict.material
    assert r0.notification is None
    assert r0.new_state.terminal_label != TERMINAL_GREEN


# ---------------------------------------------------------------------------
# Negative: idle executor cannot call mutation tool families
# ---------------------------------------------------------------------------

def test_every_forbidden_family_blocked() -> None:
    for fam in FORBIDDEN_TOOL_FAMILIES:
        try:
            assert_no_mutation_tool(fam)
            assert False, f"forbidden family {fam} must raise"
        except IdleMutationBlockedError:
            pass


def test_unknown_tool_family_rejected() -> None:
    try:
        assert_no_mutation_tool("something_new")
        assert False
    except IdleAwarenessContractError:
        pass


def test_permitted_read_probes_pass() -> None:
    for fam in PERMITTED_TOOL_FAMILIES:
        assert_no_mutation_tool(fam)  # must not raise


def test_run_idle_watch_uses_only_evidence_collect() -> None:
    # run_idle_watch asserts evidence_collect internally; it must not invoke any mutation
    watch = _pr_watch()
    r = run_idle_watch(watch=watch, observation=_green_obs(SHA), observed_at="t", previous=None)
    assert r.watch_id == "w1"


# ---------------------------------------------------------------------------
# WatchState invariants
# ---------------------------------------------------------------------------

def test_watch_state_rejects_invalid_terminal_label() -> None:
    try:
        WatchState(
            watch_id="w1", subject_type="pr", subject_id="1326",
            bound_revision=SHA, terminal_fingerprint=SHA64, terminal_label="done",
            first_observed_at="t", last_observed_at="t",
        )
        assert False
    except IdleAwarenessContractError:
        pass


def test_relevance_verdict_material_requires_valid_trigger() -> None:
    try:
        RelevanceVerdict(material=True, trigger="bogus", reason="x")
        assert False
    except IdleAwarenessContractError:
        pass


def test_maybe_notify_none_when_not_material() -> None:
    watch = _pr_watch()
    v = RelevanceVerdict(material=False, trigger=TRIGGER_PR_TERMINAL_GREEN, reason="not material")
    assert maybe_notify(watch=watch, observation=_green_obs(SHA), verdict=v, observed_at="t") is None


# ---------------------------------------------------------------------------
# Structural contract: idle_live_awareness is a pure evidence-lane module.
#
# Mirrors the TestNoIOInModule contract enforced on bug_evidence_lane.py: the
# idle watch must be a read-only, non-mutating derivation layer. No file/network
# I/O, no wall-clock time, no database driver. Evidence truth comes exclusively
# from reusing evidence_collectors, never from this module touching the world.
# ---------------------------------------------------------------------------

def _module_source() -> str:
    import importlib
    import inspect

    # The agent-runtime test suites are invoked from two working directories:
    # repo root (``backend.agent_runtime``) and ``backend`` (``agent_runtime``).
    # Resolve the module under whichever import root is active so the structural
    # contract holds in both CI invocation modes.
    mod = None
    for module_path in ("backend.agent_runtime.idle_live_awareness", "agent_runtime.idle_live_awareness"):
        try:
            mod = importlib.import_module(module_path)
            break
        except ModuleNotFoundError:
            continue
    assert mod is not None, "could not import idle_live_awareness under either import root"

    return inspect.getsource(mod)


def test_module_has_no_open_calls() -> None:
    assert "open(" not in _module_source()


def test_module_has_no_socket_or_requests() -> None:
    src = _module_source()
    assert "import socket" not in src
    assert "import requests" not in src
    assert "import urllib.request" not in src
    assert "import aiohttp" not in src


def test_module_has_no_time_or_datetime() -> None:
    src = _module_source()
    assert "import time" not in src
    assert "import datetime" not in src


def test_module_has_no_psycopg2() -> None:
    assert "psycopg2" not in _module_source()


# ---------------------------------------------------------------------------
# Mirror parity: canonical and deployment copies must stay byte-identical.
# ---------------------------------------------------------------------------

def test_idle_live_awareness_mirror_byte_identical() -> None:
    import hashlib
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    canonical = repo_root / "backend" / "agent_runtime" / "idle_live_awareness.py"
    production = repo_root / "scripts" / "sovereign-backend" / "agent_runtime" / "idle_live_awareness.py"

    assert production.is_file(), f"missing production mirror: {production}"
    assert (
        hashlib.sha256(canonical.read_bytes()).hexdigest()
        == hashlib.sha256(production.read_bytes()).hexdigest()
    ), "byte-drift between canonical and deployment mirror of idle_live_awareness.py"


# ---------------------------------------------------------------------------
# Integration: PR #1326 canary -- full read-only pipeline over real inputs.
#
# This feeds real CollectorObservation inputs (built via evidence_collectors)
# through the real run_idle_watch pipeline. No GitHub API is hit; the inputs
# stand in for parsed real readbacks. The point is to prove the pipeline's
# causal chain end-to-end: head change resets green, green emits exactly one
# notification, identical repeat is suppressed, and observe-only never notifies.
# ---------------------------------------------------------------------------

def test_pr_canary_full_pipeline_green_transition_then_suppressed() -> None:
    watch = _pr_watch()
    head_a = "a" * 40
    head_b = "b" * 40

    # tick 1: not yet green (red) -- no notification, no green fingerprint
    red = _red_obs(head_a)
    r1 = run_idle_watch(watch=watch, observation=red, observed_at="t1")
    assert r1.notification is None
    assert r1.verdict.material is False
    assert r1.new_state.terminal_label != TERMINAL_GREEN

    # tick 2: terminal green on same head -- one material notification
    green = _green_obs(head_a)
    r2 = run_idle_watch(watch=watch, observation=green, observed_at="t2", previous=r1.new_state)
    assert r2.notification is not None
    assert r2.notification.trigger == TRIGGER_PR_TERMINAL_GREEN
    assert r2.notification.subject_id == "1326"
    assert r2.notification.observed_revision == head_a
    # notification carries evidence + authority basis, never a mutation permission
    assert "idle grant" in r2.notification.authority_basis
    assert r2.notification.evidence_refs == (green.observation_hash,)

    # tick 3: identical green repeat -- suppressed (no duplicate)
    green2 = _green_obs(head_a)
    r3 = run_idle_watch(watch=watch, observation=green2, observed_at="t3", previous=r2.new_state)
    assert r3.notification is None

    # tick 4: head changes -- green state resets; green on new head must re-evaluate
    green_b = _green_obs(head_b)
    r4 = run_idle_watch(watch=watch, observation=green_b, observed_at="t4", previous=r3.new_state)
    # new head re-evaluates and, being green, emits exactly one fresh notification
    assert r4.notification is not None
    assert r4.notification.observed_revision == head_b


def test_pr_canary_observe_only_never_notifies_even_on_green() -> None:
    watch = _pr_watch(grant=_grant(mode=MODE_OBSERVE))
    green = _green_obs(SHA)
    r = run_idle_watch(watch=watch, observation=green, observed_at="t1")
    assert r.verdict.material is True
    assert r.notification is None  # observe-only: detect, but never notify
