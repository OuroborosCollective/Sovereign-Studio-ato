from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import threading

import pytest

import foundation_runtime
import neuro_teaching_tools as tools
from neuromorphic_runtime import ChangeEvent, NeuromorphicLedger, ZERO_SHA256


REVISION_SHA = "a" * 40
POLICY_SHA256 = hashlib.sha256(
    (Path(tools.__file__).resolve().parent / "config" / "sovereign-continuity-policy.json").read_bytes()
).hexdigest()
BASE_TIME = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
WORKSPACE_ID = "job-neuro-teacher"
EVIDENCE_EXCERPT = "Runtime inspection is read-only evidence collection."
SOURCE_DOCUMENT = (
    "# Runtime evidence\n\n"
    + EVIDENCE_EXCERPT
    + "\n\nThis fixture is the authoritative local source for the teaching package.\n"
).encode("utf-8")
SOURCE_SHA256 = hashlib.sha256(SOURCE_DOCUMENT).hexdigest()


class FakeRuntime:
    def __init__(self, repository: Path) -> None:
        self.repository = repository

    def _repo(self, workspace_id: str) -> Path:
        assert workspace_id == WORKSPACE_ID
        return self.repository


class FakeMCP:
    def __init__(self) -> None:
        self.registered: list[tuple[str, object]] = []

    def tool(self, *, annotations):
        def decorator(function):
            self.registered.append((function.__name__, annotations))
            return function

        return decorator


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _registry(*, effect: str = "read", contract_override: str | None = None) -> dict:
    contract = {
        "name": "runtime_health_inspect",
        "description": "Read status and inspect runtime health evidence deterministically.",
        "capabilities": ["observability", "runtime"],
        "effect": effect,
        "annotations": {
            "readOnlyHint": effect == "read",
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": effect == "external-write",
        },
        "parameters": {"type": "object", "properties": {}},
        "outputSchema": {"type": "object"},
    }
    tool = {**contract, "contractSha256": contract_override or _sha(contract)}
    return {
        "schemaVersion": "sovereign.mcp-tool-contract-registry.v1",
        "ok": True,
        "status": "MCP_TOOL_REGISTRY_READY",
        "registrySnapshotSha256": _sha([contract]),
        "toolCount": 1,
        "tools": [tool],
        "truncated": False,
    }


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    state = tmp_path / "routing-state"
    monkeypatch.setenv("SOVEREIGN_TOOL_RANKING_STATE_ROOT", str(state))
    monkeypatch.delenv("SOVEREIGN_NEURO_RUNTIME_STATE_ROOT", raising=False)
    monkeypatch.delenv("SOVEREIGN_NEURO_POLICY_SHA256", raising=False)
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", REVISION_SHA)
    monkeypatch.setattr(tools, "_REGISTRY_PROVIDER", lambda: _registry())
    monkeypatch.setattr(tools, "_RUNTIME", None)
    monkeypatch.setattr(tools, "_MCP", None)
    monkeypatch.setattr(tools, "_REGISTERED", False)
    yield state


def _change_event(
    *,
    event_id: str = "event.neuro-preview-000",
    sequence: int = 0,
    tick: int = 0,
    previous_hash: str = ZERO_SHA256,
    event_time: datetime = BASE_TIME,
    delta_ms: int = 0,
    kind: str = "runtime.change",
    magnitude: int = 4,
    payload: dict | None = None,
    revision_sha: str = REVISION_SHA,
    policy_sha256: str = POLICY_SHA256,
    source: str = "runtime.teacher-test",
) -> ChangeEvent:
    return ChangeEvent.create(
        event_id=event_id,
        system_id="sovereign-studio-ato",
        revision_sha=revision_sha,
        policy_sha256=policy_sha256,
        lane="deterministic-verification",
        tick=tick,
        sequence=sequence,
        event_time=event_time,
        delta_ms=delta_ms,
        kind=kind,
        source=source,
        entity="runtime.health",
        field="status",
        old_hash=f"{sequence:064x}"[-64:],
        new_hash=f"{sequence + 1:064x}"[-64:],
        magnitude=magnitude,
        previous_evidence_sha256=previous_hash,
        causal_parent_sha256=ZERO_SHA256,
        producer_identity="sovereign.test-producer",
        canonical=True,
        payload=payload or {"units": 1, "max_units": 2, "scope": "test"},
    )


def _preview(event: ChangeEvent, *, foundation_kind: str = "work_request", **kwargs):
    return tools.neuro_event_route_preview(
        change_event=event.to_dict(),
        foundation_event_kind=foundation_kind,
        request_id="request.neuro-test",
        session_id="session.neuro-test",
        mission_summary="inspect runtime health evidence",
        required_capabilities=["runtime"],
        allowed_effects=["read"],
        relevance_threshold=1,
        max_tools=3,
        **kwargs,
    )


def _package(contract: dict, *, title: str = "Runtime evidence lesson") -> dict:
    excerpt = EVIDENCE_EXCERPT
    return {
        "schema_version": "1.0",
        "package": {
            "id": "runtime-evidence",
            "title": title,
            "version": "1.0.0",
            "created_at": "2026-08-14T00:00:00Z",
            "language": "en",
            "scope": "read-only runtime evidence",
            "limitations": ["no tool execution"],
            "source_profile_ref": "source-local",
        },
        "provenance": [
            {
                "id": "prov-runtime",
                "source_type": "files",
                "locator": "docs/runtime.md",
                "retrieved_at": "2026-08-14T00:00:00Z",
                "content_hash": SOURCE_SHA256,
                "trust_level": "repository",
                "license_or_policy": "repository-owner-policy",
            }
        ],
        "evidence": [
            {
                "id": "ev-runtime",
                "provenance_ref": "prov-runtime",
                "locator": "docs/runtime.md",
                "excerpt": excerpt,
                "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                "classification": "internal",
            }
        ],
        "knowledge_units": [
            {
                "id": "ku-runtime",
                "claim": "Inspect runtime evidence before drawing a conclusion.",
                "explanation": "The registered read-only contract returns bounded evidence.",
                "scope": "runtime inspection",
                "assumptions": ["live registry available"],
                "evidence_refs": ["ev-runtime"],
                "confidence": "high",
            }
        ],
        "skills": [
            {
                "id": "skill-runtime",
                "title": title,
                "outcome": "A bounded runtime evidence report.",
                "knowledge_refs": ["ku-runtime"],
                "preconditions": ["live registry is available"],
                "inputs_schema": {
                    "type": "object",
                    "properties": {"scope": {"type": "string"}},
                    "required": ["scope"],
                    "additionalProperties": False,
                },
                "steps": [
                    {
                        "id": "inspect",
                        "action": "Inspect runtime health evidence",
                        "why": "Runtime truth requires readback.",
                        "tool_ref": contract,
                    }
                ],
                "verification": {
                    "success_conditions": ["evidence is bounded"],
                    "failure_signals": ["registry drift"],
                    "fallback": "stop and reassess",
                },
                "safety_boundaries": ["read-only", "no automatic execution"],
            }
        ],
        "assessments": [
            {
                "id": "assess-runtime",
                "skill_or_knowledge_ref": "skill-runtime",
                "type": "dry_run",
                "prompt": "Explain the evidence boundary.",
                "rubric": ["names the live contract"],
            }
        ],
        "target_adapters": [
            {
                "id": "adapter-mcp",
                "target_kind": "mcp",
                "format": "lesson",
                "mapping": {"skill": "tool"},
                "write_mode": "read_only",
                "approval_required": False,
            }
        ],
    }


def _write_package(
    repository: Path,
    package: dict,
    *,
    materialize_source: bool = True,
    source_bytes: bytes = SOURCE_DOCUMENT,
) -> tuple[str, str]:
    if materialize_source:
        source = repository / "docs" / "runtime.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(source_bytes)
    relative = "teaching/knowledge_package.json"
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
    path.write_bytes(raw)
    return relative, hashlib.sha256(raw).hexdigest()


def test_registers_exactly_five_tools_with_one_idempotent_local_write() -> None:
    mcp = FakeMCP()
    runtime = object()
    tools.register(mcp, runtime)

    assert [name for name, _annotation in mcp.registered] == [
        "neuro_runtime_contract_status",
        "neuro_event_route_preview",
        "neuro_event_commit",
        "teaching_package_assess",
        "teaching_lesson_simulate",
    ]
    assert [annotation.readOnlyHint for _name, annotation in mcp.registered] == [True, True, False, True, True]
    assert mcp.registered[2][1].idempotentHint is True
    assert all(annotation.openWorldHint is False for _name, annotation in mcp.registered)
    for function in (
        tools.neuro_runtime_contract_status,
        tools.neuro_event_route_preview,
        tools.teaching_package_assess,
        tools.teaching_lesson_simulate,
    ):
        assert getattr(function, "__sovereign_success_tracking_opt_out__", False) is True
    assert getattr(tools.neuro_event_commit, "__sovereign_success_tracking_opt_out__", False) is False


def test_quarantine_is_not_ok_and_never_initializes_or_mutates_state(isolated: Path) -> None:
    event = _change_event()
    result = _preview(event, foundation_kind="unknown_foundation_kind")

    assert result.ok is False
    assert result.status == "NEURO_EVENT_QUARANTINED"
    assert result.mutationPerformed is False
    artifact = result.data["previewArtifact"]
    assert artifact["foundationDecision"]["outcome"] == "quarantined"
    assert artifact["proposal"]["mayExecute"] is False
    assert artifact["proposal"]["selectedToolContracts"] == []
    assert not isolated.exists()


def test_preview_quarantines_stale_revision_and_policy_without_state(isolated: Path) -> None:
    stale_revision = _preview(_change_event(revision_sha="c" * 40))
    stale_policy = _preview(_change_event(policy_sha256="d" * 64))

    assert stale_revision.ok is False
    assert stale_revision.status == "NEURO_EVENT_QUARANTINED"
    assert "revision" in str(stale_revision.blocker).lower()
    assert stale_revision.mutationPerformed is False
    assert stale_policy.ok is False
    assert stale_policy.status == "NEURO_EVENT_QUARANTINED"
    assert "policy" in str(stale_policy.blocker).lower()
    assert stale_policy.mutationPerformed is False
    assert not isolated.exists()


def test_preview_quarantines_future_event_time_and_huge_sqlite_integer_without_state(
    isolated: Path,
) -> None:
    future = _preview(
        _change_event(event_time=datetime(2099, 1, 1, tzinfo=timezone.utc))
    )
    assert future.ok is False
    assert "clock skew" in str(future.blocker)

    huge = _change_event().to_dict()
    huge["temporal"]["tick"] = 2**63
    huge["envelope"]["tick"] = 2**63
    rejected = tools.neuro_event_route_preview(
        huge,
        "measurement",
        "request.neuro-test",
        "session.neuro-test",
        "Inspect runtime health and route bounded evidence",
        ["observability"],
    )
    assert rejected.ok is False
    assert "64-bit" in str(rejected.blocker)
    assert not isolated.exists()


@pytest.mark.parametrize(
    "secret_key",
    [
        "Access-Token",
        "refresh_TOKEN",
        "openrouter_api_key",
        "github_token",
        "oauthToken",
        "databasePassword",
        "webhookSecret",
        "client_secret_value",
        "access_token_value",
        "client_secret_value_data",
        "access_token_raw_value",
        "provider_api_key_material_bytes",
        "database_password_text_string",
        "authorization_header",
        "auth_header",
        "session_cookie",
        "client_secret_json",
        "access_token_payload",
    ],
)
def test_preview_and_commit_reject_secret_key_variants_without_disclosure_or_state(
    isolated: Path,
    secret_key: str,
) -> None:
    secret_value = "value-that-must-never-be-returned-123456789"
    event = _change_event(
        payload={
            "units": 1,
            "max_units": 2,
            "scope": "test",
            secret_key: secret_value,
        }
    )
    rejected_preview = _preview(event)
    assert rejected_preview.ok is False
    assert rejected_preview.status == "NEURO_EVENT_QUARANTINED"
    assert secret_value not in _canonical(rejected_preview.model_dump())
    assert not isolated.exists()

    clean = _preview(_change_event())
    assert clean.ok is True
    forged = json.loads(json.dumps(clean.data["previewArtifact"]))
    forged.pop("previewSha256")
    forged[secret_key] = secret_value
    forged_hash = _sha(forged)
    forged["previewSha256"] = forged_hash
    rejected_commit = tools.neuro_event_commit(
        forged,
        forged_hash,
        ZERO_SHA256,
        0,
    )
    assert rejected_commit.ok is False
    assert secret_value not in _canonical(rejected_commit.model_dump())
    assert not isolated.exists()


@pytest.mark.parametrize(
    "secret_key",
    [
        "client_secret_value_data",
        "access_token_raw_value",
        "provider_api_key_material_bytes",
        "database_password_text_string",
        "authorization_header",
        "auth_header",
        "session_cookie",
        "client_secret_json",
        "access_token_payload",
    ],
)
def test_secret_value_suffix_never_reaches_existing_sqlite_ledger(
    isolated: Path,
    secret_key: str,
) -> None:
    first = _change_event(event_id="event.neuro-secret-sqlite-0")
    first_preview = _preview(first)
    first_artifact = first_preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        first_artifact,
        first_artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True

    second = _change_event(
        event_id="event.neuro-secret-sqlite-1",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME + timedelta(seconds=1),
        delta_ms=1_000,
    )
    second_preview = _preview(second)
    artifact = json.loads(json.dumps(second_preview.data["previewArtifact"]))
    artifact.pop("previewSha256")
    secret_value = "sqlite-must-not-contain-this-value-123456789"
    artifact[secret_key] = secret_value
    artifact_hash = _sha(artifact)
    artifact["previewSha256"] = artifact_hash
    rejected = tools.neuro_event_commit(
        artifact,
        artifact_hash,
        first.event_hash,
        1,
    )
    assert rejected.ok is False
    assert secret_value not in _canonical(rejected.model_dump())

    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        persisted = "\n".join(connection.iterdump())
    assert secret_value not in persisted
    assert secret_key not in persisted


def test_commit_is_cas_bound_and_exact_replay_is_write_free(isolated: Path) -> None:
    first = _change_event()
    preview = _preview(first)
    assert preview.ok is True, preview.model_dump()
    artifact = preview.data["previewArtifact"]

    committed = tools.neuro_event_commit(
        preview_artifact=artifact,
        preview_sha256=artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert committed.ok is True
    assert committed.status == "NEURO_EVENT_COMMITTED"
    assert committed.mutationPerformed is True
    assert committed.data["mayExecute"] is False
    assert committed.evidence["foundationChainVerified"] is True
    assert committed.evidence["crossLedgerCommitComplete"] is True
    assert committed.evidence["admissionReceiptSha256"]
    assert stat.S_IMODE((isolated / "neuro-runtime").stat().st_mode) == 0o700

    replay = tools.neuro_event_commit(
        preview_artifact=artifact,
        preview_sha256=artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert replay.ok is True
    assert replay.status == "NEURO_EVENT_ALREADY_COMMITTED"
    assert replay.mutationPerformed is False
    assert replay.evidence["receiptHash"] == committed.evidence["receiptHash"]

    second = _change_event(
        event_id="event.neuro-preview-001",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME + timedelta(seconds=1),
        delta_ms=1_000,
    )
    second_preview = _preview(second)
    assert second_preview.ok is True
    second_artifact = second_preview.data["previewArtifact"]
    stale = tools.neuro_event_commit(
        preview_artifact=second_artifact,
        preview_sha256=second_artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=1,
    )
    assert stale.ok is False
    assert stale.status == "NEURO_EVENT_COMMIT_REJECTED"
    assert stale.mutationPerformed is False

    with NeuromorphicLedger(isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3") as ledger:
        assert ledger.metrics().observed_events == 1
        assert ledger.verify_integrity().ok is True
    foundation_ledger = foundation_runtime.SQLiteFoundationLedger(
        str(isolated / "neuro-runtime" / "foundation-runtime.sqlite3")
    )
    assert foundation_ledger.count() == 1
    assert foundation_ledger.verify_chain()["valid"] is True


def test_commit_reports_partial_intent_and_recovers_after_foundation_crash(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _change_event(event_id="event.neuro-crash-recovery")
    preview = _preview(event)
    assert preview.ok is True
    artifact = preview.data["previewArtifact"]
    real_record = tools._record_foundation_decision

    def crash_after_nmc(_decision):
        raise RuntimeError("simulated Foundation crash")

    monkeypatch.setattr(tools, "_record_foundation_decision", crash_after_nmc)
    failed = tools.neuro_event_commit(
        preview_artifact=artifact,
        preview_sha256=artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert failed.ok is False
    assert failed.mutationPerformed is True
    assert failed.evidence["eventPersisted"] is True
    assert failed.evidence["recoveryIntentRetained"] is True
    assert failed.evidence["crossLedgerCommitComplete"] is False
    with sqlite3.connect(isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM neuro_admissions WHERE event_id=?",
            (event.event_id,),
        ).fetchone()[0] == "pending"

    degraded = tools.neuro_runtime_contract_status()
    assert degraded.ok is False
    assert degraded.data["admissions"]["pending"] == 1

    monkeypatch.setattr(tools, "_record_foundation_decision", real_record)
    recovered = tools.neuro_event_commit(
        preview_artifact=artifact,
        preview_sha256=artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert recovered.ok is True
    assert recovered.mutationPerformed is True
    assert recovered.evidence["crossLedgerCommitComplete"] is True
    with sqlite3.connect(isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3") as connection:
        assert connection.execute(
            "SELECT status FROM neuro_admissions WHERE event_id=?",
            (event.event_id,),
        ).fetchone()[0] == "complete"


def test_temporal_regression_is_quarantined_before_commit_intent(isolated: Path) -> None:
    first = _change_event(event_id="event.neuro-temporal-head-0")
    first_preview = _preview(first)
    first_artifact = first_preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        first_artifact,
        first_artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True

    regressed = _change_event(
        event_id="event.neuro-temporal-head-1",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME - timedelta(seconds=1),
        delta_ms=0,
    )
    rejected = _preview(regressed)
    assert rejected.ok is False
    assert rejected.status == "NEURO_EVENT_QUARANTINED"
    assert "regresses" in str(rejected.blocker)
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM neuro_admissions WHERE status='pending'"
        ).fetchone()[0] == 0


def test_preappend_chain_failure_compensates_only_own_pending_intent(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _change_event(event_id="event.neuro-chain-compensation")
    preview = _preview(event)
    artifact = preview.data["previewArtifact"]

    def reject_before_append(_ledger, *_args, **_kwargs):
        raise tools._nmc.ChainIntegrityError("simulated pre-append chain rejection")

    monkeypatch.setattr(tools._nmc.NeuromorphicLedger, "ingest", reject_before_append)
    rejected = tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    )
    assert rejected.ok is False
    assert rejected.mutationPerformed is False
    assert rejected.evidence["intentCompensated"] is True
    assert rejected.evidence["recoveryIntentRetained"] is False
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM neuro_admissions").fetchone()[0] == 0


def test_concurrent_cas_loser_compensates_pending_admission(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifacts = []
    for index in range(2):
        event = _change_event(event_id=f"event.neuro-cas-race-{index}")
        preview = _preview(event)
        assert preview.ok is True
        artifacts.append(preview.data["previewArtifact"])

    real_ensure = tools._ensure_commit_intent
    both_intents = threading.Barrier(2)

    def synchronized_ensure(*args, **kwargs):
        result = real_ensure(*args, **kwargs)
        both_intents.wait(timeout=10)
        return result

    monkeypatch.setattr(tools, "_ensure_commit_intent", synchronized_ensure)

    def commit(artifact: dict) -> tools.NeuroTeachingOutput:
        return tools.neuro_event_commit(
            artifact,
            artifact["previewSha256"],
            ZERO_SHA256,
            0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, artifacts))
    assert sum(result.ok for result in results) == 1, _canonical(
        [result.model_dump(mode="json") for result in results]
    )
    loser = next(result for result in results if not result.ok)
    assert loser.status == "NEURO_EVENT_COMMIT_CONFLICT"
    assert loser.mutationPerformed is False
    assert loser.evidence["intentCompensated"] is True
    assert loser.evidence["recoveryIntentRetained"] is False

    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM neuro_admissions WHERE status='pending'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM neuro_admissions WHERE status='complete'"
        ).fetchone()[0] == 1
    assert tools.neuro_runtime_contract_status().ok is True


def test_concurrent_identical_commit_reports_component_replay_from_durable_receipts(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _change_event(event_id="event.neuro-identical-race")
    preview = _preview(event)
    artifact = preview.data["previewArtifact"]
    real_existing = tools._existing_event
    both_prechecks = threading.Barrier(2)
    calls = 0
    calls_lock = threading.Lock()

    def synchronized_existing(path: Path, event_id: str):
        nonlocal calls
        result = real_existing(path, event_id)
        if event_id == event.event_id:
            with calls_lock:
                calls += 1
                should_wait = calls <= 2
            if should_wait:
                both_prechecks.wait(timeout=10)
        return result

    monkeypatch.setattr(tools, "_existing_event", synchronized_existing)

    def commit() -> tools.NeuroTeachingOutput:
        return tools.neuro_event_commit(
            artifact,
            artifact["previewSha256"],
            ZERO_SHA256,
            0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: commit(), range(2)))
    assert all(result.ok for result in results), _canonical(
        [result.model_dump(mode="json") for result in results]
    )
    assert sum(not result.data["receipt"]["replayed"] for result in results) == 1
    assert sum(
        result.data["foundationReceipt"]["replayed"] is False for result in results
    ) == 1
    assert sum(
        result.data["admissionReceipt"]["transitionPerformed"] is True
        for result in results
    ) == 1
    assert len({result.evidence["receiptHash"] for result in results}) == 1
    assert len({result.evidence["foundationEvidenceSha256"] for result in results}) == 1
    assert len({result.evidence["admissionReceiptSha256"] for result in results}) == 1
    for result in results:
        expected_replay = (
            result.data["receipt"]["replayed"] is True
            and result.data["foundationReceipt"]["replayed"] is True
            and result.data["admissionReceipt"]["replayed"] is True
        )
        assert result.evidence["replayed"] is expected_replay
        assert result.status == (
            "NEURO_EVENT_ALREADY_COMMITTED"
            if expected_replay
            else "NEURO_EVENT_COMMITTED"
        )
        assert result.mutationPerformed is any(result.evidence["componentWrites"].values())


def test_parallel_global_quota_is_atomic_and_loser_leaves_no_intent(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOVEREIGN_NEURO_GLOBAL_MAX_EVENTS", "1")
    artifacts = []
    for index in range(2):
        event = _change_event(
            event_id=f"event.neuro-global-race-{index}",
            source=f"runtime.teacher-quota-{index}",
        )
        preview = _preview(event)
        assert preview.ok is True
        artifacts.append(preview.data["previewArtifact"])

    real_quota = tools._global_quota
    both_prechecks = threading.Barrier(2)

    def synchronized_quota(path: Path) -> dict:
        result = real_quota(path)
        both_prechecks.wait(timeout=10)
        return result

    monkeypatch.setattr(tools, "_global_quota", synchronized_quota)

    def commit(artifact: dict) -> tools.NeuroTeachingOutput:
        return tools.neuro_event_commit(
            artifact,
            artifact["previewSha256"],
            ZERO_SHA256,
            0,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(commit, artifacts))
    assert sum(result.ok for result in results) == 1
    loser = next(result for result in results if not result.ok)
    assert loser.status == "NEURO_EVENT_COMMIT_QUOTA_REACHED"
    assert loser.evidence["intentCompensated"] is True
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM neuro_admissions").fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM neuro_admissions WHERE status='pending'"
        ).fetchone()[0] == 0


def test_global_commit_quota_blocks_new_admission_but_allows_exact_replay(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOVEREIGN_NEURO_GLOBAL_MAX_EVENTS", "1")
    first = _change_event(event_id="event.neuro-global-quota-0")
    first_preview = _preview(first)
    assert first_preview.ok is True
    first_artifact = first_preview.data["previewArtifact"]
    committed = tools.neuro_event_commit(
        preview_artifact=first_artifact,
        preview_sha256=first_artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert committed.ok is True

    replay = tools.neuro_event_commit(
        preview_artifact=first_artifact,
        preview_sha256=first_artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert replay.ok is True
    assert replay.status == "NEURO_EVENT_ALREADY_COMMITTED"
    assert replay.mutationPerformed is False

    second = _change_event(
        event_id="event.neuro-global-quota-1",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME + timedelta(seconds=1),
        delta_ms=1_000,
    )
    second_preview = _preview(second)
    assert second_preview.ok is True
    second_artifact = second_preview.data["previewArtifact"]
    blocked = tools.neuro_event_commit(
        preview_artifact=second_artifact,
        preview_sha256=second_artifact["previewSha256"],
        expected_head_sha256=first.event_hash,
        expected_sequence=1,
    )
    assert blocked.ok is False
    assert blocked.status == "NEURO_EVENT_COMMIT_QUOTA_REACHED"
    assert blocked.mutationPerformed is False
    assert blocked.evidence["eventPersisted"] is False
    assert blocked.evidence["recoveryIntentRetained"] is False
    with sqlite3.connect(isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM neuro_admissions").fetchone()[0] == 1


def test_sensor_features_only_expose_spikes_as_candidate_evidence() -> None:
    event = _change_event(kind="sensor.change", magnitude=5)
    no_spike = _preview(
        event,
        sensor_features=[{"sensorId": "sensor.primary", "tick": 1, "magnitude": 0}],
    )
    assert no_spike.ok is True
    no_spike_artifact = no_spike.data["previewArtifact"]
    assert no_spike_artifact["classification"] == "discarded"
    assert no_spike_artifact["spikeFilter"]["spikeEvidence"] == []
    assert no_spike_artifact["proposal"]["selectedToolContracts"] == []

    spiked = tools.neuro_event_route_preview(
        change_event=event.to_dict(),
        foundation_event_kind="work_request",
        request_id="request.neuro-test",
        session_id="session.neuro-test",
        mission_summary="inspect runtime health evidence",
        required_capabilities=["runtime"],
        allowed_effects=["read"],
        relevance_threshold=3,
        max_tools=3,
        sensor_features=[{"sensorId": "sensor.primary", "tick": 1, "magnitude": 3}],
    )
    assert spiked.ok is True
    spike_artifact = spiked.data["previewArtifact"]
    assert spike_artifact["classification"] == "candidate"
    assert spike_artifact["spikeFilter"]["spikeCount"] == 1
    assert spike_artifact["proposal"]["proposalOnly"] is True
    assert spike_artifact["proposal"]["autoExecute"] is False

    pressure = tools.neuro_event_route_preview(
        change_event=event.to_dict(),
        foundation_event_kind="work_request",
        request_id="request.neuro-test",
        session_id="session.neuro-test",
        mission_summary="inspect runtime health evidence",
        required_capabilities=["runtime"],
        allowed_effects=["read"],
        relevance_threshold=1,
        max_tools=3,
        resource_pressure={
            "queueUnits": 12,
            "activeWorkers": 1,
            "unitsPerWorker": 4,
            "minWorkers": 1,
            "maxWorkers": 4,
            "maxAdjustment": 1,
        },
    )
    assert pressure.ok is True
    advisory = pressure.data["previewArtifact"]["resourceHomeostat"]
    assert advisory["enabled"] is True
    assert advisory["target_workers"] == 2
    assert advisory["advisoryOnly"] is True
    assert advisory["mayExecute"] is False
    assert advisory["actuatorAvailable"] is False


def test_discarded_preview_commit_has_hash_bound_no_registry_admission() -> None:
    event = _change_event(kind="sensor.change", magnitude=5)
    preview = _preview(
        event,
        sensor_features=[{"sensorId": "sensor.primary", "tick": 1, "magnitude": 0}],
    )
    assert preview.ok is True
    artifact = preview.data["previewArtifact"]
    assert artifact["classification"] == "discarded"
    assert artifact["proposal"]["registrySnapshotSha256"] == tools.DISCARDED_NO_REGISTRY_SHA256
    committed = tools.neuro_event_commit(
        preview_artifact=artifact,
        preview_sha256=artifact["previewSha256"],
        expected_head_sha256=ZERO_SHA256,
        expected_sequence=0,
    )
    assert committed.ok is True
    assert committed.data["admissionReceipt"]["classification"] == "discarded"
    status = tools.neuro_runtime_contract_status()
    assert status.ok is True, status.model_dump()
    assert status.data["admissions"]["integrityStatus"] == "VERIFIED"


def test_teaching_assessment_rejects_stale_contract_and_effect_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live = _registry()
    live_tool = live["tools"][0]

    stale_package = _package(
        {"name": live_tool["name"], "contractSha256": "d" * 64, "effect": live_tool["effect"]}
    )
    relative, package_sha = _write_package(repository, stale_package)
    stale = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert stale.ok is False
    assert any("contract is stale" in item for item in stale.data["assessmentReceipt"]["errors"])

    mismatch_package = _package(
        {"name": live_tool["name"], "contractSha256": live_tool["contractSha256"], "effect": "workspace-write"}
    )
    relative, package_sha = _write_package(repository, mismatch_package)
    mismatch = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert mismatch.ok is False
    assert any("effect mismatch" in item for item in mismatch.data["assessmentReceipt"]["errors"])


def test_lesson_requires_success_receipt_is_bounded_and_grammar_hashes_reconstruct(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    long_title = "Runtime evidence " + ("bounded lesson segment. " * 500)
    package = _package(
        {
            "name": live_tool["name"],
            "contractSha256": live_tool["contractSha256"],
            "effect": live_tool["effect"],
        },
        title=long_title,
    )
    relative, package_sha = _write_package(repository, package)
    before = (repository / relative).read_bytes()
    assessment = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert assessment.ok is True, assessment.model_dump()

    lesson = tools.teaching_lesson_simulate(
        WORKSPACE_ID,
        relative,
        package_sha,
        assessment.data["assessmentReceipt"],
        "skill-runtime",
        exercise_inputs={"scope": "runtime"},
        max_output_chars=700,
    )
    assert lesson.ok is True
    assert lesson.status == "TEACHING_LESSON_SIMULATED"
    assert len(lesson.data["lesson"]) <= 700
    assert lesson.data["truncated"] is True
    assert lesson.data["grammarAtlas"]["reconstructionVerified"] is True
    assert lesson.data["grammarAtlas"]["atlasSha256"]
    assert lesson.data["mayExecute"] is False
    assert (repository / relative).read_bytes() == before

    wrong_type = tools.teaching_lesson_simulate(
        WORKSPACE_ID,
        relative,
        package_sha,
        assessment.data["assessmentReceipt"],
        "skill-runtime",
        exercise_inputs={"scope": 7},
    )
    assert wrong_type.ok is False
    assert wrong_type.status == "TEACHING_LESSON_REJECTED"
    assert "must be string" in str(wrong_type.blocker)

    tampered_receipt = dict(assessment.data["assessmentReceipt"])
    tampered_receipt["packageSha256"] = "e" * 64
    rejected = tools.teaching_lesson_simulate(
        WORKSPACE_ID,
        relative,
        package_sha,
        tampered_receipt,
        "skill-runtime",
        exercise_inputs={"scope": "runtime"},
    )
    assert rejected.ok is False
    assert rejected.status == "TEACHING_LESSON_REJECTED"


def test_teacher_rejects_secret_literal_and_undefined_license(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    contract = {
        "name": live_tool["name"],
        "contractSha256": live_tool["contractSha256"],
        "effect": live_tool["effect"],
    }

    unlicensed = _package(contract)
    unlicensed["provenance"][0]["license_or_policy"] = "unknown"
    relative, package_sha = _write_package(repository, unlicensed)
    rejected_license = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert rejected_license.ok is False
    assert any("license_or_policy" in item for item in rejected_license.data["assessmentReceipt"]["errors"])

    for denied in ("FORBIDDEN_BY_OWNER_POLICY", "opaque-custom-license-value"):
        denied_package = _package(contract)
        denied_package["provenance"][0]["license_or_policy"] = denied
        relative, package_sha = _write_package(repository, denied_package)
        denied_result = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
        assert denied_result.ok is False
        assert any(
            "license_or_policy" in item
            for item in denied_result.data["assessmentReceipt"]["errors"]
        )

    unsupported_schema = _package(contract)
    unsupported_schema["skills"][0]["inputs_schema"]["anyOf"] = []
    relative, package_sha = _write_package(repository, unsupported_schema)
    rejected_schema = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert rejected_schema.ok is False
    assert any(
        "unsupported keywords" in item
        for item in rejected_schema.data["assessmentReceipt"]["errors"]
    )

    secret = _package(contract)
    secret["package"]["scope"] = "api_key=sk-1234567890abcdefghijklmnop"
    relative, package_sha = _write_package(repository, secret)
    rejected_secret = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert rejected_secret.ok is False
    assert "secret-like literal" in str(rejected_secret.blocker)


@pytest.mark.parametrize(
    ("section", "field", "value", "expected_error"),
    [
        ("provenance", "source_type", "filesystem", "source_type"),
        ("provenance", "retrieved_at", "2026-08-14T01:00:00+01:00", "retrieved_at"),
        ("provenance", "trust_level", "authoritative", "trust_level"),
        ("provenance", "trust_level", "external-unverified", "trust_level"),
        ("evidence", "classification", "credential", "classification"),
        ("evidence", "classification", "secret", "classification"),
        ("evidence", "classification", "unknown", "classification"),
        ("evidence", "classification", "pending", "classification"),
    ],
)
def test_teacher_provenance_hard_boundary_rejects_unresolved_or_sensitive_labels(
    tmp_path: Path,
    section: str,
    field: str,
    value: str,
    expected_error: str,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    package = _package(
        {
            "name": live_tool["name"],
            "contractSha256": live_tool["contractSha256"],
            "effect": live_tool["effect"],
        }
    )
    package[section][0][field] = value
    relative, package_sha = _write_package(repository, package)
    result = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert result.ok is False
    assert any(
        expected_error in error
        for error in result.data["assessmentReceipt"]["errors"]
    )


def test_teacher_binds_package_source_and_excerpt_to_local_regular_files(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    contract = {
        "name": live_tool["name"],
        "contractSha256": live_tool["contractSha256"],
        "effect": live_tool["effect"],
    }

    valid_package = _package(contract)
    relative, package_sha = _write_package(repository, valid_package)
    valid = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert valid.ok is True, valid.model_dump()
    assert valid.data["assessmentReceipt"]["packageLocator"] == relative

    fragment_bound = _package(contract)
    fragment_bound["evidence"][0]["locator"] = "docs/runtime.md#L3"
    relative, package_sha = _write_package(repository, fragment_bound)
    valid_fragment = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert valid_fragment.ok is True, valid_fragment.model_dump()

    mismatched_locator = _package(contract)
    mismatched_locator["evidence"][0]["locator"] = "docs/nonexistent.md"
    relative, package_sha = _write_package(repository, mismatched_locator)
    rejected_locator = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert rejected_locator.ok is False
    assert any(
        "locator is not bound" in error
        for error in rejected_locator.data["assessmentReceipt"]["errors"]
    )

    fabricated = _package(contract)
    fabricated_excerpt = "This excerpt is correctly hashed but absent from the source."
    fabricated["evidence"][0]["excerpt"] = fabricated_excerpt
    fabricated["evidence"][0]["content_hash"] = hashlib.sha256(
        fabricated_excerpt.encode("utf-8")
    ).hexdigest()
    relative, package_sha = _write_package(repository, fabricated)
    rejected_excerpt = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert rejected_excerpt.ok is False
    assert any(
        "not present byte-exactly" in error
        for error in rejected_excerpt.data["assessmentReceipt"]["errors"]
    )


def test_teacher_rejects_future_package_and_retrieval_times_with_fixed_clock(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    live_tool = _registry()["tools"][0]
    contract = {
        "name": live_tool["name"],
        "contractSha256": live_tool["contractSha256"],
        "effect": live_tool["effect"],
    }
    package = _package(contract)
    _write_package(repository, package)

    package["provenance"][0]["retrieved_at"] = "2099-01-01T00:00:00Z"
    package["package"]["created_at"] = "2099-01-01T00:00:00Z"
    errors, _warnings, _tools, _atlas = tools._validate_package(
        package,
        _registry(),
        repository=repository,
        validation_now=BASE_TIME,
    )
    assert any("retrieved_at" in error and "future" in error for error in errors)
    assert any("package.created_at" in error and "future" in error for error in errors)

    within_skew = _package(contract)
    within_skew["provenance"][0]["retrieved_at"] = "2026-08-14T12:04:59Z"
    within_skew["package"]["created_at"] = "2026-08-14T12:04:59Z"
    errors, _warnings, _tools, _atlas = tools._validate_package(
        within_skew,
        _registry(),
        repository=repository,
        validation_now=BASE_TIME,
    )
    assert not any("future" in error for error in errors)


@pytest.mark.parametrize("case", ["missing", "wrong-hash", "traversal", "symlink"])
def test_teacher_rejects_unverified_local_provenance_files(tmp_path: Path, case: str) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    package = _package(
        {
            "name": live_tool["name"],
            "contractSha256": live_tool["contractSha256"],
            "effect": live_tool["effect"],
        }
    )
    materialize_source = True
    if case == "missing":
        materialize_source = False
    elif case == "wrong-hash":
        package["provenance"][0]["content_hash"] = "d" * 64
    elif case == "traversal":
        package["provenance"][0]["locator"] = "../outside.md"
    elif case == "symlink":
        materialize_source = False
        outside = tmp_path / "outside.md"
        outside.write_bytes(SOURCE_DOCUMENT)
        (repository / "docs").mkdir()
        (repository / "docs" / "runtime.md").symlink_to(outside)

    relative, package_sha = _write_package(
        repository, package, materialize_source=materialize_source
    )
    result = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert result.ok is False
    assert any(
        "locator" in error or "content_hash" in error
        for error in result.data["assessmentReceipt"]["errors"]
    )


def test_teacher_rejects_external_source_claiming_repository_internal_trust(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    package = _package(
        {
            "name": live_tool["name"],
            "contractSha256": live_tool["contractSha256"],
            "effect": live_tool["effect"],
        }
    )
    package["provenance"][0].update(
        {
            "source_type": "web",
            "locator": "https://untrusted.example/evidence",
            "trust_level": "repository",
            "license_or_policy": "repository-owner-policy",
        }
    )
    package["evidence"][0]["classification"] = "internal"
    relative, package_sha = _write_package(repository, package)
    result = tools.teaching_package_assess(WORKSPACE_ID, relative, package_sha)
    assert result.ok is False
    errors = result.data["assessmentReceipt"]["errors"]
    assert any("external sources cannot assert repository trust" in error for error in errors)
    assert any("cannot self-assert internal classification" in error for error in errors)


def test_teacher_rejects_symlinked_knowledge_package(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    tools._RUNTIME = FakeRuntime(repository)
    live_tool = _registry()["tools"][0]
    package = _package(
        {
            "name": live_tool["name"],
            "contractSha256": live_tool["contractSha256"],
            "effect": live_tool["effect"],
        }
    )
    outside = tmp_path / "outside-package.json"
    raw = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
    outside.write_bytes(raw)
    (repository / "teaching").mkdir()
    (repository / "teaching" / "knowledge_package.json").symlink_to(outside)
    rejected = tools.teaching_package_assess(
        WORKSPACE_ID,
        "teaching/knowledge_package.json",
        hashlib.sha256(raw).hexdigest(),
    )
    assert rejected.ok is False
    assert "approved repository file" in str(rejected.blocker)


def test_grammar_fallback_recomputes_final_atlas_hash() -> None:
    source = "x" * 2_500
    atlas = tools._segment_text(source, tile_chars=128)
    asserted = atlas["atlasSha256"]
    unsigned = {key: value for key, value in atlas.items() if key != "atlasSha256"}

    assert atlas["mode"] == "fixed-width-fallback"
    assert atlas["reconstructionVerified"] is True
    assert asserted == _sha(unsigned)
    assert atlas["sourceSha256"] == hashlib.sha256(source.encode("utf-8")).hexdigest()


def test_tool_outcome_projection_is_revision_policy_bound_and_replay_safe(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "f" * 64,
        "sequence": 0,
        "tool": "runtime_health_inspect",
        "recordedAtEpoch": 1_786_708_800,
        "recordedAtEpochMs": 1_786_708_800_123,
        "durationMs": 4,
        "executionSuccess": True,
        "positiveOutcome": True,
        "status": "SUCCEEDED",
        "failureFamily": "",
        "missionFingerprint": "1" * 64,
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    first = tools.record_tool_outcome_event(event)
    replay = tools.record_tool_outcome_event(event)
    assert first["ok"] is True and replay["ok"] is True
    assert first["mutationPerformed"] is True
    assert replay["mutationPerformed"] is False
    assert replay["replayed"] is True
    assert replay["eventHash"] == first["eventHash"]

    stale_policy = dict(event)
    stale_policy["eventId"] = "d" * 64
    stale_policy["policySha256"] = "c" * 64
    with pytest.raises(ValueError, match="continuity policy"):
        tools.record_tool_outcome_event(stale_policy)

    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    missing_revision = dict(event)
    missing_revision["eventId"] = "e" * 64
    with pytest.raises(ValueError, match="source revision"):
        tools.record_tool_outcome_event(missing_revision)


@pytest.mark.parametrize(
    "invalid_update",
    [
        {"status": "Authorization: Basic dXNlcjpwYXNzd29yZA=="},
        {"failureFamily": "Cookie: session=protected-value"},
        {"status": "client_secret=protected-value"},
        {"missionFingerprint": "opaque-mission-text"},
        {"recommended": True},
        {"recordedAtEpoch": 4_070_908_800, "recordedAtEpochMs": 4_070_908_800_000},
        {"recordedAtEpoch": 253_402_300_800, "recordedAtEpochMs": 253_402_300_800_000},
    ],
)
def test_direct_tool_outcome_boundary_rejects_untrusted_values_without_state(
    isolated: Path,
    invalid_update: dict[str, object],
) -> None:
    event: dict[str, object] = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "9" * 64,
        "sequence": 0,
        "tool": "mutable_tool",
        "recordedAtEpoch": 1_786_708_800,
        "recordedAtEpochMs": 1_786_708_800_123,
        "durationMs": 1,
        "executionSuccess": True,
        "positiveOutcome": False,
        "status": "REPORTED_NEGATIVE",
        "failureFamily": "REPORTED_FAILURE",
        "missionFingerprint": "",
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    event.update(invalid_update)
    with pytest.raises(ValueError):
        tools.record_tool_outcome_event(event)
    assert not isolated.exists()


@pytest.mark.parametrize("lock_kind", ["symlink", "broken-symlink", "directory"])
def test_tool_outcome_lock_rejects_unsafe_child_without_touching_target(
    isolated: Path,
    lock_kind: str,
) -> None:
    state = isolated / "neuro-runtime"
    state.mkdir(parents=True)
    lock = state / "tool-outcome-neuro.lock"
    sentinel = isolated.parent / f"outcome-lock-sentinel-{lock_kind}"
    before: tuple[bytes, int] | None = None
    if lock_kind == "symlink":
        sentinel.write_text("do-not-touch\n", encoding="utf-8")
        before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)
        lock.symlink_to(sentinel)
    elif lock_kind == "broken-symlink":
        lock.symlink_to(sentinel)
    else:
        lock.mkdir()
    event = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "9" * 64,
        "sequence": 0,
        "tool": "runtime_health_inspect",
        "recordedAtEpoch": 1_786_708_800,
        "recordedAtEpochMs": 1_786_708_800_123,
        "durationMs": 1,
        "executionSuccess": True,
        "positiveOutcome": True,
        "status": "SUCCEEDED",
        "failureFamily": "",
        "missionFingerprint": "1" * 64,
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    with pytest.raises((OSError, RuntimeError)):
        tools.record_tool_outcome_event(event)
    if before is not None:
        assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == before
    elif lock_kind == "broken-symlink":
        assert not sentinel.exists()


def test_tool_outcome_quota_fails_closed_before_second_append(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOVEREIGN_NEURO_OUTCOME_MAX_EVENTS", "1")
    base = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "1" * 64,
        "sequence": 0,
        "tool": "runtime_health_inspect",
        "recordedAtEpoch": 1_786_708_800,
        "recordedAtEpochMs": 1_786_708_800_123,
        "durationMs": 1,
        "executionSuccess": True,
        "positiveOutcome": True,
        "status": "SUCCEEDED",
        "failureFamily": "",
        "missionFingerprint": "2" * 64,
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    tools.record_tool_outcome_event(base)
    second = dict(base)
    second["eventId"] = "2" * 64
    second["recordedAtEpochMs"] += 1
    with pytest.raises(RuntimeError, match="quota"):
        tools.record_tool_outcome_event(second)

    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["toolOutcomeQuota"]["exceeded"] is True
    assert status.data["toolOutcomeQuota"]["usedEvents"] == 1


def test_tool_outcome_first_start_is_concurrency_safe(isolated: Path) -> None:
    def project(index: int) -> dict:
        event = {
            "schemaVersion": "sovereign.tool-event.v1",
            "eventId": f"{index + 1:064x}",
            "sequence": index,
                "tool": "runtime_health_inspect",
                "recordedAtEpoch": 1_786_708_800,
                "recordedAtEpochMs": 1_786_708_800_000 + index,
            "durationMs": 1,
            "executionSuccess": True,
            "positiveOutcome": True,
            "status": "SUCCEEDED",
            "failureFamily": "",
            "missionFingerprint": f"{index + 101:064x}",
            "recommended": False,
            "argumentValuesRecorded": False,
            "secretValuesRecorded": False,
        }
        return tools.record_tool_outcome_event(event)

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(project, range(64)))
    assert all(result["ok"] is True for result in results)
    assert len({result["eventHash"] for result in results}) == 64
    with NeuromorphicLedger(isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3") as ledger:
        assert ledger.metrics().observed_events == 64
        assert ledger.verify_integrity().ok is True


def test_status_fails_closed_on_projection_tamper(isolated: Path) -> None:
    event = _change_event(event_id="event.neuro-projection-tamper")
    preview = _preview(event)
    artifact = preview.data["previewArtifact"]
    committed = tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    )
    assert committed.ok is True
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE projections SET value_hash=?", ("f" * 64,))
        connection.commit()
    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["ledger"]["integrityVerified"] is False
    assert status.data["ledger"]["canonicalVerifierUsed"] is True


def test_status_fails_closed_on_admission_receipt_tamper(isolated: Path) -> None:
    event = _change_event(event_id="event.neuro-admission-tamper")
    preview = _preview(event)
    artifact = preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE neuro_admissions SET preview_sha256=? WHERE event_id=?",
            ("e" * 64, event.event_id),
        )
        connection.commit()
    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["admissions"]["integrityVerified"] is False


def test_status_uses_canonical_foundation_schema_verifier(isolated: Path) -> None:
    event = _change_event(event_id="event.neuro-foundation-header-tamper")
    preview = _preview(event)
    artifact = preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True
    database = isolated / "neuro-runtime" / "foundation-runtime.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=999")
    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["foundationLedger"]["integrityVerified"] is False
    assert status.data["foundationLedger"]["canonicalVerifierUsed"] is True


def test_foundation_object_tamper_degrades_status_and_blocks_commit_preflight(
    isolated: Path,
) -> None:
    first = _change_event(event_id="event.neuro-foundation-object-0")
    first_preview = _preview(first)
    first_artifact = first_preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        first_artifact,
        first_artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True
    nmc_path = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    foundation_path = isolated / "neuro-runtime" / "foundation-runtime.sqlite3"
    with sqlite3.connect(foundation_path) as attacker:
        attacker.execute(
            "CREATE VIEW foundation_shadow_view AS SELECT * FROM foundation_evidence"
        )
    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["foundationLedger"]["integrityVerified"] is False

    second = _change_event(
        event_id="event.neuro-foundation-object-1",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME + timedelta(seconds=1),
        delta_ms=1_000,
    )
    second_preview = _preview(second)
    rejected = tools.neuro_event_commit(
        second_preview.data["previewArtifact"],
        second_preview.data["previewArtifact"]["previewSha256"],
        first.event_hash,
        1,
    )
    assert rejected.ok is False
    with sqlite3.connect(nmc_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM neuro_admissions").fetchone()[0] == 1


def test_status_rejects_foundation_only_or_unadmitted_nmc_evidence(isolated: Path) -> None:
    event = _change_event(event_id="event.neuro-foundation-orphan")
    preview = _preview(event)
    decision = preview.data["previewArtifact"]["foundationDecision"]
    tools._ensure_private_state_root()
    tools._record_foundation_decision(decision)
    foundation_only = tools.neuro_runtime_contract_status()
    assert foundation_only.ok is False
    assert foundation_only.data["admissions"]["integrityVerified"] is False
    assert foundation_only.data["admissions"]["orphanFoundationEntries"] == 1

    foundation_path = isolated / "neuro-runtime" / "foundation-runtime.sqlite3"
    foundation_path.unlink()
    nmc_path = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with NeuromorphicLedger(nmc_path) as ledger:
        ledger.ingest(event)
    nmc_only = tools.neuro_runtime_contract_status()
    assert nmc_only.ok is False
    assert nmc_only.data["admissions"]["integrityVerified"] is False


def test_status_allows_unadmitted_nmc_only_for_tool_outcome_side_channel() -> None:
    event = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "7" * 64,
        "sequence": 0,
        "tool": "mutable_tool",
        "recordedAtEpoch": 1_786_708_800,
        "recordedAtEpochMs": 1_786_708_800_123,
        "durationMs": 1,
        "executionSuccess": True,
        "positiveOutcome": True,
        "status": "SUCCEEDED",
        "failureFamily": "",
        "missionFingerprint": "1" * 64,
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    assert tools.record_tool_outcome_event(event)["ok"] is True
    status = tools.neuro_runtime_contract_status()
    assert status.ok is True, status.model_dump()
    assert status.data["admissions"]["integrityVerified"] is True
    assert status.data["admissions"]["complete"] == 0


def test_schema_tamper_degrades_status_and_blocks_shadow_trigger_followup(
    isolated: Path,
) -> None:
    first = _change_event(event_id="event.neuro-schema-shadow-0")
    first_preview = _preview(first)
    first_artifact = first_preview.data["previewArtifact"]
    assert tools.neuro_event_commit(
        first_artifact,
        first_artifact["previewSha256"],
        ZERO_SHA256,
        0,
    ).ok is True
    database = isolated / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    with sqlite3.connect(database) as attacker:
        attacker.executescript(
            """
            CREATE TABLE shadow_events(canonical_event TEXT NOT NULL);
            CREATE TRIGGER copy_change_event
            AFTER INSERT ON change_events
            BEGIN
                INSERT INTO shadow_events(canonical_event) VALUES(NEW.canonical_event);
            END;
            """
        )

    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["ledger"]["integrityVerified"] is False
    assert status.data["ledger"]["integrityStatus"] == "FAILED"

    second = _change_event(
        event_id="event.neuro-schema-shadow-1",
        sequence=1,
        tick=1,
        previous_hash=first.event_hash,
        event_time=BASE_TIME + timedelta(seconds=1),
        delta_ms=1_000,
    )
    second_preview = _preview(second)
    assert second_preview.ok is True
    second_artifact = second_preview.data["previewArtifact"]
    rejected = tools.neuro_event_commit(
        second_artifact,
        second_artifact["previewSha256"],
        first.event_hash,
        1,
    )
    assert rejected.ok is False
    with sqlite3.connect(database) as check:
        assert check.execute("SELECT COUNT(*) FROM change_events").fetchone()[0] == 1
        assert check.execute("SELECT COUNT(*) FROM shadow_events").fetchone()[0] == 0


def test_status_rejects_symlinked_neuro_database(isolated: Path) -> None:
    external = isolated.parent / "external-neuro.sqlite3"
    with NeuromorphicLedger(external):
        pass
    before = (external.stat().st_mtime_ns, external.read_bytes())
    state = isolated / "neuro-runtime"
    state.mkdir(parents=True)
    (state / "neuromorphic-runtime.sqlite3").symlink_to(external)

    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["ledger"]["integrityVerified"] is False
    assert status.data["ledger"]["canonicalVerifierUsed"] is True
    assert (external.stat().st_mtime_ns, external.read_bytes()) == before


def test_status_and_commit_reject_broken_symlinked_neuro_database(isolated: Path) -> None:
    event = _change_event(event_id="event.neuro-broken-ledger-link")
    preview = _preview(event)
    assert preview.ok is True
    artifact = preview.data["previewArtifact"]

    state = isolated / "neuro-runtime"
    state.mkdir(parents=True)
    database = state / "neuromorphic-runtime.sqlite3"
    database.symlink_to(isolated.parent / "missing-neuro.sqlite3")

    status = tools.neuro_runtime_contract_status()
    assert status.ok is False
    assert status.data["ledger"]["initialized"] is True
    assert status.data["ledger"]["integrityStatus"] == "FAILED"

    rejected = tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    )
    assert rejected.ok is False
    assert database.is_symlink()
    assert not database.exists()


def test_commit_rejects_symlinked_state_root_without_touching_target(isolated: Path) -> None:
    external_root = isolated.parent / "external-state-root"
    external_root.mkdir(mode=0o755)
    isolated.mkdir(parents=True)
    (isolated / "neuro-runtime").symlink_to(external_root, target_is_directory=True)
    before_mode = stat.S_IMODE(external_root.stat().st_mode)
    event = _change_event(event_id="event.neuro-linked-state-root")
    preview = _preview(event)
    assert preview.ok is True
    artifact = preview.data["previewArtifact"]

    rejected = tools.neuro_event_commit(
        artifact,
        artifact["previewSha256"],
        ZERO_SHA256,
        0,
    )
    assert rejected.ok is False
    assert "non-symlink directory" in str(rejected.blocker)
    assert stat.S_IMODE(external_root.stat().st_mode) == before_mode
    assert list(external_root.iterdir()) == []


def test_status_is_read_only_and_reports_private_prototypes(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = tools.neuro_runtime_contract_status()

    assert result.ok is True
    assert result.data["stateInitializedByThisCall"] is False
    assert result.data["ledger"]["initialized"] is False
    assert result.data["privatePrototypes"]["quantizedSpikeFilter"]["active"] is True
    assert result.data["privatePrototypes"]["resourceHomeostat"]["hasActuator"] is False
    assert not isolated.exists()

    monkeypatch.delenv("SOVEREIGN_SOURCE_REVISION", raising=False)
    degraded = tools.neuro_runtime_contract_status()
    assert degraded.ok is False
    assert degraded.data["deploymentBinding"]["ready"] is False
    assert not isolated.exists()
