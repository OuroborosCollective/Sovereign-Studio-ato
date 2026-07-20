from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

flask_stub = types.ModuleType("flask")
flask_stub.jsonify = lambda payload: payload
flask_stub.request = types.SimpleNamespace(headers={})
sys.modules.setdefault("flask", flask_stub)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import proven_learning_runtime as runtime


def _record(operation_type: str = "fix") -> dict:
    revision = "a" * 40
    source = "database_readback" if operation_type == "database" else (
        "merge_result" if operation_type == "merge" else "github_actions"
    )
    return {
        "title": "Persist only proven learning",
        "problem": "Unverified outcomes could pollute reusable memory.",
        "context": "Sovereign runtime",
        "solution": "Bind one structured pattern to exact evidence receipts and Owner approval.",
        "applicability": "Successful repository and database work",
        "validation": ["Read the candidate and vector through the canonical store"],
        "tags": ["Runtime Truth", "Learning"],
        "source_refs": [{
            "repository": "OuroborosCollective/Sovereign-Studio-ato",
            "revision": revision,
            "path": "scripts/sovereign-backend/proven_learning_runtime.py",
            "lines": "1-400",
            "license": "project-owned",
        }],
        "confidence": 0.99,
        "evidence": {
            "operation_type": operation_type,
            "outcome": "successful",
            "revision": revision,
            "completed_at": "2026-07-19T12:00:00Z",
            "changed_paths": ["scripts/sovereign-backend/proven_learning_runtime.py"],
            "checks": [{
                "name": "real path",
                "status": "passed",
                "source": source,
                "evidence_sha256": "b" * 64,
                "summary": "The exact real-path gate completed successfully.",
            }],
        },
    }


def test_plan_is_deterministic_secret_safe_and_read_only() -> None:
    first = runtime.plan_proven_learning(_record())
    second = runtime.plan_proven_learning(_record())

    assert first == second
    assert first["status"] == "PROVEN_LEARNING_PLAN_READY"
    assert len(first["confirmationSha256"]) == 64
    assert first["record"]["content_hash"] == f"sha256:{first['confirmationSha256']}"
    assert first["record"]["embedding_text"].startswith("Title: Persist only proven learning")
    assert first["databaseAccessed"] is False
    assert first["embeddingGenerated"] is False
    assert first["ownerApprovalRequired"] is False
    assert first["approvalMode"] == "persisted-owner-policy-or-fresh-owner-approval"


def test_database_and_merge_require_operation_specific_readback() -> None:
    database = _record("database")
    database["evidence"]["checks"][0]["source"] = "github_actions"
    with pytest.raises(ValueError, match="database or migration readback"):
        runtime.plan_proven_learning(database)

    merge = _record("merge")
    merge["evidence"]["checks"][0]["source"] = "repository_check"
    with pytest.raises(ValueError, match="merge result"):
        runtime.plan_proven_learning(merge)


def test_failed_or_secret_shaped_outcomes_never_plan() -> None:
    failed = _record()
    failed["evidence"]["outcome"] = "failed"
    with pytest.raises(ValueError, match="only successful"):
        runtime.plan_proven_learning(failed)

    secret = _record()
    secret["solution"] = "Authorization: Bearer definitely-not-allowed"
    with pytest.raises(ValueError, match="secret-like"):
        runtime.plan_proven_learning(secret)



def test_apply_commits_candidate_vector_and_approval_atomically(monkeypatch) -> None:
    class Cursor:
        def __init__(self, connection):
            self.connection = connection
            self.rowcount = 0
            self.statement = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, _params=()):
            self.statement = " ".join(statement.split())
            if self.statement.startswith("UPDATE owner_input_requests"):
                self.rowcount = 1

        def fetchone(self):
            if "SELECT id::text" in self.statement:
                return {
                    "id": "33333333-3333-4333-8333-333333333333",
                    "target_id": "proven_learning_confirmation",
                    "status": "consumed",
                    "owner_admin_id": "owner-1",
                    "result_code": "target_updated",
                    "resolved_at": "2026-07-19T12:00:00Z",
                }
            if "SELECT EXISTS" in self.statement:
                return {"fresh": True}
            raise AssertionError(f"unexpected fetch: {self.statement}")

    class Connection:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        def cursor(self):
            return Cursor(self)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    record = _record()
    plan = runtime.plan_proven_learning(record)
    digest = plan["confirmationSha256"]
    calls: list[tuple[str, bool]] = []

    monkeypatch.setattr(runtime, "_read_approval_hash", lambda: digest)
    monkeypatch.setattr(runtime, "_remove_approval_hash", lambda: calls.append(("cleanup", True)))
    monkeypatch.setattr(
        runtime,
        "persist_pattern_learning_candidate_once",
        lambda _conn, *, user_id, result, commit: (
            calls.append(("candidate", commit)) or ("pattern-1", True)
        ),
    )
    monkeypatch.setattr(
        runtime,
        "persist_pattern_vector",
        lambda _conn, *, candidate_id, user_id, result, commit: (
            calls.append(("vector", commit))
            or {
                "stored": True,
                "embeddingModel": "text-embedding-3-small",
                "provider": "openai",
            }
        ),
    )
    monkeypatch.setattr(
        runtime,
        "_pattern_readback",
        lambda _conn, *, user_id, digest: {
            "candidateId": "pattern-1",
            "vectorStored": True,
            "outboxStatus": "pending",
        },
    )
    connection = Connection()

    result = runtime.apply_proven_learning(
        connection,
        request_id="33333333-3333-4333-8333-333333333333",
        confirmation_sha256=digest,
        record=record,
    )

    assert result["status"] == "PROVEN_LEARNING_PATTERN_STORED"
    assert result["readbackVerified"] is True
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert ("candidate", False) in calls
    assert ("vector", False) in calls
    assert calls[-1] == ("cleanup", True)


def test_standing_owner_policy_persists_without_one_time_confirmation(monkeypatch) -> None:
    record = _record()
    digest = runtime.plan_proven_learning(record)["confirmationSha256"]
    calls = []

    class Cursor:
        def __init__(self):
            self.statement = ""
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, statement, _params=()): self.statement = " ".join(statement.split())
        def fetchall(self):
            assert "owner_learning_policies" in self.statement
            return [{"owner_admin_id": "owner-1"}]

    class Connection:
        def __init__(self): self.commits = 0
        def cursor(self): return Cursor()
        def commit(self): self.commits += 1
        def rollback(self): raise AssertionError("rollback not expected")

    monkeypatch.setattr(runtime, "_read_approval_hash", lambda: pytest.fail("one-time hash must not be read"))
    monkeypatch.setattr(runtime, "_remove_approval_hash", lambda: pytest.fail("one-time hash must not be removed"))
    monkeypatch.setattr(runtime, "persist_pattern_learning_candidate_once", lambda *_args, **_kwargs: ("pattern-2", True))
    monkeypatch.setattr(runtime, "persist_pattern_vector", lambda *_args, **_kwargs: {"stored": True, "embeddingModel": "model", "provider": "proxy"})
    monkeypatch.setattr(runtime, "_pattern_readback", lambda *_args, **_kwargs: {"candidateId": "pattern-2", "vectorStored": True, "outboxStatus": "pending"})

    connection = Connection()
    result = runtime.apply_proven_learning(
        connection,
        confirmation_sha256=digest,
        record=record,
    )

    assert result["standingOwnerPolicyUsed"] is True
    assert result["ownerApprovalConsumed"] is False
    assert result["duplicate"] is False
    assert connection.commits == 1


def test_owner_confirmation_file_requires_exact_mode_owner_and_hash(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SOVEREIGN_OWNER_INPUT_ROOT", str(tmp_path))
    approval = tmp_path / "proven_learning_confirmation.txt"
    approval.write_text("c" * 64, "utf-8")
    approval.chmod(0o600)

    assert runtime._read_approval_hash() == "c" * 64

    approval.chmod(0o644)
    with pytest.raises(runtime.ProvenLearningBlocked, match="unsafe"):
        runtime._read_approval_hash()
