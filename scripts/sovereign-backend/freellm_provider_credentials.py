"""Static FreeLLMAPI provider credential contracts.

Only provider identities and secret-file metadata live here. Raw credentials are
never returned, logged or persisted in PostgreSQL.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
_SECRET_DIRECTORY = "freellm-provider-keys"
FREELLM_RUNTIME_UID = 1000
FREELLM_RUNTIME_GID = 1000

# Strong provider-issued prefixes only. Unknown or ambiguous keys remain
# fail-closed and require an explicit provider choice in the admin fallback.
_PROVIDER_KEY_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"AQ.", "google"),
    (b"AIza", "google"),
    (b"gsk_", "groq"),
    (b"sk-or-v1-", "openrouter"),
    (b"github_pat_", "github"),
    (b"ghp_", "github"),
    (b"nvapi-", "nvidia"),
    (b"hf_", "huggingface"),
)

FREELLM_PROVIDER_SPECS: dict[str, dict[str, Any]] = {
    "google": {"label": "Google AI Studio", "keyless": False},
    "groq": {"label": "Groq", "keyless": False},
    "cerebras": {"label": "Cerebras", "keyless": False},
    "nvidia": {"label": "NVIDIA NIM", "keyless": False},
    "mistral": {"label": "Mistral", "keyless": False},
    "openrouter": {"label": "OpenRouter Free-Modelle", "keyless": False},
    "github": {"label": "GitHub Models", "keyless": False},
    "cohere": {"label": "Cohere", "keyless": False},
    "cloudflare": {"label": "Cloudflare Workers AI", "keyless": False},
    "zhipu": {"label": "Zhipu / Z.ai", "keyless": False},
    "ollama": {"label": "Ollama Cloud", "keyless": False},
    "llm7": {"label": "LLM7", "keyless": False},
    "huggingface": {"label": "Hugging Face Router", "keyless": False},
    "opencode": {"label": "OpenCode Zen", "keyless": False},
    "agnes": {"label": "Agnes AI", "keyless": False},
    "reka": {"label": "Reka", "keyless": False},
    "siliconflow": {"label": "SiliconFlow", "keyless": False},
    "routeway": {"label": "Routeway", "keyless": False},
    "bazaarlink": {"label": "BazaarLink", "keyless": False},
    "ainative": {"label": "AI Native", "keyless": False},
    "aion": {"label": "Aion", "keyless": False},
    "requesty": {"label": "Requesty", "keyless": False},
    "navy": {"label": "Navy", "keyless": False},
    "nara": {"label": "NaraRouter", "keyless": False},
    "sealion": {"label": "SEA-LION", "keyless": False},
    "kilo": {
        "label": "Kilo Gateway (anonym)",
        "keyless": True,
        "privacyNotice": "Prompts und Ausgaben können laut Provider für Training protokolliert werden.",
    },
    "pollinations": {
        "label": "Pollinations (Publishable Key)",
        "keyless": False,
    },
    "ovh": {
        "label": "OVH AI Endpoints (anonym)",
        "keyless": True,
        "privacyNotice": "Anonymer Tier ist stark rate-limitiert und kann sich ändern.",
    },
    "aihorde": {
        "label": "AI Horde (anonym)",
        "keyless": True,
        "privacyNotice": "Community-Inferenz mit niedriger Priorität und variabler Wartezeit.",
    },
}


def normalize_freellm_provider_id(value: Any) -> str:
    provider_id = str(value or "").strip().lower()
    if not _PROVIDER_ID_RE.fullmatch(provider_id) or provider_id not in FREELLM_PROVIDER_SPECS:
        raise ValueError("freellm_provider_id_invalid")
    return provider_id


def detect_freellm_provider_id_from_key(value: bytes | bytearray | memoryview) -> str:
    """Return one provider only for a strong, non-ambiguous key signature."""
    protected = value if isinstance(value, bytearray) else bytearray(value)
    start = 0
    end = len(protected)
    while start < end and protected[start] in b" \t\r\n":
        start += 1
    while end > start and protected[end - 1] in b" \t\r\n":
        end -= 1
    if end - start < 8:
        raise ValueError("freellm_provider_key_unrecognized")
    candidate = memoryview(protected)[start:end]
    matches = {
        provider_id
        for prefix, provider_id in _PROVIDER_KEY_PREFIXES
        if len(candidate) >= len(prefix) and bytes(candidate[:len(prefix)]) == prefix
    }
    if len(matches) != 1:
        raise ValueError("freellm_provider_key_unrecognized")
    return next(iter(matches))


def provider_target_id(provider_id: str) -> str:
    normalized = normalize_freellm_provider_id(provider_id)
    return f"freellm_provider_{normalized.replace('-', '_')}_key"


def provider_id_from_target_id(target_id: str) -> str:
    candidate = str(target_id or "").strip()
    for provider_id in FREELLM_PROVIDER_SPECS:
        if provider_target_id(provider_id) == candidate:
            return provider_id
    raise ValueError("freellm_provider_target_id_invalid")


def provider_secret_directory(owner_root: Path) -> Path:
    return Path(owner_root).resolve() / _SECRET_DIRECTORY


def provider_secret_path(owner_root: Path, provider_id: str) -> Path:
    """Legacy single-key path retained for backwards-compatible imports."""
    normalized = normalize_freellm_provider_id(provider_id)
    return provider_secret_directory(owner_root) / f"{normalized}.key"


def provider_secret_pool_path(
    owner_root: Path,
    provider_id: str,
    fingerprint_sha256: str,
) -> Path:
    normalized = normalize_freellm_provider_id(provider_id)
    fingerprint = str(fingerprint_sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("freellm_provider_key_fingerprint_invalid")
    return provider_secret_directory(owner_root) / f"{normalized}.{fingerprint}.key"


def provider_secret_paths(owner_root: Path, provider_id: str) -> tuple[Path, ...]:
    normalized = normalize_freellm_provider_id(provider_id)
    root = provider_secret_directory(owner_root)
    candidates = [provider_secret_path(owner_root, normalized)]
    if root.is_dir():
        for path in sorted(root.glob(f"{normalized}.*.key"))[:100]:
            if re.fullmatch(
                rf"{re.escape(normalized)}\.[0-9a-f]{{64}}\.key",
                path.name,
            ):
                candidates.append(path)
    return tuple(dict.fromkeys(candidates))


def provider_keyless_marker_path(owner_root: Path, provider_id: str) -> Path:
    normalized = normalize_freellm_provider_id(provider_id)
    if not bool(FREELLM_PROVIDER_SPECS[normalized].get("keyless")):
        raise ValueError("freellm_provider_not_keyless")
    return provider_secret_directory(owner_root) / f"{normalized}.keyless"
