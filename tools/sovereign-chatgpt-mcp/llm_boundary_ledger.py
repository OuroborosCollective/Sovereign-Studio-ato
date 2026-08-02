from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tempfile
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


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Replace one repository artifact atomically while preserving its file mode."""

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _semantic_candidate_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(entry.get("canonicalPath") or ""),
        str(entry.get("symbol") or ""),
        str(entry.get("patternFamily") or ""),
    )


def _anchored_candidate_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (*_semantic_candidate_key(entry), str(entry.get("anchorSha256") or ""))


def _python_symbol_source(repo: Path, entry: dict[str, Any]) -> str:
    path = repo / str(entry.get("canonicalPath") or "")
    text = safe_text(path)
    if text is None or path.suffix != ".py":
        return ""
    symbol = str(entry.get("symbol") or "")
    matches = [item for item in _python_symbols(text) if item[2] == symbol]
    if len(matches) != 1:
        return ""
    start, end, _ = matches[0]
    return "\n".join(text.splitlines()[start - 1 : end])


def _deterministic_classification_suggestion(
    repo: Path,
    entry: dict[str, Any],
) -> tuple[str, str] | None:
    """Return a classification only for a narrowly provable, effect-free SHA guard."""

    source = _python_symbol_source(repo, entry)
    if not source:
        return None
    compact = " ".join(source.split())
    sha_guard = bool(
        "re.fullmatch" in source
        and re.search(r"\\?\[0-9a-f\]\\?\{40\\?\}", source)
        and "raise " in source
        and "return " in source
    )
    forbidden_effect_markers = (
        "requests.",
        "httpx.",
        "subprocess.",
        "broker.call",
        "runtime.",
        ".write_text(",
        ".write_bytes(",
        ".unlink(",
        "dispatch_workflow",
        "rerun_failed",
        "merge_pr",
        "create_draft_pr",
    )
    if not sha_guard or any(marker in compact for marker in forbidden_effect_markers):
        return None
    return (
        "STRUCTURED_POLICY",
        f"{entry.get('symbol')} validates one explicit or environment-provided lowercase Git SHA-40 "
        "and fails closed before configuration; it does not interpret free language, select a route, "
        "or authorize an effect.",
    )


def reconcile_ledger(
    repo: Path,
    payload: dict[str, Any],
    *,
    owner_decisions: dict[str, dict[str, str]] | None = None,
    write_path: Path | None = None,
) -> dict[str, Any]:
    """Reconcile detector drift without reclassifying preserved review decisions.

    Exact candidate IDs are preferred. A unique canonical path/symbol/family/anchor
    match, followed by a unique canonical path/symbol/family match, is treated as
    binding drift so its prior classification and rationale survive line, file-hash,
    or mirror changes. New candidates remain UNREVIEWED unless a narrow deterministic
    rule or an explicit owner decision classifies them.
    """

    discovery = discover_review_candidates(repo)
    prior_entries = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    prior = [entry for entry in prior_entries if isinstance(entry, dict)]
    prior_by_id = {
        str(entry.get("candidateId")): entry
        for entry in prior
        if str(entry.get("candidateId") or "")
    }
    prior_by_semantic: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    prior_by_anchor: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for entry in prior:
        prior_by_semantic.setdefault(_semantic_candidate_key(entry), []).append(entry)
        prior_by_anchor.setdefault(_anchored_candidate_key(entry), []).append(entry)

    decisions = owner_decisions or {}
    used_prior_ids: set[str] = set()
    reconciled_entries: list[dict[str, Any]] = []
    new_candidates: list[dict[str, Any]] = []
    binding_drift: list[dict[str, Any]] = []
    owner_required: list[str] = []
    preserved = 0
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

    for expected in discovery["entries"]:
        candidate_id = str(expected["candidateId"])
        previous = prior_by_id.get(candidate_id)
        previous_id = candidate_id if previous is not None else ""
        if previous is None:
            anchor_matches = [
                item
                for item in prior_by_anchor.get(_anchored_candidate_key(expected), [])
                if str(item.get("candidateId") or "") not in used_prior_ids
            ]
            if len(anchor_matches) == 1:
                previous = anchor_matches[0]
                previous_id = str(previous.get("candidateId") or "")
        if previous is None:
            semantic_matches = [
                item
                for item in prior_by_semantic.get(_semantic_candidate_key(expected), [])
                if str(item.get("candidateId") or "") not in used_prior_ids
            ]
            if len(semantic_matches) == 1:
                previous = semantic_matches[0]
                previous_id = str(previous.get("candidateId") or "")

        if previous is not None:
            used_prior_ids.add(previous_id)
            classification = str(previous.get("classification") or "")
            rationale = str(previous.get("rationale") or "")
            reconciled_entries.append(
                {**expected, "classification": classification, "rationale": rationale}
            )
            changed_fields = [
                field for field in bound_fields if previous.get(field) != expected.get(field)
            ]
            if previous_id != candidate_id:
                changed_fields.insert(0, "candidateId")
            if changed_fields:
                binding_drift.append(
                    {
                        "previousCandidateId": previous_id,
                        "candidateId": candidate_id,
                        "path": expected["canonicalPath"],
                        "symbol": expected["symbol"],
                        "changedFields": changed_fields,
                        "classificationPreserved": classification,
                    }
                )
            preserved += 1
            continue

        decision = decisions.get(candidate_id)
        suggested = _deterministic_classification_suggestion(repo, expected)
        if decision is not None:
            classification = str(decision.get("classification") or "")
            rationale = " ".join(str(decision.get("rationale") or "").split())
            decision_source = "OWNER_DECISION"
        elif suggested is not None:
            classification, rationale = suggested
            decision_source = "DETERMINISTIC_RULE"
        else:
            classification, rationale = "UNREVIEWED", ""
            decision_source = "NONE"

        valid_decision = (
            classification in ALLOWED_CLASSIFICATIONS
            and classification != "FORBIDDEN_FREE_LANGUAGE"
            and len(rationale) >= 24
        )
        requires_owner = not valid_decision
        if requires_owner:
            owner_required.append(candidate_id)
        reconciled_entries.append(
            {**expected, "classification": classification, "rationale": rationale}
        )
        new_candidates.append(
            {
                "candidateId": candidate_id,
                "path": expected["canonicalPath"],
                "mirrorPaths": expected["mirrorPaths"],
                "symbol": expected["symbol"],
                "line": expected["line"],
                "fileSha256": expected["fileSha256"],
                "anchorSha256": expected["anchorSha256"],
                "suggestedClassification": classification if valid_decision else None,
                "suggestionReason": rationale or None,
                "decisionSource": decision_source,
                "ownerDecisionRequired": requires_owner,
            }
        )

    removed = [
        {
            "candidateId": str(entry.get("candidateId") or ""),
            "path": str(entry.get("canonicalPath") or ""),
            "symbol": str(entry.get("symbol") or ""),
            "classification": str(entry.get("classification") or ""),
        }
        for entry in prior
        if str(entry.get("candidateId") or "") not in used_prior_ids
    ]
    removed.sort(key=lambda item: (item["path"], item["symbol"], item["candidateId"]))

    reconciled: dict[str, Any] = {
        "schemaVersion": LEDGER_SCHEMA,
        "detector": str(
            payload.get("detector")
            or "tools/sovereign-chatgpt-mcp/llm_boundary_contract.py"
        ),
        "sourceRevision": discovery["sourceRevision"],
        "rawCandidateCount": discovery["rawCandidateCount"],
        "canonicalCandidateCount": discovery["canonicalCandidateCount"],
        "entries": reconciled_entries,
    }
    reconciled["ledgerSha256"] = ledger_sha256(reconciled)
    validation = validate_ledger(repo, reconciled)
    drift_present = bool(new_candidates or removed or binding_drift)
    can_apply = not owner_required and bool(validation["ok"])
    only_new_structured = bool(new_candidates) and not removed and not binding_drift and all(
        item.get("suggestedClassification") == "STRUCTURED_POLICY"
        and item.get("ownerDecisionRequired") is False
        for item in new_candidates
    )
    mutation_performed = False
    if write_path is not None:
        if not can_apply:
            raise RuntimeError(
                "BOUNDARY_LEDGER_OWNER_REVIEW_REQUIRED: " + ", ".join(owner_required)
            )
        previous_payload = write_path.read_bytes() if write_path.exists() else None
        atomic_write_bytes(
            write_path,
            (json.dumps(reconciled, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        try:
            readback = load_ledger(write_path)
            validation = validate_ledger(repo, readback)
            if not validation["ok"]:
                raise RuntimeError(
                    "BOUNDARY_LEDGER_WRITE_READBACK_FAILED: "
                    + ", ".join(str(item) for item in validation["findings"])
                )
        except Exception:
            if previous_payload is not None:
                atomic_write_bytes(write_path, previous_payload)
            else:
                write_path.unlink(missing_ok=True)
            raise
        mutation_performed = True

    if owner_required:
        status = "RECONCILIATION_REQUIRED"
    elif mutation_performed:
        status = "BOUNDARY_LEDGER_RECONCILED"
    elif drift_present:
        status = "SAFE_RECONCILIATION_READY"
    else:
        status = "BOUNDARY_LEDGER_CURRENT"
    return {
        "schemaVersion": "sovereign.boundary-ledger-reconciliation.v1",
        "ok": bool(validation["ok"]) and not owner_required,
        "status": status,
        "sourceRevision": discovery["sourceRevision"],
        "preservedCandidates": preserved,
        "newCandidates": new_candidates,
        "removedCandidates": removed,
        "bindingDrift": binding_drift,
        "ownerDecisionCandidateIds": owner_required,
        "onlyNewStructuredCandidates": only_new_structured,
        "safeToApply": can_apply,
        "rawCandidateCount": discovery["rawCandidateCount"],
        "canonicalCandidateCount": discovery["canonicalCandidateCount"],
        "previousLedgerSha256": str(payload.get("ledgerSha256") or ""),
        "ledgerSha256": reconciled["ledgerSha256"],
        "ledgerPath": str(write_path.relative_to(repo)) if write_path is not None else None,
        "validation": validation,
        "mutationPerformed": mutation_performed,
        "secretValuesReturned": False,
        "truthNotice": (
            "This reconciliation preserves reviewed classifications and updates static bindings only; "
            "it does not prove runtime language understanding, workflow success, or deployment."
        ),
    }
