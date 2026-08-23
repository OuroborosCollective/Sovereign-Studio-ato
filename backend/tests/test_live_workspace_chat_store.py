from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_runtime.fleet_supervisor import FleetContractError  # noqa: E402
from agent_runtime.live_workspace_chat_store import (  # noqa: E402
    LiveWorkspaceChatSessionV1,
    LiveWorkspaceChatStoreError,
    build_persistable_chat_bubble,
    normalize_chat_branch,
    normalize_chat_repository_identity,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
REVISION = "c" * 40
SESSION = LiveWorkspaceChatSessionV1(
    session_id="livechat-" + ("d" * 24),
    user_id="00000000-0000-4000-8000-000000000001",
    repository_identity="https://github.com/OuroborosCollective/Sovereign-Studio-ato",
    repository_branch="main",
)


def test_mission_input_is_typed_non_authoritative_and_cannot_carry_permission() -> None:
    bubble = build_persistable_chat_bubble(
        session=SESSION,
        client_message_id="mission-1",
        bubble_kind="MISSION_INPUT",
        text="Repariere den Login und erstelle einen Draft PR.",
        source_kind="USER_INPUT",
    )
    assert bubble["bubbleKind"] == "MISSION_INPUT"
    assert bubble["sourceKind"] == "USER_INPUT"
    assert bubble["workflowState"] == "RECORDED"
    assert bubble["canonicalReferenceHashes"] == []
    assert bubble["authoritative"] is False
    assert len(bubble["bubbleHash"]) == 64

    with pytest.raises(LiveWorkspaceChatStoreError, match="cannot carry"):
        build_persistable_chat_bubble(
            session=SESSION,
            client_message_id="mission-2",
            bubble_kind="MISSION_INPUT",
            text="Deploy production.",
            source_kind="USER_INPUT",
            effect_kind="DEPLOYMENT",
        )


def test_question_blocker_consent_and_result_require_canonical_bindings() -> None:
    with pytest.raises(LiveWorkspaceChatStoreError, match="exact session"):
        build_persistable_chat_bubble(
            session=SESSION,
            client_message_id="question-1",
            bubble_kind="REQUIRED_QUESTION",
            text="Welche Zielumgebung ist gemeint?",
            source_kind="CANONICAL_WORKFLOW",
            workflow_state="WAITING_FOR_USER",
            canonical_reference_hashes=[HASH_A],
        )

    consent = build_persistable_chat_bubble(
        session=SESSION,
        client_message_id="consent-1",
        bubble_kind="OWNER_CONSENT_REQUEST",
        text="Production deployment für die gebundene Revision.",
        source_kind="CONSENT_CONTRACT",
        workflow_state="WAITING_FOR_USER",
        canonical_reference_hashes=[HASH_A],
        session_binding_hash=HASH_B,
        run_id="run-1",
        attempt_id="attempt-1",
        bound_revision=REVISION,
        effect_kind="DEPLOYMENT",
        target_hash=HASH_A,
        consent_binding_hash=HASH_B,
    )
    assert consent["effectKind"] == "DEPLOYMENT"
    assert consent["boundRevision"] == REVISION

    final = build_persistable_chat_bubble(
        session=SESSION,
        client_message_id="final-1",
        bubble_kind="FINAL_RESULT",
        text="Draft PR gegen den gebundenen Head zurückgelesen.",
        source_kind="EFFECT_READBACK",
        workflow_state="VERIFIED",
        canonical_reference_hashes=[HASH_A],
        session_binding_hash=HASH_B,
        run_id="run-1",
        attempt_id="attempt-1",
        bound_revision=REVISION,
    )
    assert final["workflowState"] == "VERIFIED"
    with pytest.raises(LiveWorkspaceChatStoreError, match="verified readback"):
        build_persistable_chat_bubble(
            session=SESSION,
            client_message_id="final-2",
            bubble_kind="FINAL_RESULT",
            text="Fertig.",
            source_kind="EFFECT_READBACK",
            workflow_state="UNVERIFIED",
            canonical_reference_hashes=[HASH_A],
            session_binding_hash=HASH_B,
            run_id="run-1",
            attempt_id="attempt-1",
            bound_revision=REVISION,
        )


def test_internal_reasoning_and_secret_shaped_text_never_reach_persistence() -> None:
    with pytest.raises(FleetContractError, match="internal reasoning"):
        build_persistable_chat_bubble(
            session=SESSION,
            client_message_id="mission-internal",
            bubble_kind="MISSION_INPUT",
            text="Here's a thinking process about the request.",
            source_kind="USER_INPUT",
        )
    secret = "github_" + "pat_" + ("x" * 40)
    with pytest.raises(FleetContractError, match="secret-shaped"):
        build_persistable_chat_bubble(
            session=SESSION,
            client_message_id="mission-secret",
            bubble_kind="MISSION_INPUT",
            text=secret,
            source_kind="USER_INPUT",
        )


def test_scope_and_replay_identity_are_session_bound() -> None:
    other = LiveWorkspaceChatSessionV1(
        session_id="livechat-" + ("e" * 24),
        user_id=SESSION.user_id,
        repository_identity=SESSION.repository_identity,
        repository_branch="feature",
    )
    args = {
        "client_message_id": "mission-replay",
        "bubble_kind": "MISSION_INPUT",
        "text": "Prüfe die Regression.",
        "source_kind": "USER_INPUT",
    }
    assert build_persistable_chat_bubble(session=SESSION, **args)["bubbleHash"] != build_persistable_chat_bubble(session=other, **args)["bubbleHash"]


def test_repository_and_branch_scope_fail_closed() -> None:
    assert normalize_chat_repository_identity(
        "https://github.com/OuroborosCollective/Sovereign-Studio-ato.git"
    ) == "https://github.com/OuroborosCollective/Sovereign-Studio-ato"
    assert normalize_chat_repository_identity("UNBOUND") == "UNBOUND"
    assert normalize_chat_branch("sovereign/issue-1620") == "sovereign/issue-1620"
    with pytest.raises(LiveWorkspaceChatStoreError):
        normalize_chat_repository_identity("https://example.invalid/repo")
    with pytest.raises(LiveWorkspaceChatStoreError):
        normalize_chat_branch("../main")


def test_store_and_migration_are_byte_identical_in_deployment_mirrors() -> None:
    root = Path(__file__).resolve().parents[2]
    canonical_store = root / "backend" / "agent_runtime" / "live_workspace_chat_store.py"
    mirror_store = root / "scripts" / "sovereign-backend" / "agent_runtime" / "live_workspace_chat_store.py"
    canonical_migration = root / "backend" / "migrations" / "059_live_workspace_chat_bubbles.sql"
    mirror_migration = root / "scripts" / "sovereign-backend" / "migrations" / "059_live_workspace_chat_bubbles.sql"
    assert canonical_store.read_bytes() == mirror_store.read_bytes()
    assert canonical_migration.read_bytes() == mirror_migration.read_bytes()

    sql = canonical_migration.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS live_workspace_chat_sessions" in sql
    assert "CREATE TABLE IF NOT EXISTS live_workspace_chat_bubbles" in sql
    assert "reject_live_workspace_chat_bubbles_update" in sql
    assert "reject_live_workspace_chat_bubbles_delete" in sql
    assert "source_kind = 'CONSENT_CONTRACT'" in sql
    assert "workflow_state = 'VERIFIED'" in sql
