from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Final

_MAX_TRACKED_FILES: Final[int] = 30_000
_MAX_TEXT_BYTES: Final[int] = 1_200_000
_MAX_RESULT_ITEMS: Final[int] = 160
_BOUNDARY_PREFIXES: Final[tuple[str, ...]] = (
    "src/runtime/",
    "src/features/product/runtime/",
    "backend/agent_runtime/",
    "scripts/sovereign-backend/agent_runtime/",
    "tools/sovereign-chatgpt-mcp/",
)
_BOUNDARY_SUFFIXES: Final[frozenset[str]] = frozenset({".py", ".ts", ".tsx", ".js", ".jsx"})

INTENT_BOUNDARY_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "javascript_keyword_intent",
        re.compile(
            r"(?:toLowerCase\(\)|casefold\(\)|lower\(\)).{0,160}"
            r"(?:includes|test|search|match)\(.{0,160}"
            r"(?:create|build|implement|fix|repair|deploy|merge|erstelle|baue|repariere)",
            re.I | re.S,
        ),
    ),
    (
        "python_keyword_intent",
        re.compile(
            r"(?:re\.(?:search|match|fullmatch)|\bin\b).{0,180}"
            r"(?:create|build|implement|fix|repair|deploy|merge|erstelle|baue|repariere)"
            r".{0,180}(?:lower|casefold|\btext\b|\bmessage\b|\bprompt\b|\bmission\b)",
            re.I | re.S,
        ),
    ),
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return result.stdout.strip()


def tracked_files(repo: Path) -> list[str]:
    files = [line for line in _git(repo, "ls-files").splitlines() if line]
    if len(files) > _MAX_TRACKED_FILES:
        raise ValueError("Repository exceeds the bounded tracked-file limit")
    return files


def safe_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_TEXT_BYTES:
            return None
        return path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def path_class(path: str) -> str:
    lowered = path.casefold()
    if any(part in lowered for part in ("node_modules/", "vendor/", "dist/", "build/", "generated/", ".min.")):
        return "GENERATED"
    if any(part in lowered for part in ("test/", "tests/", "__tests__/", ".test.", ".spec.", "fixture", "e2e/")):
        return "TEST_ONLY"
    if any(part in lowered for part in ("legacy", "deprecated", "archive", "obsolete")):
        return "LEGACY"
    if any(part in lowered for part in ("experiment", "prototype", "poc/", "example/", "examples/", "demo/")):
        return "EXPERIMENTAL"
    return "PRODUCTION_CANDIDATE"


def llm_boundary_candidates(repo: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    selected_files = files if files is not None else tracked_files(repo)
    output: list[dict[str, Any]] = []
    for relative in selected_files:
        if not relative.startswith(_BOUNDARY_PREFIXES) or path_class(relative) == "TEST_ONLY":
            continue
        if relative in {
            "tools/sovereign-chatgpt-mcp/repository_skill_tools.py",
            "tools/sovereign-chatgpt-mcp/llm_boundary_contract.py",
            "tools/sovereign-chatgpt-mcp/llm_boundary_ledger.py",
        }:
            continue
        if PurePosixPath(relative).suffix.casefold() not in _BOUNDARY_SUFFIXES:
            continue
        text = safe_text(repo / relative)
        if text is None:
            continue
        for family, pattern in INTENT_BOUNDARY_PATTERNS:
            for match in pattern.finditer(text):
                output.append(
                    {
                        "family": family,
                        "file": relative,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "status": "CANDIDATE_REQUIRES_REVIEW",
                        "truthNotice": "Offline fallback and structured enum handling may be valid.",
                    }
                )
                if len(output) >= _MAX_RESULT_ITEMS:
                    return output
    return output
