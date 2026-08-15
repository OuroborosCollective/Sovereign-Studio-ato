from __future__ import annotations

import hashlib
import os
from pathlib import Path

KEY_PATH = Path("/run/secrets/freellmpool_proxy_key")
CATALOG_PATH = Path("/tmp/sovereign-freellmpool-providers.toml")
CATALOG_SHA256 = "eb6647f5bb7aec552a2b82bf03f9341ae246f5025a2ced1caa27b7a08bcb6a90"
CATALOG_OVERLAY = """# Sovereign bounded keyless catalog overlay for immutable freellmpool 0.11.4.
# Runtime image remains pinned; this file uses freellmpool's native FREELLMPOOL_CONFIG override.
# Positive evidence:
# - llm7/default and llm7/fast: upstream 0xzr/freellmpool audit @ 172b1bb6759a1c08cb9d9f7d4e247ca05b34126c, 3/3 non-empty HTTP 200 each.
# - llm7/codestral-latest: Sovereign FreeLLMPool verification run 31877008001, two verified text-chat confirmations.
# Other built-in keyless providers are overridden with no automatic models in this bounded lane;
# this is conservative admission, not a claim that those providers are permanently unavailable.

[[provider]]
id = "pollinations"
label = "Pollinations (bounded; no admitted models)"
adapter = "openai"
base_url = "https://text.pollinations.ai/openai"
auth = "none"
models = []

[[provider]]
id = "llm7"
label = "LLM7 (bounded keyless evidence set)"
adapter = "openai"
base_url = "https://api.llm7.io/v1"
key_env = "LLM7_API_KEY"
key_optional = true
models = [
    { name = "default", rpd = 60 },
    { name = "fast", rpd = 60 },
    { name = "codestral-latest", rpd = 0 },
]

[[provider]]
id = "ovh"
label = "OVHcloud (bounded; no admitted models)"
adapter = "openai"
base_url = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
auth = "none"
models = []

[[provider]]
id = "kilo"
label = "Kilo Gateway (bounded; no admitted models)"
adapter = "openai"
base_url = "https://api.kilo.ai/api/gateway"
auth = "none"
models = []
"""


def install_catalog_overlay() -> None:
    payload = CATALOG_OVERLAY.encode("utf-8")
    if hashlib.sha256(payload).hexdigest() != CATALOG_SHA256:
        raise SystemExit("freellmpool_catalog_overlay_hash_mismatch")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(CATALOG_PATH, flags, 0o400)
    except FileExistsError:
        raise SystemExit("freellmpool_catalog_overlay_path_not_fresh")
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        CATALOG_PATH.unlink(missing_ok=True)
        raise
    if CATALOG_PATH.is_symlink() or not CATALOG_PATH.is_file():
        raise SystemExit("freellmpool_catalog_overlay_not_regular")
    if hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest() != CATALOG_SHA256:
        raise SystemExit("freellmpool_catalog_overlay_readback_mismatch")
    os.environ["FREELLMPOOL_CONFIG"] = str(CATALOG_PATH)
    os.environ["SOVEREIGN_FREELLMPOOL_CATALOG_SHA256"] = CATALOG_SHA256


def main() -> None:
    if KEY_PATH.is_symlink() or not KEY_PATH.is_file():
        raise SystemExit("freellmpool_proxy_key_missing")
    key = KEY_PATH.read_text(encoding="utf-8").strip()
    if not 32 <= len(key) <= 160 or any(marker in key for marker in ("\x00", "\n", "\r")):
        raise SystemExit("freellmpool_proxy_key_invalid")
    install_catalog_overlay()
    os.environ["FREELLMPOOL_PROXY_KEY"] = key
    os.execvp(
        "python",
        [
            "python",
            "-m",
            "freellmpool.cli",
            "proxy",
            "--host",
            "0.0.0.0",
            "--port",
            "8080",
        ],
    )


if __name__ == "__main__":
    main()
