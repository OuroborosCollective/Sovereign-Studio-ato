from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Final

from llm_boundary_contract import llm_boundary_candidates, safe_text, tracked_files

LEDGER_SCHEMA: Final[str] = "sovereign.llm-tool-boundary-review-ledger.v1"
ALLOWED_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {
        "STRUCTURED_POLICY",
        "OFFLINE_FALLBACK",
        "TEST_OR_ANALYSIS",
        "FORBIDDEN_FREE_LANGUAGE",
    }
)
_CANONICAL_MIRROR_PREFIX: Final[str] = "scripts/sovereign-backend/agent_runtime/"
_NON_CANONICAL_MIRROR_PREFIX: Final[str] = "backend/agent_runtime/"
_TS_DECLARATION = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|"
    r"^\s*(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\b"
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


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_path(repo: Path, relative: str) -> tuple[str, list[str]]:
    if relative.startswith(_NON_CANONICAL_MIRROR_PREFIX):
        suffix = relative.removeprefix(_NON_CANONICAL_MIRROR_PREFIX)
        canonical = _CANONICAL_MIRROR_PREFIX + suffix
        canonical_path = repo / canonical
        source_path = repo / relative
        if canonical_path.is_file() and source_path.is_file() and canonical_path.read_bytes() == source_path.read_bytes():
            return canonical, [relative]
    if relative.startswith(_CANONICAL_MIRROR_PREFIX):
        suffix = relative.removeprefix(_CANONICAL_MIRROR_PREFIX)
        mirror = _NON_CANONICAL_MIRROR_PREFIX + suffix
        canonical_path = repo / relative
        mirror_path = repo / mirror
        if canonical_path.is_file() and mirror_path.is_file() and canonical_path.read_bytes() == mirror_path.read_bytes():
            return relative, [mirror]
    return relative, []


def _python_symbols(text: str) -> list[tuple[int, int, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    output: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = ".".join((*parents, child.name))
                output.append((int(child.lineno), int(getattr(child, "end_lineno", child.lineno)), name))
                visit(child, (*parents, child.name))
            else:
                visit(child, parents)

    visit(tree, ())
    return output


def _nearest_symbol(path: str, text: str, line: int) -> str:
    if path.endswith(".py"):
        containing = [item for item in _python_symbols(text) if item[0] <= line <= item[1]]
        if containing:
            containing.sort(key=lambda item: ((item[1] - item[0]), -item[0], item[2]))
            return containing[0][2]
        return "<module>"
    lines = text.splitlines()
    for index in range(min(max(line - 1, 0), len(lines) - 1), -1, -1):
        match = _TS_DECLARATION.search(lines[index])
        if match:
            return next(group for group in match.groups() if group)
    return "<module>"


def _anchor_sha256(text: str, line: int) -> str:
    lines = text.splitlines()
    start = max(0, line - 3)
    end = min(len(lines), line + 2)
    normalized = "\n".join(item.rstrip() for item in lines[start:end]).strip()
    return _sha256(normalized.encode("utf-8"))


def _candidate_id(candidate: dict[str, Any]) -> str:
    identity = "|".join(
        (
            str(candidate["canonicalPath"]),
            str(candidate["symbol"]),
            str(candidate["patternFamily"]),
            str(candidate["line"]),
            str(candidate["anchorSha256"]),
        )
    )
    return "llm-boundary:" + _sha256(identity.encode("utf-8"))[:24]


def discover_review_candidates(repo: Path) -> dict[str, Any]:
    files = tracked_files(repo)
    raw = llm_boundary_candidates(repo, files)
    canonical: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in raw:
        canonical_path, mirror_paths = _canonical_path(repo, str(item["file"]))
        text = safe_text(repo / canonical_path)
        if text is None:
            raise RuntimeError(f"Candidate file is not readable: {canonical_path}")
        line = int(item["line"])
        key = (canonical_path, str(item["family"]), line)
        record = {
            "canonicalPath": canonical_path,
            "mirrorPaths": sorted(mirror_paths),
            "symbol": _nearest_symbol(canonical_path, text, line),
            "line": line,
            "patternFamily": str(item["family"]),
            "fileSha256": _sha256((repo / canonical_path).read_bytes()),
            "anchorSha256": _anchor_sha256(text, line),
            "reopenOnChange": True,
        }
        existing = canonical.get(key)
        if existing is None:
            canonical[key] = record
        else:
            existing["mirrorPaths"] = sorted(set(existing["mirrorPaths"]) | set(record["mirrorPaths"]))
    entries = sorted(
        canonical.values(),
        key=lambda item: (item["canonicalPath"], item["line"], item["patternFamily"]),
    )
    for entry in entries:
        entry["candidateId"] = _candidate_id(entry)
    return {
        "sourceRevision": _git(repo, "rev-parse", "HEAD"),
        "rawCandidateCount": len(raw),
        "canonicalCandidateCount": len(entries),
        "entries": entries,
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ledger_sha256(payload: dict[str, Any]) -> str:
    signed = {
        "schemaVersion": payload.get("schemaVersion"),
        "detector": payload.get("detector"),
        "rawCandidateCount": payload.get("rawCandidateCount"),
        "canonicalCandidateCount": payload.get("canonicalCandidateCount"),
        "entries": payload.get("entries"),
    }
    return _sha256(_canonical_json(signed))


def generate_unreviewed_ledger(repo: Path) -> dict[str, Any]:
    discovery = discover_review_candidates(repo)
    entries = [
        {
            **entry,
            "classification": "UNREVIEWED",
            "rationale": "",
        }
        for entry in discovery["entries"]
    ]
    payload: dict[str, Any] = {
        "schemaVersion": LEDGER_SCHEMA,
        "detector": "tools/sovereign-chatgpt-mcp/llm_boundary_contract.py",
        "sourceRevision": discovery["sourceRevision"],
        "rawCandidateCount": discovery["rawCandidateCount"],
        "canonicalCandidateCount": discovery["canonicalCandidateCount"],
        "entries": entries,
    }
    payload["ledgerSha256"] = ledger_sha256(payload)
    return payload


def validate_ledger(repo: Path, payload: dict[str, Any]) -> dict[str, Any]:
    discovery = discover_review_candidates(repo)
    findings: list[str] = []
    if payload.get("schemaVersion") != LEDGER_SCHEMA:
        findings.append("LEDGER_SCHEMA_MISMATCH")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        entries = []
        findings.append("LEDGER_ENTRIES_MISSING")
    expected_by_id = {entry["candidateId"]: entry for entry in discovery["entries"]}
    actual_by_id: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            findings.append(f"ENTRY_{index + 1}_NOT_OBJECT")
            continue
        candidate_id = str(entry.get("candidateId") or "")
        if not candidate_id:
            findings.append(f"ENTRY_{index + 1}_CANDIDATE_ID_MISSING")
            continue
        if candidate_id in actual_by_id:
            findings.append(f"DUPLICATE_CANDIDATE:{candidate_id}")
            continue
        actual_by_id[candidate_id] = entry
    for candidate_id in sorted(set(expected_by_id) - set(actual_by_id)):
        findings.append(f"MISSING_CANDIDATE:{candidate_id}")
    for candidate_id in sorted(set(actual_by_id) - set(expected_by_id)):
        findings.append(f"STALE_OR_REMOVED_CANDIDATE:{candidate_id}")
    bound_fields = (
        "canonicalPath",
        "mirrorPaths",
        "symbol",
        "line",
        "patternFamily",
        "fileSha256",
        "anchorSha256",
        "reopenOnChange",
    )
    for candidate_id in sorted(set(expected_by_id) & set(actual_by_id)):
        expected = expected_by_id[candidate_id]
        actual = actual_by_id[candidate_id]
        for field in bound_fields:
            if actual.get(field) != expected.get(field):
                findings.append(f"BINDING_DRIFT:{candidate_id}:{field}")
        classification = str(actual.get("classification") or "")
        rationale = " ".join(str(actual.get("rationale") or "").split())
        if classification not in ALLOWED_CLASSIFICATIONS:
            findings.append(f"UNREVIEWED_OR_INVALID_CLASSIFICATION:{candidate_id}")
        elif classification == "FORBIDDEN_FREE_LANGUAGE":
            findings.append(f"FORBIDDEN_CANDIDATE_REMAINS:{candidate_id}")
        if len(rationale) < 24:
            findings.append(f"RATIONALE_TOO_SHORT:{candidate_id}")
        if actual.get("reopenOnChange") is not True:
            findings.append(f"REOPEN_ON_CHANGE_REQUIRED:{candidate_id}")
    if payload.get("rawCandidateCount") != discovery["rawCandidateCount"]:
        findings.append("RAW_CANDIDATE_COUNT_DRIFT")
    if payload.get("canonicalCandidateCount") != discovery["canonicalCandidateCount"]:
        findings.append("CANONICAL_CANDIDATE_COUNT_DRIFT")
    expected_hash = ledger_sha256(payload)
    if payload.get("ledgerSha256") != expected_hash:
        findings.append("LEDGER_HASH_MISMATCH")
    return {
        "ok": not findings,
        "status": "LLM_BOUNDARY_LEDGER_VERIFIED" if not findings else "LLM_BOUNDARY_LEDGER_REVIEW_REQUIRED",
        "revision": discovery["sourceRevision"],
        "rawCandidateCount": discovery["rawCandidateCount"],
        "canonicalCandidateCount": discovery["canonicalCandidateCount"],
        "ledgerSha256": expected_hash,
        "findings": findings,
        "mutationPerformed": False,
        "truthNotice": "The ledger classifies static candidates only; it does not claim runtime language understanding or execution success.",
    }


def load_ledger(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ledger root must be a JSON object")
    return payload
