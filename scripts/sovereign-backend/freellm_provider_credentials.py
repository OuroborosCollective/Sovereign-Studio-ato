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
    normalized = normalize_freellm_provider_id(provider_id)
    return provider_secret_directory(owner_root) / f"{normalized}.key"


def provider_keyless_marker_path(owner_root: Path, provider_id: str) -> Path:
    normalized = normalize_freellm_provider_id(provider_id)
    if not bool(FREELLM_PROVIDER_SPECS[normalized].get("keyless")):
        raise ValueError("freellm_provider_not_keyless")
    return provider_secret_directory(owner_root) / f"{normalized}.keyless"
