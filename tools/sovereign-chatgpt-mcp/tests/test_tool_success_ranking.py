from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

import tool_success_ranking as ranking


def _state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ranking, "_STATE_ROOT", tmp_path)
    monkeypatch.setattr(ranking, "_EVENTS_PATH", tmp_path / "tool-events.jsonl")
    monkeypatch.setattr(ranking, "_SNAPSHOT_PATH", tmp_path / "tool-ranking.json")
    monkeypatch.setattr(ranking, "_AGGREGATES", None)
    monkeypatch.setattr(ranking, "_PROJECTION_CACHE_KEY", "")
    monkeypatch.setattr(ranking, "_PROJECTION_STATS", {})
    monkeypatch.setattr(ranking, "_SNAPSHOT_MTIME_NS", -1)


def test_repeated_reliable_tools_rank_above_less_reliable_tools(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    for _ in range(12):
        ranking.record_event("repository_read_file", outcome=ranking.Outcome(True, True, "COMPLETED", ""), duration_ms=10)
    for _ in range(4):
        ranking.record_event("repository_hash_bound_replace", outcome=ranking.Outcome(True, True, "COMPLETED", ""), duration_ms=20)
    ranking.record_event("repository_hash_bound_replace", outcome=ranking.Outcome(False, False, "EXCEPTION", "RuntimeError"), duration_ms=20)
    result = ranking.ranking_snapshot(limit=10)
    assert [item["tool"] for item in result["tools"][:2]] == ["repository_read_file", "repository_hash_bound_replace"]
    assert result["argumentValuesRecorded"] is False
    assert result["secretValuesRecorded"] is False


def test_events_store_only_mission_fingerprint_and_no_argument_values(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    secret_like = "github_pat_" + "x" * 40
    with ranking.mission_scope(f"Use protected value {secret_like}"):
        ranking.record_event(
            "repository_pr_status",
            outcome=ranking.Outcome(True, False, "BLOCKED", "EXPECTED_HEAD_MISMATCH"),
            duration_ms=5,
        )
    raw = ranking._EVENTS_PATH.read_text("utf-8")
    payload = json.loads(raw.strip())
    assert secret_like not in raw
    assert len(payload["missionFingerprint"]) == 64
    assert payload["argumentValuesRecorded"] is False
    assert payload["secretValuesRecorded"] is False
    assert payload["executionSuccess"] is True
    assert payload["positiveOutcome"] is False


def test_wrapper_records_success_and_exception(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)

    def healthy(value: int) -> dict:
        return {"ok": True, "status": "COMPLETED", "value": value}

    def broken() -> dict:
        raise RuntimeError("boom")

    assert ranking._wrap_callable("healthy_tool", healthy)(3)["value"] == 3
    with pytest.raises(RuntimeError):
        ranking._wrap_callable("broken_tool", broken)()
    tools = {item["tool"]: item for item in ranking.ranking_snapshot(limit=10)["tools"]}
    assert tools["healthy_tool"]["executionSuccesses"] == 1
    assert tools["broken_tool"]["executionFailures"] == 1


def test_explicit_read_only_opt_out_skips_state_but_other_tools_keep_ranking(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _state(monkeypatch, tmp_path)

    def read_only_status() -> dict:
        return {"ok": True, "status": "READY"}

    setattr(read_only_status, "__sovereign_success_tracking_opt_out__", True)
    assert ranking._wrap_callable("read_only_status", read_only_status) is read_only_status
    assert read_only_status()["ok"] is True
    assert not ranking._EVENTS_PATH.exists()
    assert not ranking._SNAPSHOT_PATH.exists()

    def normal_tool() -> dict:
        return {"ok": True, "status": "COMPLETED"}

    wrapped = ranking._wrap_callable("normal_tool", normal_tool)
    assert wrapped is not normal_tool
    assert wrapped()["ok"] is True
    snapshot = ranking.ranking_snapshot(limit=10)
    assert [item["tool"] for item in snapshot["tools"]] == ["normal_tool"]


def test_recommendations_alone_never_create_history_bonus(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    ranking.record_recommendations(["repository_read_file"], "Read one file")
    assert ranking.historical_bonus("repository_read_file") == 0
    assert list(tmp_path.iterdir()) == []
    for _ in range(30):
        ranking.record_event("repository_read_file", outcome=ranking.Outcome(True, True, "COMPLETED", ""), duration_ms=1)
    assert 1 <= ranking.historical_bonus("repository_read_file") <= 80


def test_event_projection_updates_incrementally_without_rescanning_history(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "0")
    original_read = ranking._read_events
    reads = 0

    def counted_read() -> list[dict]:
        nonlocal reads
        reads += 1
        return original_read()

    monkeypatch.setattr(ranking, "_read_events", counted_read)
    for _ in range(3):
        ranking.record_event(
            "repository_read_file",
            outcome=ranking.Outcome(True, True, "COMPLETED", ""),
            duration_ms=2,
        )
    snapshot = ranking.ranking_snapshot(limit=10)

    assert reads == 1
    assert snapshot["projection"]["mode"] == "event-driven-incremental"
    assert snapshot["projection"]["processedEventCount"] == 3
    assert snapshot["projection"]["incrementalUpdateCount"] == 3
    assert snapshot["projection"]["recoveryFullScanCount"] == 1
    assert snapshot["tools"][0]["invocations"] == 3


def test_cold_start_replays_only_durable_tail_after_snapshot_crash(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "0")
    ranking.record_event(
        "repository_read_file",
        outcome=ranking.Outcome(True, True, "COMPLETED", ""),
        duration_ms=2,
    )

    # Model a process crash after fsync(JSONL), before projection replacement.
    tail = {
        "schemaVersion": "sovereign.tool-event.v1",
        "eventId": "a" * 64,
        "sequence": 1,
        "tool": "repository_read_file",
        "recordedAtEpoch": 1,
        "recordedAtEpochMs": 1_000,
        "durationMs": 3,
        "executionSuccess": True,
        "positiveOutcome": True,
        "status": "COMPLETED",
        "failureFamily": "",
        "missionFingerprint": "",
        "recommended": False,
        "argumentValuesRecorded": False,
        "secretValuesRecorded": False,
    }
    with ranking._EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(ranking._canonical(tail) + "\n")

    monkeypatch.setattr(ranking, "_AGGREGATES", None)
    monkeypatch.setattr(ranking, "_PROJECTION_CACHE_KEY", "")
    result = ranking.ranking_snapshot(limit=10)

    assert result["tools"][0]["invocations"] == 2
    assert result["projection"]["processedEventCount"] == 2
    assert result["projection"]["recoveredTailEventCount"] == 1
    assert result["projection"]["historyGapCount"] == 0


def test_tracking_failure_never_replaces_tool_success_or_original_error(monkeypatch) -> None:
    def tracking_failed(*_args, **_kwargs) -> None:
        raise OSError("telemetry unavailable")

    monkeypatch.setattr(ranking, "record_event", tracking_failed)

    def healthy() -> dict:
        return {"ok": True, "status": "COMPLETED"}

    def broken() -> dict:
        raise RuntimeError("primary failure")

    assert ranking._wrap_callable("healthy_tool", healthy)()["ok"] is True
    with pytest.raises(RuntimeError, match="primary failure"):
        ranking._wrap_callable("broken_tool", broken)()


def test_tool_controlled_outcome_text_is_categorized_before_persistence(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "0")
    secret_like = "ghp_" + "x" * 24
    ranking.record_event(
        "repository_pr_status",
        outcome=ranking.Outcome(True, False, f"BLOCKED {secret_like}", secret_like),
        duration_ms=1,
    )

    raw = ranking._EVENTS_PATH.read_text("utf-8")
    assert secret_like not in raw
    payload = json.loads(raw)
    assert payload["status"] == "BLOCKED"
    assert payload["failureFamily"] == "REPORTED_FAILURE"


@pytest.mark.parametrize(
    "secret_literal",
    [
        "password=not-a-real-secret-value-123",
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "client_secret=protected-value",
        "access_token=protected-value",
        "Cookie: session=protected-value",
        "Set-Cookie: session=protected-value",
        "https://user:protected-value@example.invalid/path",
    ],
)
def test_tool_controlled_text_never_reaches_jsonl_snapshot_or_neuro_sqlite(
    monkeypatch,
    tmp_path: Path,
    secret_literal: str,
) -> None:
    state = tmp_path / "ranking-state"
    _state(monkeypatch, state)
    monkeypatch.setenv("SOVEREIGN_TOOL_RANKING_STATE_ROOT", str(state))
    monkeypatch.setenv("SOVEREIGN_SOURCE_REVISION", "a" * 40)
    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "1")
    ranking.record_event(
        "mutable_tool",
        outcome=ranking.Outcome(True, False, secret_literal, secret_literal),
        duration_ms=1,
    )

    assert secret_literal not in ranking._EVENTS_PATH.read_text("utf-8")
    assert secret_literal not in ranking._SNAPSHOT_PATH.read_text("utf-8")
    neuro_database = state / "neuro-runtime" / "neuromorphic-runtime.sqlite3"
    assert neuro_database.is_file()
    with sqlite3.connect(neuro_database) as connection:
        persisted = "\n".join(connection.iterdump())
    assert secret_literal not in persisted
    event = json.loads(ranking._EVENTS_PATH.read_text("utf-8"))
    assert event["status"] == "REPORTED_NEGATIVE"
    assert event["failureFamily"] in {
        "AUTHORIZATION_FAILURE",
        "CONTRACT_VIOLATION",
        "REPORTED_FAILURE",
    }


def test_read_only_snapshots_never_create_or_rewrite_state(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    fresh = ranking.ranking_snapshot(limit=10)
    assert fresh["tools"] == []
    assert fresh["telemetryScope"] == "mutable-tool-outcomes-only"
    assert list(tmp_path.iterdir()) == []

    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "0")
    ranking.record_event(
        "mutable_tool",
        outcome=ranking.Outcome(True, True, "COMPLETED", ""),
        duration_ms=1,
    )
    before = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    ranking.ranking_snapshot(limit=10)
    ranking.historical_bonus_map()
    after = {
        path.name: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    assert after == before


def test_install_opts_out_every_read_only_annotation_and_tracks_mutable_only(
    monkeypatch, tmp_path: Path
) -> None:
    _state(monkeypatch, tmp_path)
    monkeypatch.setenv("SOVEREIGN_NEURO_RUNTIME_TRACKING_ENABLED", "0")

    def inspect_status() -> dict:
        return {"ok": True, "status": "READY"}

    def commit_change() -> dict:
        return {"ok": True, "status": "COMPLETED"}

    read_tool = SimpleNamespace(
        name="inspect_status",
        fn=inspect_status,
        annotations=SimpleNamespace(readOnlyHint=True),
    )
    write_tool = SimpleNamespace(
        name="commit_change",
        fn=commit_change,
        annotations=SimpleNamespace(readOnlyHint=False),
    )
    manager = SimpleNamespace(list_tools=lambda: [read_tool, write_tool])
    receipt = ranking.install_success_tracking(SimpleNamespace(_tool_manager=manager))

    assert receipt["trackedToolCount"] == 1
    assert receipt["optedOutToolCount"] == 1
    assert receipt["telemetryScope"] == "mutable-tool-outcomes-only"
    assert read_tool.fn is inspect_status
    assert read_tool.fn()["ok"] is True
    assert list(tmp_path.iterdir()) == []
    assert write_tool.fn is not commit_change
    assert write_tool.fn()["ok"] is True
    assert ranking._EVENTS_PATH.is_file()


@pytest.mark.parametrize(
    "child_name",
    ["tool-events.jsonl", ".tool-ranking.lock", "tool-ranking.json"],
)
def test_ranking_child_symlinks_never_touch_target_or_primary_result(
    monkeypatch,
    tmp_path: Path,
    child_name: str,
) -> None:
    state = tmp_path / "ranking"
    _state(monkeypatch, state)
    state.mkdir()
    sentinel = tmp_path / f"sentinel-{child_name.replace('.', '_')}"
    sentinel.write_text("do-not-touch\n", encoding="utf-8")
    before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)
    (state / child_name).symlink_to(sentinel)

    def primary() -> dict:
        return {"ok": True, "status": "COMPLETED"}

    wrapped = ranking._wrap_callable("mutable_tool", primary)
    assert wrapped()["ok"] is True
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == before
    assert (state / child_name).is_symlink()
