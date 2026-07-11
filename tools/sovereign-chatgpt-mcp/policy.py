from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

WORKSPACE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{5,63}$")
BRANCH_RE = re.compile(r"^sovereign/chatgpt/[a-z0-9][a-z0-9._/-]{5,120}$")
CONTAINER_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
CONTAINER_ALIASES = {
    "sovereign-mcp": "sovereign-chatgpt-mcp",
    "mcp": "sovereign-chatgpt-mcp",
}

BLOCKED_PARTS = {
    ".git",
    ".env",
    ".ssh",
    "node_modules",
    "runtime-evidence",
    "secrets",
    "credentials",
}
BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".jks", ".keystore"}
MAX_FILE_BYTES = 1_000_000
MAX_PATCH_BLOCKS = 20
MAX_BLOCK_BYTES = 65_536


def validate_workspace_id(value: str) -> str:
    value = str(value or "").strip().lower()
    if not WORKSPACE_ID_RE.fullmatch(value):
        raise ValueError("Ungültige workspace_id")
    return value


def validate_branch(value: str) -> str:
    value = str(value or "").strip()
    if not BRANCH_RE.fullmatch(value):
        raise ValueError("Branch muss unter sovereign/chatgpt/ liegen")
    if value.endswith("/main") or value in {"main", "master"}:
        raise ValueError("Direkte Hauptbranch-Nutzung ist gesperrt")
    return value


def validate_container(value: str, allowed: Iterable[str]) -> str:
    requested = str(value or "").strip()
    if not CONTAINER_RE.fullmatch(requested):
        raise ValueError("Container ist nicht freigegeben")
    canonical = CONTAINER_ALIASES.get(requested, requested)
    allowlist = {item.strip() for item in allowed if item.strip()}
    if canonical not in allowlist:
        raise ValueError("Container ist nicht freigegeben")
    return canonical


def safe_repo_path(repo_root: Path, relative_path: str, *, must_exist: bool | None = None) -> Path:
    relative = Path(str(relative_path or "").strip())
    if relative.is_absolute() or not relative.parts:
        raise ValueError("Pfad muss relativ zum Repository sein")
    if any(part in BLOCKED_PARTS or part.startswith(".env") for part in relative.parts):
        raise ValueError("Geschützter Pfad")
    if relative.suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError("Secret-/Schlüsseldateien sind gesperrt")

    root = repo_root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Pfad verlässt den Workspace")
    if must_exist is True and not candidate.is_file():
        raise FileNotFoundError(relative_path)
    if must_exist is False and candidate.exists():
        raise FileExistsError(relative_path)
    return candidate


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_patch_blocks(blocks: list[dict[str, str]]) -> None:
    if not 1 <= len(blocks) <= MAX_PATCH_BLOCKS:
        raise ValueError(f"Erlaubt sind 1 bis {MAX_PATCH_BLOCKS} Patch-Blöcke")
    for index, block in enumerate(blocks, start=1):
        search = block.get("search")
        replace = block.get("replace")
        if not isinstance(search, str) or not search:
            raise ValueError(f"Patch-Block {index}: search fehlt")
        if not isinstance(replace, str):
            raise ValueError(f"Patch-Block {index}: replace fehlt")
        if len(search.encode("utf-8")) > MAX_BLOCK_BYTES or len(replace.encode("utf-8")) > MAX_BLOCK_BYTES:
            raise ValueError(f"Patch-Block {index} ist zu groß")
