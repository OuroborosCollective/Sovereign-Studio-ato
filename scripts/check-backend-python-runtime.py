#!/usr/bin/env python3
"""Fail-fast canary for the complete Sovereign backend test runtime.

This script intentionally imports the same packages that the Flask live-path
contracts need. CI and local runners execute it immediately after dependency
installation so missing or incompatible packages fail with one clear error,
not later during pytest collection.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys

REQUIRED_IMPORTS = {
    "flask": "flask",
    "flask-cors": "flask_cors",
    "requests": "requests",
    "psycopg2-binary": "psycopg2",
    "cryptography": "cryptography",
    "PyJWT": "jwt",
    "pypdf": "pypdf",
    "webauthn": "webauthn",
    "openai-agents": "agents",
    "a2a-sdk": "a2a",
    "pytest": "pytest",
}


def main() -> int:
    failures: list[str] = []
    versions: list[str] = []

    for distribution, module_name in REQUIRED_IMPORTS.items():
        try:
            importlib.import_module(module_name)
            version = importlib.metadata.version(distribution)
            versions.append(f"{distribution}={version}")
        except Exception as exc:  # noqa: BLE001 - diagnostic canary must report all failures
            failures.append(f"{distribution}/{module_name}: {type(exc).__name__}: {exc}")

    if failures:
        print("BACKEND_PYTHON_RUNTIME=FAIL", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        print(
            "Install the single test contract with: "
            "python -m pip install -r backend/requirements-test.txt",
            file=sys.stderr,
        )
        return 1

    from flask import Flask

    probe = Flask("sovereign-backend-runtime-canary")
    if not callable(getattr(probe, "test_client", None)):
        print("BACKEND_PYTHON_RUNTIME=FAIL Flask.test_client unavailable", file=sys.stderr)
        return 1

    print("BACKEND_PYTHON_RUNTIME=PASS " + " ".join(sorted(versions)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
