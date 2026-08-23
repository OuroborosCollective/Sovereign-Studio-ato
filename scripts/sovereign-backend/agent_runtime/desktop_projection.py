"""Path-free frame projection from one private desktop worker.

The backend is the authenticated view gateway.  The worker's view scope is
read only from private activation material and is never forwarded to the user.
Frame delivery is an observation channel only; no frame can verify an effect.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .desktop_activation import DesktopActivationHandleV1
from .fleet_supervisor import FleetContractError

_ACTIVATION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTAINER_RE = re.compile(r"^sovereign-desktop-[0-9a-f]{20}$")
_MAX_FRAME_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class DesktopFrameV1:
    content: bytes
    frame_hash: str
    runtime_identity_hash: str

    def observation(self) -> dict[str, Any]:
        return {
            "status": "OBSERVED",
            "frameHash": self.frame_hash,
            "runtimeIdentityHash": self.runtime_identity_hash,
            "authoritative": False,
            "targetEffectVerified": False,
        }


class DesktopFrameProxyV1:
    def __init__(
        self,
        *,
        activation_root: Path,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.activation_root = activation_root
        self.opener = opener

    @classmethod
    def from_env(cls) -> "DesktopFrameProxyV1":
        import os

        return cls(activation_root=Path(os.getenv("SOVEREIGN_DESKTOP_ACTIVATION_ROOT", "/var/lib/sovereign-desktop-activations")))

    def _scope(self, handle: DesktopActivationHandleV1) -> str:
        if self.activation_root.is_symlink() or not self.activation_root.is_dir():
            raise FleetContractError("desktop activation root is unavailable")
        if not _ACTIVATION_ID_RE.fullmatch(handle.activation_id):
            raise FleetContractError("desktop activation id is invalid")
        document = self.activation_root / f"{handle.activation_id}.json"
        if document.is_symlink() or not document.is_file() or document.stat().st_mode & 0o077:
            raise FleetContractError("desktop activation document is unsafe")
        try:
            raw = json.loads(document.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FleetContractError("desktop activation document is unreadable") from exc
        if not isinstance(raw, dict) or raw.get("sessionBindingHash") != handle.session_binding_hash:
            raise FleetContractError("desktop activation document does not match the live session")
        scope_name = str(raw.get("viewScopeFile") or "").strip()
        if not re.fullmatch(r"[0-9a-f]{64}\.view\.scope", scope_name):
            raise FleetContractError("desktop view scope filename is invalid")
        scope_path = self.activation_root / scope_name
        if scope_path.is_symlink() or not scope_path.is_file():
            raise FleetContractError("desktop view scope is unavailable")
        metadata = scope_path.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077 or metadata.st_size > 256:
            raise FleetContractError("desktop view scope is unsafe")
        value = scope_path.read_text("utf-8").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,160}", value):
            raise FleetContractError("desktop view scope is invalid")
        expected_hash = str(raw.get("viewScopeHash") or "").strip().lower()
        if not _HASH_RE.fullmatch(expected_hash) or hashlib.sha256(value.encode("utf-8")).hexdigest() != expected_hash:
            raise FleetContractError("desktop view scope does not match activation")
        return value

    @staticmethod
    def _container_name(handle: DesktopActivationHandleV1) -> str:
        value = f"sovereign-desktop-{handle.session_binding_hash[:20]}"
        if not _CONTAINER_RE.fullmatch(value):
            raise FleetContractError("desktop worker identity is invalid")
        return value

    def frame(self, *, handle: DesktopActivationHandleV1) -> DesktopFrameV1:
        scope = self._scope(handle)
        request = Request(
            f"http://{self._container_name(handle)}:8765/frame",
            headers={"X-Sovereign-Desktop-Scope": scope},
            method="GET",
        )
        try:
            response = self.opener(request, timeout=5)
            with response:
                content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                content = response.read(_MAX_FRAME_BYTES + 1)
        except (OSError, URLError) as exc:
            raise FleetContractError("desktop frame worker is unavailable") from exc
        if content_type != "image/png" or not content.startswith(b"\x89PNG") or len(content) > _MAX_FRAME_BYTES:
            raise FleetContractError("desktop frame response is invalid")
        return DesktopFrameV1(
            content=content,
            frame_hash=hashlib.sha256(content).hexdigest(),
            runtime_identity_hash=handle.runtime_identity_hash,
        )


__all__ = ["DesktopFrameProxyV1", "DesktopFrameV1"]
