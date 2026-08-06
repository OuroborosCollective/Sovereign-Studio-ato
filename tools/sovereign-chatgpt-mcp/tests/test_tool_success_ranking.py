from __future__ import annotations

import json
from pathlib import Path

import pytest

import tool_success_ranking as ranking


def _state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ranking, "_STATE_ROOT", tmp_path)
    monkeypatch.setattr(ranking, "_EVENTS_PATH", tmp_path / "tool-events.jsonl")
    monkeypatch.setattr(ranking, "_SNAPSHOT_PATH", tmp_path / "tool-ranking.json")


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


def test_recommendations_alone_never_create_history_bonus(monkeypatch, tmp_path: Path) -> None:
    _state(monkeypatch, tmp_path)
    ranking.record_recommendations(["repository_read_file"], "Read one file")
    assert ranking.historical_bonus("repository_read_file") == 0
    for _ in range(30):
        ranking.record_event("repository_read_file", outcome=ranking.Outcome(True, True, "COMPLETED", ""), duration_ms=1)
    assert 1 <= ranking.historical_bonus("repository_read_file") <= 80
