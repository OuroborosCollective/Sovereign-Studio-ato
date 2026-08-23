"""Controller-side issuer for one opaque desktop-worker activation.

This module writes only private, short-lived scope material for an already
resolved LiveWorkspaceContextV1.  It neither starts Docker nor exposes paths or
scope values to the user-facing route.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

from .fleet_supervisor import FleetContractError, stable_hash
from .live_workspace_context import LiveWorkspaceContextV1

_ACTIVATION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_IMAGE_RE = re.compile(r"^[A-Za-z0-9./_-]+@sha256:[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def _text(value: object, field: str, maximum: int = 360) -> str:
    result = str(value or "").strip()
    if not result or len(result) > maximum:
        raise FleetContractError(f"{field} is invalid")
    return result


def _hash(value: object, field: str) -> str:
    result = _text(value, field, 64).lower()
    if not _HASH_RE.fullmatch(result):
        raise FleetContractError(f"{field} must be an exact SHA-256 value")
    return result


def _bounded_int(value: object, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FleetContractError(f"{field} is outside its bounded range")
    return value


def _read_private_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FleetContractError("desktop activation key is unavailable")
    metadata = path.stat()
    if metadata.st_mode & 0o077:
        raise FleetContractError("desktop activation key mode is unsafe")
    value = path.read_bytes().strip()
    if len(value) < 32 or len(value) > 512:
        raise FleetContractError("desktop activation key is invalid")
    return value


@dataclass(frozen=True)
class DesktopActivationHandleV1:
    activation_id: str
    session_binding_hash: str
    attempt_id: str
    workspace_id: str
    worktree_identity_hash: str
    image_reference: str
    runtime_identity_hash: str
    handle_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "activationId": self.activation_id,
            "sessionBindingHash": self.session_binding_hash,
            "attemptId": self.attempt_id,
            "workspaceId": self.workspace_id,
            "worktreeIdentityHash": self.worktree_identity_hash,
            "imageReference": self.image_reference,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "handleHash": self.handle_hash,
            "authoritative": False,
            "verificationAuthority": False,
        }


@dataclass(frozen=True)
class DesktopActivationIssuerV1:
    activation_root: Path
    workspace_root: Path
    activation_key_path: Path
    image_reference: str
    source_revision: str
    cpu_millis: int = 1000
    memory_bytes: int = 1_073_741_824
    pids_limit: int = 128
    wall_time_seconds: int = 3600
    idle_timeout_seconds: int = 900

    @classmethod
    def from_env(cls) -> "DesktopActivationIssuerV1":
        image_reference = _text(os.getenv("SOVEREIGN_DESKTOP_WORKER_IMAGE"), "desktop worker image reference")
        source_revision = _text(os.getenv("SOVEREIGN_SOURCE_REVISION"), "source revision", 40).lower()
        return cls(
            activation_root=Path(os.getenv("SOVEREIGN_DESKTOP_ACTIVATION_ROOT", "/var/lib/sovereign-desktop-activations")),
            workspace_root=Path(os.getenv("SOVEREIGN_AGENT_WORKSPACE_ROOT", "/var/lib/sovereign-agent/workspaces")),
            activation_key_path=Path(os.getenv("SOVEREIGN_DESKTOP_ACTIVATION_KEY_FILE", "/opt/sovereign-owner-managed/desktop_activation_key.txt")),
            image_reference=image_reference,
            source_revision=source_revision,
            cpu_millis=int(os.getenv("SOVEREIGN_DESKTOP_CPU_MILLIS", "1000")),
            memory_bytes=int(os.getenv("SOVEREIGN_DESKTOP_MEMORY_BYTES", "1073741824")),
            pids_limit=int(os.getenv("SOVEREIGN_DESKTOP_PIDS_LIMIT", "128")),
            wall_time_seconds=int(os.getenv("SOVEREIGN_DESKTOP_WALL_TIME_SECONDS", "3600")),
            idle_timeout_seconds=int(os.getenv("SOVEREIGN_DESKTOP_IDLE_TIMEOUT_SECONDS", "900")),
        )

    def _validate_configuration(self) -> None:
        if not _IMAGE_RE.fullmatch(self.image_reference) or ":latest" in self.image_reference.lower():
            raise FleetContractError("desktop worker image must be immutable and digest-bound")
        if not _REVISION_RE.fullmatch(self.source_revision):
            raise FleetContractError("desktop worker source revision must be exact")
        _bounded_int(self.cpu_millis, "desktop cpu millis", 100, 4000)
        _bounded_int(self.memory_bytes, "desktop memory bytes", 268_435_456, 8_589_934_592)
        _bounded_int(self.pids_limit, "desktop pids limit", 16, 256)
        _bounded_int(self.wall_time_seconds, "desktop wall time", 60, 86_400)
        _bounded_int(self.idle_timeout_seconds, "desktop idle timeout", 60, self.wall_time_seconds)
        if self.activation_root.is_symlink() or not self.activation_root.is_dir():
            raise FleetContractError("desktop activation root is unavailable")
        if self.workspace_root.is_symlink() or not self.workspace_root.is_dir():
            raise FleetContractError("desktop workspace root is unavailable")

    def _activation_id(self, context: LiveWorkspaceContextV1) -> str:
        key = _read_private_key(self.activation_key_path)
        message = "|".join(
            (
                "sovereign.desktop.activation.v1",
                context.session.session_binding_hash,
                context.attempt_workspace.attempt_id,
                context.attempt_workspace.binding_hash,
                self.image_reference,
                self.source_revision,
            )
        ).encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def _paths(self, activation_id: str) -> tuple[Path, Path, Path]:
        if not _ACTIVATION_ID_RE.fullmatch(activation_id):
            raise FleetContractError("desktop activation id is invalid")
        return (
            self.activation_root / f"{activation_id}.json",
            self.activation_root / f"{activation_id}.view.scope",
            self.activation_root / f"{activation_id}.input.scope",
        )

    @staticmethod
    def _create_private(path: Path, payload: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _existing_handle(self, *, document: Path, context: LiveWorkspaceContextV1) -> DesktopActivationHandleV1 | None:
        if not document.exists():
            return None
        if document.is_symlink() or document.stat().st_mode & 0o077:
            raise FleetContractError("desktop activation document is unsafe")
        raw = json.loads(document.read_text("utf-8"))
        if not isinstance(raw, dict):
            raise FleetContractError("desktop activation document is invalid")
        session = context.session
        workspace = context.attempt_workspace
        required = {
            "sessionBindingHash": session.session_binding_hash,
            "attemptId": workspace.attempt_id,
            "workspaceId": workspace.workspace_id,
            "worktreeIdentityHash": workspace.worktree_readback_sha256,
            "imageReference": self.image_reference,
            "sourceRevision": self.source_revision,
        }
        if any(raw.get(key) != value for key, value in required.items()):
            raise FleetContractError("existing desktop activation binds a different live workspace")
        return self._handle(raw)

    @staticmethod
    def _handle(raw: dict[str, Any]) -> DesktopActivationHandleV1:
        payload = {
            "activationId": _hash(raw.get("activationId"), "activation id"),
            "sessionBindingHash": _hash(raw.get("sessionBindingHash"), "session binding hash"),
            "attemptId": _text(raw.get("attemptId"), "attempt id", 40),
            "workspaceId": _text(raw.get("workspaceId"), "workspace id", 160),
            "worktreeIdentityHash": _hash(raw.get("worktreeIdentityHash"), "worktree identity hash"),
            "imageReference": _text(raw.get("imageReference"), "image reference"),
            "runtimeIdentityHash": _hash(raw.get("runtimeIdentityHash"), "runtime identity hash"),
        }
        return DesktopActivationHandleV1(
            activation_id=payload["activationId"],
            session_binding_hash=payload["sessionBindingHash"],
            attempt_id=payload["attemptId"],
            workspace_id=payload["workspaceId"],
            worktree_identity_hash=payload["worktreeIdentityHash"],
            image_reference=payload["imageReference"],
            runtime_identity_hash=payload["runtimeIdentityHash"],
            handle_hash=stable_hash(payload),
        )

    def issue(self, *, context: LiveWorkspaceContextV1) -> DesktopActivationHandleV1:
        self._validate_configuration()
        if context.reconciliation.projection_state != "LIVE":
            raise FleetContractError("desktop activation requires a live reconciled workspace session")
        session = context.session
        workspace = context.attempt_workspace
        try:
            relative_workspace = workspace.worktree_path.resolve().relative_to(self.workspace_root.resolve())
        except (OSError, ValueError) as exc:
            raise FleetContractError("active attempt worktree is outside desktop workspace root") from exc
        if not relative_workspace.parts or ".." in relative_workspace.parts:
            raise FleetContractError("active attempt worktree relative path is unsafe")
        activation_id = self._activation_id(context)
        document, view_scope, input_scope = self._paths(activation_id)
        existing = self._existing_handle(document=document, context=context)
        if existing is not None:
            return existing
        runtime_identity_hash = stable_hash(
            {
                "sessionBindingHash": session.session_binding_hash,
                "attemptId": workspace.attempt_id,
                "worktreeIdentityHash": workspace.worktree_readback_sha256,
                "imageReference": self.image_reference,
                "sourceRevision": self.source_revision,
            }
        )
        view_value = secrets.token_urlsafe(48)
        input_value = secrets.token_urlsafe(48)
        if view_value == input_value:
            raise FleetContractError("desktop scope generator produced a collision")
        payload = {
            "activationId": activation_id,
            "sessionBindingHash": session.session_binding_hash,
            "attemptId": workspace.attempt_id,
            "workspaceId": workspace.workspace_id,
            "worktreeIdentityHash": workspace.worktree_readback_sha256,
            "workspaceRelativePath": relative_workspace.as_posix(),
            "workspacePathHash": workspace.receipt_binding()["worktreePathSha256"],
            "imageReference": self.image_reference,
            "runtimeIdentityHash": runtime_identity_hash,
            "sourceRevision": self.source_revision,
            "expectedBaseRevision": workspace.base_revision,
            "observedHeadRevision": workspace.head_revision,
            "viewScopeFile": view_scope.name,
            "viewScopeHash": hashlib.sha256(view_value.encode("utf-8")).hexdigest(),
            "inputScopeFile": input_scope.name,
            "inputScopeHash": hashlib.sha256(input_value.encode("utf-8")).hexdigest(),
            "cpuMillis": self.cpu_millis,
            "memoryBytes": self.memory_bytes,
            "pidsLimit": self.pids_limit,
            "wallTimeSeconds": self.wall_time_seconds,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
        }
        created: list[Path] = []
        try:
            self._create_private(view_scope, view_value.encode("utf-8"))
            created.append(view_scope)
            self._create_private(input_scope, input_value.encode("utf-8"))
            created.append(input_scope)
            self._create_private(document, json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            return self._handle(payload)
        except FileExistsError:
            existing = self._existing_handle(document=document, context=context)
            if existing is not None:
                return existing
            raise FleetContractError("desktop activation creation raced without a complete document")
        except OSError as exc:
            for path in created:
                path.unlink(missing_ok=True)
            raise FleetContractError("desktop activation material could not be written") from exc


__all__ = ["DesktopActivationHandleV1", "DesktopActivationIssuerV1"]
