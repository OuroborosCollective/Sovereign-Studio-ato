from __future__ import annotations

import os
from pathlib import Path

KEY_PATH = Path("/run/secrets/freellmpool_proxy_key")


def main() -> None:
    if KEY_PATH.is_symlink() or not KEY_PATH.is_file():
        raise SystemExit("freellmpool_proxy_key_missing")
    key = KEY_PATH.read_text(encoding="utf-8").strip()
    if not 32 <= len(key) <= 160 or any(marker in key for marker in ("\x00", "\n", "\r")):
        raise SystemExit("freellmpool_proxy_key_invalid")
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
