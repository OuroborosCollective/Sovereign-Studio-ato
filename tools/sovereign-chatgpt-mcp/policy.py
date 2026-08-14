from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Iterable

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

_SENSITIVE_KEYS = frozenset(
    {
        "apikey",
        "authorization",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "sessiontoken",
        "authtoken",
        "clientsecret",
        "cookie",
        "credential",
        "credentials",
        "password",
        "passwd",
        "privatekey",
        "secret",
        "token",
    }
)
_FALSE_SECRET_ATTESTATION_KEYS = frozenset(
    {"argumentvaluesrecorded", "secretvaluesrecorded", "secretvaluesreturned"}
)
_SECRET_LITERAL_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b", re.I),
    re.compile(r"\bBasic\s+[A-Za-z0-9+/]{8,}={0,2}\b", re.I),
    re.compile(
        r"\b(?:api[_-]?key|password|passwd|secret|token|client[_-]?secret|"
        r"access[_-]?token|refresh[_-]?token|authorization|cookie|set-cookie)"
        r"\s*[:=]\s*[^\s,;]{4,}",
        re.I,
    ),
    re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@", re.I),
)


def normalized_argument_key(value: Any) -> str:
    """Return the separator/case-insensitive form used by secret gates."""

    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def mapping_key_is_secret_shaped(key: Any, value: Any) -> bool:
    """Detect protected-value fields, including provider prefixes/suffixes.

    The three explicit no-secret attestations are allowed only when their value
    is exactly ``False``.  Counters such as ``inputTokens`` and ``token_count``
    remain distinct because they do not end in a singular protected core after
    neutral-value suffix removal.
    """

    normalized = normalized_argument_key(key)
    if normalized in _FALSE_SECRET_ATTESTATION_KEYS:
        return value is not False
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(key or ""))
    tokens = tuple(
        token for token in re.sub(r"[^A-Za-z0-9]+", " ", separated).casefold().split() if token
    )
    compound_markers = (
        "authorization",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "apikey",
        "password",
        "passwd",
        "privatekey",
        "credential",
        "credentials",
        "webhooksecret",
    )
    if normalized in _SENSITIVE_KEYS or any(marker in normalized for marker in compound_markers):
        return True
    if any(
        token
        in {
            "authorization",
            "password",
            "passwd",
            "secret",
            "privatekey",
            "credential",
            "credentials",
            "cookie",
        }
        for token in tokens
    ):
        return True
    if any(
        pair
        in {
            ("api", "key"),
            ("private", "key"),
            ("access", "token"),
            ("refresh", "token"),
            ("auth", "header"),
            ("session", "cookie"),
        }
        for pair in zip(tokens, tokens[1:])
    ):
        return True
    if "token" in tokens:
        metric_prefixes = {"input", "output", "total", "prompt", "completion", "cached"}
        is_token_counter = (
            len(tokens) in {2, 3}
            and tokens[-1] in {"count", "counts"}
            and (len(tokens) == 2 or tokens[0] in metric_prefixes)
        )
        return not is_token_counter
    return False


def string_is_secret_shaped(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_LITERAL_PATTERNS)


def contains_secret_shaped_value(value: Any) -> bool:
    """Recursively reject secret-shaped mapping keys and literal values."""

    if isinstance(value, Mapping):
        return any(
            mapping_key_is_secret_shaped(key, child) or contains_secret_shaped_value(child)
            for key, child in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(contains_secret_shaped_value(child) for child in value)
    return isinstance(value, str) and string_is_secret_shaped(value)


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


def validate_container(value: str, allowed: Iterable[str], *, allow_any: bool = False) -> str:
    requested = str(value or "").strip()
    if not CONTAINER_RE.fullmatch(requested):
        raise ValueError("Container ist nicht freigegeben")
    canonical = CONTAINER_ALIASES.get(requested, requested)
    allowlist = {item.strip() for item in allowed if item.strip()}
    if not allow_any and canonical not in allowlist:
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
