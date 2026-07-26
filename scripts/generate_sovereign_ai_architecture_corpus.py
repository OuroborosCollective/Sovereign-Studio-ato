#!/usr/bin/env python3
"""Generate one revision-bound Markdown corpus containing all mapped repository text files.

The output is intentionally monolithic for ingestion by large-context AI systems.
It reads blobs from one exact Git revision, never from the mutable worktree, and
redacts secret-shaped values while preserving path, size and original SHA-256
metadata for evidence-bound comparison.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

SCHEMA_VERSION = "sovereign.ai-architecture-corpus.v1"
DEFAULT_REVISION = "d8393f4323923b65cf3edb4df0e4d3b3e789cb2a"
DEFAULT_OUTPUT = "docs/architecture/SOVEREIGN_AI_ARCHITECTURE_CORPUS.md"
EXPECTED_FILE_COUNT = 1643
MINIMUM_ARCHITECTURE_COVERAGE = 0.95

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

SECRET_KEY = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|"
    r"authorization|bearer|client[_-]?secret|private[_-]?key|password|passwd|"
    r"pwd|secret|signing[_-]?key|webhook[_-]?secret)"
)
PEM_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
JWT_TOKEN = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
KNOWN_TOKEN = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"glpat-[A-Za-z0-9_-]{16,}|xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{20,})\b"
)
BEARER_VALUE = re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/-]{12,}")
URL_USERINFO = re.compile(r"(https?://[^\s/:]+:)[^@\s/]+(@)")


@dataclass(frozen=True)
class FileRecord:
    index: int
    path: str
    language: str
    original_bytes: bytes
    original_sha256: str
    rendered_content: str
    rendered_sha256: str
    redaction_count: int
    encoding: str


def run_git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        error = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {error}")
    return completed.stdout


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def mapped_language(path: str) -> str | None:
    return LANGUAGE_BY_SUFFIX.get(PurePosixPath(path).suffix.lower())


def tracked_mapped_paths(revision: str) -> list[str]:
    raw = run_git("ls-tree", "-r", "--name-only", "-z", revision)
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    mapped = [path for path in paths if mapped_language(path) is not None]
    return sorted(mapped)


def read_blob(revision: str, path: str) -> bytes:
    return run_git("show", f"{revision}:{path}")


def redact_assignment_line(line: str) -> tuple[str, int]:
    """Redact values assigned to secret-shaped keys without exposing the value."""
    if not SECRET_KEY.search(line):
        return line, 0

    patterns = (
        re.compile(
            r"^(?P<prefix>\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_.-]*\s*=\s*)"
            r"(?P<value>.*?)(?P<suffix>\s*(?:#.*)?)$"
        ),
        re.compile(
            r"^(?P<prefix>\s*[\"']?[A-Za-z_][A-Za-z0-9_.-]*[\"']?\s*:\s*)"
            r"(?P<value>.*?)(?P<suffix>\s*,?\s*(?://.*|#.*)?)$"
        ),
    )
    for pattern in patterns:
        match = pattern.match(line)
        if not match:
            continue
        prefix = match.group("prefix")
        key = re.split(r"[:=]", prefix, maxsplit=1)[0]
        if not SECRET_KEY.search(key):
            continue
        value = match.group("value").strip()
        if not value or value in {"null", "None", "true", "false", "True", "False"}:
            return line, 0
        quote = '"' if value.startswith('"') and value.endswith('"') else ""
        replacement = f'{quote}<REDACTED:SECRET_VALUE>{quote}'
        return f"{prefix}{replacement}{match.group('suffix')}", 1
    return line, 0


def redact_text(text: str) -> tuple[str, int]:
    count = 0

    text, substitutions = PEM_PRIVATE_KEY.subn(
        "<REDACTED:PRIVATE_KEY_BLOCK>", text
    )
    count += substitutions
    text, substitutions = JWT_TOKEN.subn("<REDACTED:JWT>", text)
    count += substitutions
    text, substitutions = KNOWN_TOKEN.subn("<REDACTED:TOKEN>", text)
    count += substitutions
    text, substitutions = BEARER_VALUE.subn(
        r"\1<REDACTED:BEARER_TOKEN>", text
    )
    count += substitutions
    text, substitutions = URL_USERINFO.subn(
        r"\1<REDACTED:URL_PASSWORD>\2", text
    )
    count += substitutions

    rendered_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        ending = ""
        body = line
        if line.endswith("\r\n"):
            body, ending = line[:-2], "\r\n"
        elif line.endswith("\n"):
            body, ending = line[:-1], "\n"
        rendered, line_count = redact_assignment_line(body)
        rendered_lines.append(rendered + ending)
        count += line_count

    return "".join(rendered_lines), count


def decode_blob(blob: bytes) -> tuple[str, str]:
    try:
        return blob.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        encoded = base64.b64encode(blob).decode("ascii")
        return encoded, "base64"


def build_records(revision: str, paths: Iterable[str]) -> list[FileRecord]:
    records: list[FileRecord] = []
    for index, path in enumerate(paths, start=1):
        blob = read_blob(revision, path)
        decoded, encoding = decode_blob(blob)
        if encoding == "utf-8":
            rendered, redaction_count = redact_text(decoded)
        else:
            rendered, redaction_count = decoded, 0
        records.append(
            FileRecord(
                index=index,
                path=path,
                language=mapped_language(path) or "text",
                original_bytes=blob,
                original_sha256=sha256_bytes(blob),
                rendered_content=rendered,
                rendered_sha256=sha256_bytes(rendered.encode("utf-8")),
                redaction_count=redaction_count,
                encoding=encoding,
            )
        )
    return records


def build_tree(paths: Iterable[str]) -> str:
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
        for position, name in enumerate(names):
            child = node[name]
            last = position == len(names) - 1
            branch = "└── " if last else "├── "
            is_file = file_marker in child
            lines.append(f"{prefix}{branch}{name}{'' if is_file else '/'}")
            if not is_file:
                walk(child, prefix + ("    " if last else "│   "))

    walk(root, "")
    return "\n".join(lines)


def language_counts(records: Iterable[FileRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        counts[record.language] = counts.get(record.language, 0) + 1
    return dict(sorted(counts.items()))


def render_document(revision: str, records: list[FileRecord]) -> str:
    tree = build_tree(record.path for record in records)
    redacted_files = sum(1 for record in records if record.redaction_count)
    total_redactions = sum(record.redaction_count for record in records)
    counts = language_counts(records)

    frontmatter = {
        "schema_version": SCHEMA_VERSION,
        "repository": "OuroborosCollective/Sovereign-Studio-ato",
        "source_revision": revision,
        "source_revision_exact": True,
        "source_file_count": len(records),
        "expected_source_file_count": EXPECTED_FILE_COUNT,
        "minimum_architecture_coverage": MINIMUM_ARCHITECTURE_COVERAGE,
        "selection": "git-tracked files with mapped text extensions",
        "language_counts": counts,
        "content_mode": "single_markdown_monolith",
        "content_order": "lexicographic_path",
        "original_blob_hash_algorithm": "sha256",
        "rendered_content_hash_algorithm": "sha256",
        "redaction_policy": "secret-shaped values are replaced; original values are never copied",
        "files_with_redactions": redacted_files,
        "redaction_count": total_redactions,
        "runtime_truth_claimed": False,
        "truth_notice": "Repository snapshot and static content only. Runtime activity requires separate evidence readback.",
    }

    parts: list[str] = [
        "---\n",
        json.dumps(frontmatter, ensure_ascii=False, indent=2, sort_keys=True),
        "\n---\n\n",
        "# Sovereign Studio ATO: Machine-Readable Architecture Corpus\n\n",
        "This single Markdown file contains the complete mapped text corpus from the exact source revision. "
        "Each source file is represented once with original blob identity, rendered-content identity, language, "
        "byte size, encoding and explicit redaction evidence.\n\n",
        "## Parsing Contract\n\n",
        "1. Parse the JSON frontmatter first.\n",
        "2. Read the directory tree for path topology.\n",
        "3. Parse every `SOVEREIGN_FILE_BEGIN` JSON object.\n",
        "4. Read raw content between that record's unique content delimiters.\n",
        "5. Treat `original_sha256` as the source-blob identity and `rendered_sha256` as the embedded-content identity.\n",
        "6. A redaction marker is evidence that the source contained a secret-shaped value, not the value itself.\n\n",
        "## Complete Directory Tree\n\n",
        "```text\n",
        tree,
        "\n```\n\n",
        "## File Records\n\n",
    ]

    for record in records:
        token = f"SOVEREIGN_CONTENT_{record.original_sha256[:24].upper()}"
        metadata = {
            "index": record.index,
            "path": record.path,
            "language": record.language,
            "original_bytes": len(record.original_bytes),
            "original_sha256": record.original_sha256,
            "rendered_sha256": record.rendered_sha256,
            "encoding": record.encoding,
            "redaction_count": record.redaction_count,
            "content_delimiter": token,
        }
        parts.extend(
            [
                "<!-- SOVEREIGN_FILE_BEGIN ",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                " -->\n",
                f"<{token}>\n",
                record.rendered_content,
            ]
        )
        if record.rendered_content and not record.rendered_content.endswith(("\n", "\r")):
            parts.append("\n")
        parts.extend(
            [
                f"</{token}>\n",
                "<!-- SOVEREIGN_FILE_END -->\n\n",
            ]
        )

    parts.extend(
        [
            "## Corpus Terminator\n\n",
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "source_revision": revision,
                    "file_records_written": len(records),
                    "complete": len(records) >= int(EXPECTED_FILE_COUNT * MINIMUM_ARCHITECTURE_COVERAGE),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "\n",
        ]
    )
    return "".join(parts)


def validate_document(document: str, records: list[FileRecord]) -> None:
    begin_count = document.count("<!-- SOVEREIGN_FILE_BEGIN ")
    end_count = document.count("<!-- SOVEREIGN_FILE_END -->")
    if begin_count != len(records) or end_count != len(records):
        raise RuntimeError(
            f"record delimiter mismatch: begin={begin_count}, end={end_count}, expected={len(records)}"
        )
    for record in records:
        token = f"SOVEREIGN_CONTENT_{record.original_sha256[:24].upper()}"
        if document.count(f"<{token}>") != 1 or document.count(f"</{token}>") != 1:
            raise RuntimeError(f"content delimiter mismatch for {record.path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--expected-count", type=int, default=EXPECTED_FILE_COUNT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    revision = run_git("rev-parse", "--verify", f"{args.revision}^{{commit}}").decode().strip()
    if revision != args.revision:
        raise RuntimeError(f"revision did not resolve exactly: requested={args.revision}, resolved={revision}")

    paths = tracked_mapped_paths(revision)
    minimum_count = int(args.expected_count * MINIMUM_ARCHITECTURE_COVERAGE)
    if len(paths) < minimum_count:
        by_language: dict[str, int] = {}
        for path in paths:
            language = mapped_language(path) or "unknown"
            by_language[language] = by_language.get(language, 0) + 1
        raise RuntimeError(
            "mapped file count mismatch: "
            f"actual={len(paths)}, minimum={minimum_count}, reference={args.expected_count}, languages={json.dumps(by_language, sort_keys=True)}"
        )

    records = build_records(revision, paths)
    document = render_document(revision, records)
    validate_document(document, records)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="")

    output_bytes = output.read_bytes()
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "CORPUS_GENERATED",
        "source_revision": revision,
        "output": output.as_posix(),
        "file_records": len(records),
        "output_bytes": len(output_bytes),
        "output_sha256": sha256_bytes(output_bytes),
        "files_with_redactions": sum(1 for record in records if record.redaction_count),
        "redaction_count": sum(record.redaction_count for record in records),
        "language_counts": language_counts(records),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CORPUS_GENERATION_FAILED: {exc}", file=sys.stderr)
        raise
