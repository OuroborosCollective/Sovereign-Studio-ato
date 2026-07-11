"""Workspace discovery and optional explanation support for the repository janitor."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from .janitor_rules import (
    FORBIDDEN_FILE_NAMES,
    FORBIDDEN_SUFFIXES,
    SKIP_DIRECTORY_NAMES,
    SUPPORTED_EXTENSIONS,
    _mask_sensitive,
)


def _is_skipped_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in SKIP_DIRECTORY_NAMES for part in relative.parts)


def _safe_target(root: Path, relative_path: str) -> Path | None:
    candidate_text = str(relative_path or "").strip().replace("\\", "/")
    if not candidate_text or candidate_text.startswith("/"):
        return None
    target = (root / candidate_text).resolve()
    if target != root and root not in target.parents:
        return None
    if _is_skipped_path(target, root):
        return None
    lower_name = target.name.lower()
    if lower_name in FORBIDDEN_FILE_NAMES or target.suffix.lower() in FORBIDDEN_SUFFIXES:
        return None
    return target


def _iter_source_files(
    root: Path,
    paths: Iterable[str],
    max_files: int,
    *,
    include_docs: bool = False,
) -> Iterable[Path]:
    requested = [str(value).strip() for value in paths if str(value).strip()]
    seeds: list[Path] = []
    if requested:
        for relative in requested:
            target = _safe_target(root, relative)
            if target is not None and target.exists():
                seeds.append(target)
    else:
        seeds.append(root)

    candidates_by_path: dict[Path, Path] = {}
    for seed in seeds:
        candidates = [seed] if seed.is_file() else seed.rglob("*")
        for candidate in candidates:
            try:
                if candidate.is_symlink():
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in candidates_by_path or _is_skipped_path(resolved, root):
                continue
            suffix = resolved.suffix.lower()
            if not resolved.is_file() or suffix not in SUPPORTED_EXTENSIONS:
                continue
            if suffix == ".md" and not include_docs and not requested:
                continue
            candidates_by_path[resolved] = resolved

    priority = {
        ".py": 0, ".ts": 0, ".tsx": 0, ".js": 0, ".jsx": 0,
        ".mjs": 0, ".cjs": 0, ".go": 0, ".rs": 0,
        ".sh": 1, ".yml": 1, ".yaml": 1, ".json": 1, ".toml": 1,
        ".md": 2,
    }
    ordered = sorted(
        candidates_by_path.values(),
        key=lambda item: (priority.get(item.suffix.lower(), 3), item.relative_to(root).as_posix()),
    )
    yield from ordered[:max_files]


def _detect_test_command(root: Path) -> str | None:
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = package.get("scripts") if isinstance(package, dict) else None
            if isinstance(scripts, dict):
                manager = (
                    "pnpm" if (root / "pnpm-lock.yaml").exists()
                    else "yarn" if (root / "yarn.lock").exists()
                    else "npm"
                )
                run = f"{manager} run"
                if "type-check" in scripts and "test" in scripts:
                    return f"{run} type-check && {run} test"
                if "test:all" in scripts:
                    return f"{run} test:all"
                if "test" in scripts:
                    return f"{run} test"
        except (OSError, ValueError, TypeError):
            package = None
    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        return "python -m pytest"
    if (root / "go.mod").exists():
        return "go test ./..."
    if (root / "Cargo.toml").exists():
        return "cargo test"
    return None


def _optional_ollama_explanation(findings: list[dict[str, Any]], family: str) -> tuple[str | None, str | None]:
    if os.getenv("SOVEREIGN_JANITOR_OLLAMA_ENABLED", "false").lower() != "true":
        return None, "Local Ollama explanation is disabled by server policy."
    url = os.getenv("SOVEREIGN_JANITOR_OLLAMA_URL", "http://127.0.0.1:11434/api/chat").strip()
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return None, "Ollama URL must be loopback HTTP."
    try:
        import requests

        compact = [
            {
                "ruleId": item["ruleId"],
                "severity": item["severity"],
                "path": item["path"],
                "line": item["line"],
                "message": item["message"],
            }
            for item in findings[:20]
        ]
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "model": os.getenv("SOVEREIGN_JANITOR_OLLAMA_MODEL", "qwen2.5-coder"),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Explain deterministic repository findings. Do not produce code, patches, "
                            "commands, secrets, success claims, or JSON. Keep the explanation under 250 words."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"family": family, "findings": compact}, ensure_ascii=False),
                    },
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=20,
        )
        if not response.ok:
            return None, f"Ollama returned HTTP {response.status_code}."
        data = response.json()
        text = data.get("message", {}).get("content", "") if isinstance(data, dict) else ""
        return _mask_sensitive(str(text))[:4_000] or None, None
    except Exception as exc:  # explanation failure must never fail the deterministic scan
        return None, f"Ollama explanation unavailable: {type(exc).__name__}."
