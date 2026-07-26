#!/usr/bin/env python3
"""Build one revision-bound Markdown architecture corpus for large-context AI readers."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = "sovereign.ai-architecture-corpus.v1"
DEFAULT_REVISION = "d8393f4323923b65cf3edb4df0e4d3b3e789cb2a"
DEFAULT_OUTPUT = "docs/architecture/SOVEREIGN_AI_ARCHITECTURE_CORPUS.md"
REFERENCE_FILE_COUNT = 1643
MINIMUM_FILE_COUNT = 1560

LANGUAGE_BY_SUFFIX = {
    ".ts": "typescript",
    ".tsx": "typescript-react",
    ".py": "python",
    ".md": "markdown",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sql": "sql",
    ".sh": "shell",
    ".xml": "xml",
    ".css": "css",
    ".java": "java",
    ".toml": "toml",
}

SENSITIVE_KEYS = tuple(
    value.casefold()
    for value in (
        "api" + "key",
        "access" + "token",
        "refresh" + "token",
        "auth" + "token",
        "client" + "secret",
        "private" + "key",
        "pass" + "word",
        "passwd",
        "authorization",
        "bearer",
        "webhook" + "secret",
    )
)
ASSIGNMENT = re.compile(
    r"^(?P<prefix>\s*[\"']?[A-Za-z_][A-Za-z0-9_.-]*[\"']?\s*(?:=|:)\s*)"
    r"(?P<value>.*?)(?P<suffix>\s*,?\s*(?://.*|#.*)?)$"
)
TOKEN_SHAPE = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b"
)
JWT_SHAPE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
URL_PASSWORD = re.compile(r"(https?://[^\s/:]+:)[^@\s/]+(@)")


def git_bytes(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def language(path: str) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.casefold())


def source_paths(revision: str) -> list[str]:
    raw = git_bytes("ls-tree", "-r", "--name-only", "-z", revision)
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    return sorted(path for path in paths if language(path) is not None)


def decode_blob(blob: bytes) -> tuple[str, str]:
    if b"\0" in blob:
        return base64.b64encode(blob).decode("ascii"), "base64"
    try:
        return blob.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return base64.b64encode(blob).decode("ascii"), "base64"


def redact_text(text: str) -> tuple[str, int]:
    count = 0
    text, hits = PRIVATE_KEY_BLOCK.subn("<REDACTED:PRIVATE_KEY_BLOCK>", text)
    count += hits
    text, hits = TOKEN_SHAPE.subn("<REDACTED:TOKEN>", text)
    count += hits
    text, hits = JWT_SHAPE.subn("<REDACTED:JWT>", text)
    count += hits
    text, hits = URL_PASSWORD.subn(r"\1<REDACTED:URL_PASSWORD>\2", text)
    count += hits

    lines: list[str] = []
    for raw_line in text.splitlines(keepends=True):
        ending = ""
        body = raw_line
        if raw_line.endswith("\r\n"):
            body, ending = raw_line[:-2], "\r\n"
        elif raw_line.endswith("\n"):
            body, ending = raw_line[:-1], "\n"
        match = ASSIGNMENT.match(body)
        if match:
            key = re.split(r"[:=]", match.group("prefix"), maxsplit=1)[0].casefold()
            value = match.group("value").strip()
            if any(marker in key for marker in SENSITIVE_KEYS) and value not in {
                "",
                "null",
                "None",
                "true",
                "false",
                "True",
                "False",
            }:
                body = f"{match.group('prefix')}<REDACTED:SENSITIVE_VALUE>{match.group('suffix')}"
                count += 1
        lines.append(body + ending)
    return "".join(lines), count


def directory_tree(paths: list[str]) -> str:
    root: dict[str, dict] = {}
    file_marker = "\0FILE"
    for path in paths:
        parts = PurePosixPath(path).parts
        node = root
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault(parts[-1], {})[file_marker] = {}

    lines = ["Sovereign-Studio-ato/"]

    def walk(node: dict[str, dict], prefix: str) -> None:
        names = sorted(name for name in node if name != file_marker)
        for index, name in enumerate(names):
            child = node[name]
            last = index == len(names) - 1
            is_file = file_marker in child
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}{'' if is_file else '/'}")
            if not is_file:
                walk(child, prefix + ("    " if last else "│   "))

    walk(root, "")
    return "\n".join(lines)


def build_document(revision: str, paths: list[str]) -> tuple[str, dict[str, object]]:
    records: list[tuple[dict[str, object], str]] = []
    language_counts: dict[str, int] = {}
    redaction_count = 0
    base64_count = 0

    for index, path in enumerate(paths, start=1):
        blob = git_bytes("show", f"{revision}:{path}")
        rendered, encoding = decode_blob(blob)
        file_redactions = 0
        if encoding == "utf-8":
            rendered, file_redactions = redact_text(rendered)
        else:
            base64_count += 1
        lang = language(path) or "text"
        language_counts[lang] = language_counts.get(lang, 0) + 1
        redaction_count += file_redactions
        original_digest = sha256(blob)
        metadata: dict[str, object] = {
            "index": index,
            "path": path,
            "language": lang,
            "original_bytes": len(blob),
            "original_sha256": original_digest,
            "rendered_sha256": sha256(rendered.encode("utf-8")),
            "encoding": encoding,
            "redaction_count": file_redactions,
            "content_delimiter": f"SOVEREIGN_CONTENT_{original_digest[:24].upper()}",
        }
        records.append((metadata, rendered))

    frontmatter = {
        "schema_version": SCHEMA_VERSION,
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "source_revision": revision,
        "source_revision_exact": True,
        "source_file_count": len(paths),
        "reference_file_count": REFERENCE_FILE_COUNT,
        "minimum_file_count": MINIMUM_FILE_COUNT,
        "architecture_coverage_target": 0.95,
        "content_mode": "single_markdown_monolith",
        "content_order": "lexicographic_path",
        "language_counts": dict(sorted(language_counts.items())),
        "base64_file_count": base64_count,
        "redaction_count": redaction_count,
        "runtime_truth_claimed": False,
        "truth_notice": "Static repository snapshot only; live activity requires separate runtime evidence.",
    }

    parts = [
        "---\n",
        json.dumps(frontmatter, ensure_ascii=False, indent=2, sort_keys=True),
        "\n---\n\n",
        "# Sovereign Studio ATO: Machine-Readable Architecture Corpus\n\n",
        "One revision-bound Markdown monolith for Gemini and other large-context AI systems.\n\n",
        "## Parsing Contract\n\n",
        "Read the JSON frontmatter, then the complete tree, then each `SOVEREIGN_FILE_BEGIN` record. "
        "The original hash identifies the Git blob; the rendered hash identifies the embedded content.\n\n",
        "## Complete Directory Tree\n\n```text\n",
        directory_tree(paths),
        "\n```\n\n## File Records\n\n",
    ]

    for metadata, rendered in records:
        delimiter = str(metadata["content_delimiter"])
        parts.append(
            "<!-- SOVEREIGN_FILE_BEGIN "
            + json.dumps(metadata, ensure_ascii=False, sort_keys=True)
            + " -->\n"
        )
        parts.append(f"<{delimiter}>\n")
        parts.append(rendered)
        if rendered and not rendered.endswith(("\n", "\r")):
            parts.append("\n")
        parts.append(f"</{delimiter}>\n<!-- SOVEREIGN_FILE_END -->\n\n")

    terminator = {
        "schema_version": SCHEMA_VERSION,
        "source_revision": revision,
        "file_records_written": len(records),
        "complete": len(records) >= MINIMUM_FILE_COUNT,
    }
    parts.append("## Corpus Terminator\n\n" + json.dumps(terminator, sort_keys=True) + "\n")
    document = "".join(parts)

    begin_count = document.count("<!-- SOVEREIGN_FILE_BEGIN ")
    end_count = document.count("<!-- SOVEREIGN_FILE_END -->")
    if begin_count != len(records) or end_count != len(records):
        raise RuntimeError(
            f"record mismatch: begin={begin_count}, end={end_count}, expected={len(records)}"
        )
    return document, frontmatter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    revision = git_bytes("rev-parse", "--verify", f"{args.revision}^{{commit}}").decode().strip()
    if revision != args.revision:
        raise RuntimeError(f"revision mismatch: requested={args.revision}, resolved={revision}")
    paths = source_paths(revision)
    if len(paths) < MINIMUM_FILE_COUNT:
        raise RuntimeError(f"architecture coverage too small: {len(paths)} < {MINIMUM_FILE_COUNT}")
    document, frontmatter = build_document(revision, paths)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="")
    payload = output.read_bytes()
    print(
        json.dumps(
            {
                "status": "CORPUS_GENERATED",
                "output": output.as_posix(),
                "output_bytes": len(payload),
                "output_sha256": sha256(payload),
                "source_file_count": frontmatter["source_file_count"],
                "redaction_count": frontmatter["redaction_count"],
                "base64_file_count": frontmatter["base64_file_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CORPUS_GENERATION_FAILED: {exc}", file=sys.stderr)
        raise
