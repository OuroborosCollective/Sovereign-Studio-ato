"""Real PostgreSQL persistence for typed Live Workspace chat bubbles.

The browser never supplies user authority, workflow verdicts or approval state.
User-facing routes may append only MISSION_INPUT. Other bubble kinds are reserved
for server-side canonical workflow, consent and effect-readback producers.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from .fleet_supervisor import FleetContractError, stable_hash
from .live_workspace import CHAT_BUBBLE_SCHEMA_VERSION, ChatBubbleV1


CHAT_SESSION_SCHEMA_VERSION = "sovereign.live-workspace-chat-session.v1"
CHAT_PERSISTENCE_SCHEMA_VERSION = "sovereign.live-workspace-chat-persistence.v1"

_SESSION_ID_RE = re.compile(r"^livechat-[0-9a-f]{24}$")
_CLIENT_MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_EFFECT_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")

_SOURCE_BY_KIND = {
    "MISSION_INPUT": "USER_INPUT",
    "REQUIRED_QUESTION": "CANONICAL_WORKFLOW",
    "OWNER_CONSENT_REQUEST": "CONSENT_CONTRACT",
    "MATERIAL_BLOCKER": "CANONICAL_WORKFLOW",
    "FINAL_RESULT": "EFFECT_READBACK",
}
_ALLOWED_WORKFLOW_STATES = {
    "RECORDED",
    "WAITING_FOR_USER",
    "BLOCKED",
    "FAILED",
    "UNVERIFIED",
    "CONTRADICTED",
    "VERIFIED",
}


class LiveWorkspaceChatStoreError(RuntimeError):
    """Raised when typed chat persistence would cross a truth boundary."""


@dataclass(frozen=True)
class LiveWorkspaceChatSessionV1:
    session_id: str
    user_id: str
    repository_identity: str
    repository_branch: str
    recorded_at: object | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": CHAT_SESSION_SCHEMA_VERSION,
            "sessionId": self.session_id,
            "repositoryIdentity": self.repository_identity,
            "repositoryBranch": self.repository_branch,
            "recordedAt": _timestamp(self.recorded_at),
            "persistence": "postgresql",
            "authoritative": False,
        }


def _timestamp(value: object | None) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value: object, field: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or "\x00" in normalized:
        raise LiveWorkspaceChatStoreError(f"{field} is invalid")
    return normalized


def _optional_hash(value: object | None, field: str) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if not _HASH_RE.fullmatch(normalized):
        raise LiveWorkspaceChatStoreError(f"{field} must be an exact SHA-256 value")
    return normalized


def _optional_revision(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    if not _REVISION_RE.fullmatch(normalized):
        raise LiveWorkspaceChatStoreError("bound_revision must be an exact Git revision")
    return normalized


def normalize_chat_repository_identity(value: object) -> str:
    normalized = _text(value, "repository_identity", 300)
    if normalized == "UNBOUND":
        return normalized
    parsed = urlparse(normalized)
    if (
        parsed.scheme != "https"
        or parsed.netloc.casefold() != "github.com"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise LiveWorkspaceChatStoreError("repository_identity must be an exact GitHub repository URL")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        raise LiveWorkspaceChatStoreError("repository_identity must name one repository")
    owner, repository = parts
    repository = repository.removesuffix(".git")
    if not owner or not repository or not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise LiveWorkspaceChatStoreError("repository_identity is invalid")
    return f"https://github.com/{owner}/{repository}"


def normalize_chat_branch(value: object) -> str:
    normalized = _text(value, "repository_branch", 200)
    if not _BRANCH_RE.fullmatch(normalized) or ".." in normalized or normalized.endswith(("/", ".")):
        raise LiveWorkspaceChatStoreError("repository_branch is invalid")
    return normalized


def _session_id(user_id: str, repository_identity: str, repository_branch: str) -> str:
    digest = sha256(
        f"{CHAT_SESSION_SCHEMA_VERSION}\n{user_id}\n{repository_identity}\n{repository_branch}".encode("utf-8")
    ).hexdigest()
    return f"livechat-{digest[:24]}"


def _session_from_row(row: Mapping[str, Any]) -> LiveWorkspaceChatSessionV1:
    session = LiveWorkspaceChatSessionV1(
        session_id=str(row.get("session_id") or ""),
        user_id=str(row.get("user_id") or ""),
        repository_identity=str(row.get("repository_identity") or ""),
        repository_branch=str(row.get("repository_branch") or ""),
        recorded_at=row.get("recorded_at"),
    )
    if not _SESSION_ID_RE.fullmatch(session.session_id):
        raise LiveWorkspaceChatStoreError("persisted chat session identity is invalid")
    return session


def resolve_live_workspace_chat_session(
    conn: Any,
    *,
    user_id: str,
    repository_identity: object,
    repository_branch: object,
) -> LiveWorkspaceChatSessionV1:
    """Resolve one immutable user/repository/branch session in real PostgreSQL."""

    owner = _text(user_id, "user_id", 80)
    repository = normalize_chat_repository_identity(repository_identity)
    branch = normalize_chat_branch(repository_branch)
    session_id = _session_id(owner, repository, branch)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO live_workspace_chat_sessions (
                    session_id, user_id, repository_identity, repository_branch
                ) VALUES (%s, %s::uuid, %s, %s)
                ON CONFLICT (user_id, repository_identity, repository_branch) DO NOTHING
                """,
                (session_id, owner, repository, branch),
            )
            cur.execute(
                """
                SELECT session_id, user_id, repository_identity, repository_branch, recorded_at
                FROM live_workspace_chat_sessions
                WHERE session_id = %s AND user_id = %s::uuid
                """,
                (session_id, owner),
            )
            row = cur.fetchone()
        if not isinstance(row, Mapping):
            raise LiveWorkspaceChatStoreError("chat session was not persisted")
        conn.commit()
        return _session_from_row(row)
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise


def read_live_workspace_chat_session(conn: Any, *, user_id: str, session_id: str) -> LiveWorkspaceChatSessionV1 | None:
    owner = _text(user_id, "user_id", 80)
    normalized_session_id = _text(session_id, "session_id", 40)
    if not _SESSION_ID_RE.fullmatch(normalized_session_id):
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT session_id, user_id, repository_identity, repository_branch, recorded_at
            FROM live_workspace_chat_sessions
            WHERE session_id = %s AND user_id = %s::uuid
            """,
            (normalized_session_id, owner),
        )
        row = cur.fetchone()
    return _session_from_row(row) if isinstance(row, Mapping) else None


def build_persistable_chat_bubble(
    *,
    session: LiveWorkspaceChatSessionV1,
    client_message_id: object,
    bubble_kind: object,
    text: object,
    source_kind: object,
    canonical_reference_hashes: Sequence[str] = (),
    session_binding_hash: object | None = None,
    run_id: object | None = None,
    attempt_id: object | None = None,
    workflow_state: object = "RECORDED",
    bound_revision: object | None = None,
    effect_kind: object | None = None,
    target_hash: object | None = None,
    consent_binding_hash: object | None = None,
) -> dict[str, Any]:
    """Build a structurally gated bubble; text filters are defense in depth only."""

    message_id = _text(client_message_id, "client_message_id", 120)
    if not _CLIENT_MESSAGE_ID_RE.fullmatch(message_id):
        raise LiveWorkspaceChatStoreError("client_message_id is invalid")

    kind = _text(bubble_kind, "bubble_kind", 80).upper()
    expected_source = _SOURCE_BY_KIND.get(kind)
    source = _text(source_kind, "source_kind", 80).upper()
    if expected_source is None or source != expected_source:
        raise LiveWorkspaceChatStoreError("bubble source does not match its typed class")

    state = _text(workflow_state, "workflow_state", 40).upper()
    if state not in _ALLOWED_WORKFLOW_STATES:
        raise LiveWorkspaceChatStoreError("workflow_state is invalid")

    contract = ChatBubbleV1.create(
        bubble_kind=kind,
        text=str(text or ""),
        canonical_reference_hashes=canonical_reference_hashes,
    )
    binding_hash = _optional_hash(session_binding_hash, "session_binding_hash")
    target = _optional_hash(target_hash, "target_hash")
    consent = _optional_hash(consent_binding_hash, "consent_binding_hash")
    revision = _optional_revision(bound_revision)
    run = _text(run_id, "run_id", 160) if run_id not in (None, "") else None
    attempt = _text(attempt_id, "attempt_id", 160) if attempt_id not in (None, "") else None
    effect = _text(effect_kind, "effect_kind", 80).upper() if effect_kind not in (None, "") else None
    if effect is not None and not _EFFECT_RE.fullmatch(effect):
        raise LiveWorkspaceChatStoreError("effect_kind is invalid")

    if kind == "MISSION_INPUT":
        if source != "USER_INPUT" or state != "RECORDED" or any(
            value is not None for value in (binding_hash, run, attempt, revision, effect, target, consent)
        ):
            raise LiveWorkspaceChatStoreError("mission input cannot carry workflow or permission authority")
    else:
        if not binding_hash or not run or not attempt or not contract.canonical_reference_hashes:
            raise LiveWorkspaceChatStoreError("interactive bubble requires exact session, run, attempt and canonical references")
        if kind == "REQUIRED_QUESTION" and state != "WAITING_FOR_USER":
            raise LiveWorkspaceChatStoreError("required question must bind WAITING_FOR_USER")
        if kind == "MATERIAL_BLOCKER" and state not in {"BLOCKED", "FAILED", "UNVERIFIED", "CONTRADICTED"}:
            raise LiveWorkspaceChatStoreError("material blocker must bind a non-success workflow state")
        if kind == "OWNER_CONSENT_REQUEST":
            if state != "WAITING_FOR_USER" or not revision or not effect or not target or not consent:
                raise LiveWorkspaceChatStoreError("consent request lacks effect, target, revision or consent binding")
        if kind == "FINAL_RESULT":
            if state != "VERIFIED" or not revision or effect is not None or consent is not None:
                raise LiveWorkspaceChatStoreError("final result requires verified readback without permission authority")

    payload: dict[str, Any] = {
        "schemaVersion": CHAT_BUBBLE_SCHEMA_VERSION,
        "persistenceSchemaVersion": CHAT_PERSISTENCE_SCHEMA_VERSION,
        "sessionId": session.session_id,
        "clientMessageId": message_id,
        "bubbleKind": contract.bubble_kind,
        "sourceKind": source,
        "text": contract.text,
        "canonicalReferenceHashes": list(contract.canonical_reference_hashes),
        "sessionBindingHash": binding_hash,
        "runId": run,
        "attemptId": attempt,
        "workflowState": state,
        "boundRevision": revision,
        "effectKind": effect,
        "targetHash": target,
        "consentBindingHash": consent,
        "authoritative": False,
    }
    payload["bubbleHash"] = stable_hash(payload)
    return payload


def append_live_workspace_chat_bubble(
    conn: Any,
    *,
    session: LiveWorkspaceChatSessionV1,
    user_id: str,
    **candidate: Any,
) -> dict[str, Any]:
    owner = _text(user_id, "user_id", 80)
    if owner != session.user_id:
        raise LiveWorkspaceChatStoreError("chat session owner mismatch")
    payload = build_persistable_chat_bubble(session=session, **candidate)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO live_workspace_chat_bubbles (
                    bubble_hash, session_id, user_id, client_message_id, schema_version,
                    bubble_kind, source_kind, bubble_text, canonical_reference_hashes,
                    session_binding_hash, run_id, attempt_id, workflow_state, bound_revision,
                    effect_kind, target_hash, consent_binding_hash, canonical_body
                ) VALUES (
                    %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
                )
                ON CONFLICT (session_id, client_message_id) DO NOTHING
                """,
                (
                    payload["bubbleHash"], session.session_id, owner, payload["clientMessageId"],
                    CHAT_BUBBLE_SCHEMA_VERSION, payload["bubbleKind"], payload["sourceKind"],
                    payload["text"], json.dumps(payload["canonicalReferenceHashes"]),
                    payload["sessionBindingHash"], payload["runId"], payload["attemptId"],
                    payload["workflowState"], payload["boundRevision"], payload["effectKind"],
                    payload["targetHash"], payload["consentBindingHash"], _json(payload),
                ),
            )
            cur.execute(
                """
                SELECT bubble_hash, canonical_body, recorded_at
                FROM live_workspace_chat_bubbles
                WHERE session_id = %s AND user_id = %s::uuid AND client_message_id = %s
                """,
                (session.session_id, owner, payload["clientMessageId"]),
            )
            row = cur.fetchone()
        if not isinstance(row, Mapping):
            raise LiveWorkspaceChatStoreError("chat bubble was not persisted")
        stored = row.get("canonical_body")
        if isinstance(stored, str):
            stored = json.loads(stored)
        if not isinstance(stored, Mapping) or str(row.get("bubble_hash") or "") != payload["bubbleHash"]:
            raise LiveWorkspaceChatStoreError("client message replay does not match the persisted bubble")
        result = dict(stored)
        result["recordedAt"] = _timestamp(row.get("recorded_at"))
        conn.commit()
        return result
    except Exception:
        rollback = getattr(conn, "rollback", None)
        if callable(rollback):
            rollback()
        raise


def list_live_workspace_chat_bubbles(
    conn: Any,
    *,
    session: LiveWorkspaceChatSessionV1,
    user_id: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    owner = _text(user_id, "user_id", 80)
    if owner != session.user_id:
        raise LiveWorkspaceChatStoreError("chat session owner mismatch")
    bounded_limit = max(1, min(int(limit), 500))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT canonical_body, recorded_at
            FROM live_workspace_chat_bubbles
            WHERE session_id = %s AND user_id = %s::uuid
            -- Fetch the authoritative newest bounded tail; reversing below preserves
            -- chronological projection without deriving freshness from a truncated prefix.
            ORDER BY ordinal DESC
            LIMIT %s
            """,
            (session.session_id, owner, bounded_limit),
        )
        rows = cur.fetchall()
    result: list[dict[str, Any]] = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            raise LiveWorkspaceChatStoreError("persisted chat bubble row is invalid")
        body = row.get("canonical_body")
        if isinstance(body, str):
            body = json.loads(body)
        if not isinstance(body, Mapping):
            raise LiveWorkspaceChatStoreError("persisted chat bubble payload is invalid")
        item = dict(body)
        item["recordedAt"] = _timestamp(row.get("recorded_at"))
        result.append(item)
    result.reverse()
    return result


__all__ = [
    "CHAT_PERSISTENCE_SCHEMA_VERSION",
    "CHAT_SESSION_SCHEMA_VERSION",
    "LiveWorkspaceChatSessionV1",
    "LiveWorkspaceChatStoreError",
    "append_live_workspace_chat_bubble",
    "build_persistable_chat_bubble",
    "list_live_workspace_chat_bubbles",
    "normalize_chat_branch",
    "normalize_chat_repository_identity",
    "read_live_workspace_chat_session",
    "resolve_live_workspace_chat_session",
]
