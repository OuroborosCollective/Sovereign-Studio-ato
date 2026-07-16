#!/usr/bin/env python3
"""Start LiteLLM with one owner-managed provider credential.

The credential is mounted as a read-only file. It is copied only into the
LiteLLM process environment and is never printed or persisted by this wrapper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROVIDER_INPUT = Path("/run/secrets/openai_api_key")
MAX_BYTES = 8192


def main() -> None:
    if PROVIDER_INPUT.is_symlink() or not PROVIDER_INPUT.is_file():
        raise SystemExit("provider input is unavailable")
    size = PROVIDER_INPUT.stat().st_size
    if size < 16 or size > MAX_BYTES:
        raise SystemExit("provider input has an invalid size")
    value = PROVIDER_INPUT.read_text("utf-8").strip()
    if len(value) < 16 or "\x00" in value or "\n" in value or "\r" in value:
        raise SystemExit("provider input has an invalid format")
    environment = os.environ.copy()
    environment["OPENAI_API_KEY"] = value
    os.execvpe("litellm", ["litellm", *sys.argv[1:]], environment)


if __name__ == "__main__":
    main()
