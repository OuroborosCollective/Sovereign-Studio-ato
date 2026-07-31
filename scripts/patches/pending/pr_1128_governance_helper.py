#!/usr/bin/env python3
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PATCHES_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PATCHES_DIR))
from search_replace_runner import GitHubApi, SHA_RE, fail, read_file, update_file  # noqa: E402


def _load_request(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        fail("helper request must be an object")
    return payload


def _refresh_llm_ledger(request: dict) -> None:
    repo_name = os.environ.get("REPO_FULL_NAME", "OuroborosCollective/Sovereign-Studio-ato")
    source_ref = str(request.get("source_ref") or "").strip()
    analysis_revision = str(request.get("analysis_revision") or "").strip().lower()
    ledger_target = str(request.get("ledger_target") or "").strip()
    test_target = str(request.get("test_target") or "").strip()
    reviews = request.get("candidate_reviews")
    message = str(request.get("commit_message") or "chore: refresh LLM boundary review ledger")
    if not source_ref or not SHA_RE.fullmatch(analysis_revision) or not ledger_target or not test_target:
        fail("refresh request identity is incomplete")
    if not isinstance(reviews, dict) or not reviews:
        fail("candidate_reviews must be a non-empty object")

    api = GitHubApi(repo_name, os.environ.get("GITHUB_TOKEN", ""))
    subprocess.run(["git", "fetch", "--no-tags", "origin", analysis_revision], check=True, timeout=90)
    temp_parent = Path(tempfile.mkdtemp(prefix="sovereign-llm-ledger-"))
    worktree = temp_parent / "repo"
    subprocess.run(["git", "worktree", "add", "--detach", str(worktree), analysis_revision], check=True, timeout=90)
    try:
        sys.path.insert(0, str(worktree / "tools" / "sovereign-chatgpt-mcp"))
        ledger_module = importlib.import_module("llm_boundary_ledger")
        test_path = worktree / test_target
        test_text = test_path.read_text(encoding="utf-8")
        discovery = ledger_module.discover_review_candidates(worktree)
        for _ in range(4):
            updated = re.sub(
                r'assert result\["rawCandidateCount"\] == \d+',
                f'assert result["rawCandidateCount"] == {discovery["rawCandidateCount"]}',
                test_text,
            )
            updated = re.sub(
                r'assert result\["canonicalCandidateCount"\] == \d+',
                f'assert result["canonicalCandidateCount"] == {discovery["canonicalCandidateCount"]}',
                updated,
            )
            if updated != test_text:
                test_text = updated
                test_path.write_text(test_text, encoding="utf-8")
            next_discovery = ledger_module.discover_review_candidates(worktree)
            stable = (
                next_discovery["rawCandidateCount"] == discovery["rawCandidateCount"]
                and next_discovery["canonicalCandidateCount"] == discovery["canonicalCandidateCount"]
            )
            discovery = next_discovery
            if stable:
                break
        else:
            fail("candidate counts did not stabilize")

        _, ledger_text = read_file(api, ledger_target, source_ref)
        existing = json.loads(ledger_text)
        old_entries = existing.get("entries") or []
        old_by_id = {
            str(item.get("candidateId") or ""): item
            for item in old_entries
            if isinstance(item, dict)
        }
        old_by_identity = {
            (
                str(item.get("canonicalPath") or ""),
                str(item.get("symbol") or ""),
                int(item.get("line") or 0),
                str(item.get("patternFamily") or ""),
            ): item
            for item in old_entries
            if isinstance(item, dict)
        }
        used_old_ids: set[str] = set()
        observed_new: set[str] = set()
        entries: list[dict] = []
        for discovered in discovery["entries"]:
            candidate_id = str(discovered["candidateId"])
            prior = old_by_id.get(candidate_id)
            if prior is None:
                identity = (
                    str(discovered["canonicalPath"]),
                    str(discovered["symbol"]),
                    int(discovered["line"]),
                    str(discovered["patternFamily"]),
                )
                prior = old_by_identity.get(identity)
            if prior is not None:
                used_old_ids.add(str(prior.get("candidateId") or ""))
                classification = str(prior.get("classification") or "")
                rationale = str(prior.get("rationale") or "")
            else:
                review = reviews.get(candidate_id)
                if not isinstance(review, dict):
                    fail(f"unreviewed new candidate: {candidate_id}")
                classification = str(review.get("classification") or "")
                rationale = str(review.get("rationale") or "")
                observed_new.add(candidate_id)
            entries.append({**discovered, "classification": classification, "rationale": rationale})

        stale = sorted(set(old_by_id) - used_old_ids)
        if stale:
            fail(f"stale existing candidates: {stale}")
        if observed_new != set(reviews):
            fail(f"new candidate mismatch: expected={sorted(reviews)} observed={sorted(observed_new)}")

        payload = {
            "schemaVersion": ledger_module.LEDGER_SCHEMA,
            "detector": str(existing.get("detector") or "tools/sovereign-chatgpt-mcp/llm_boundary_contract.py"),
            "sourceRevision": analysis_revision,
            "rawCandidateCount": discovery["rawCandidateCount"],
            "canonicalCandidateCount": discovery["canonicalCandidateCount"],
            "entries": entries,
        }
        payload["ledgerSha256"] = ledger_module.ledger_sha256(payload)
        validation = ledger_module.validate_ledger(worktree, payload)
        if validation.get("ok") is not True:
            fail(f"refreshed ledger validation failed: {validation}")

        ledger_sha, _ = read_file(api, ledger_target, source_ref)
        ledger_commit = update_file(
            api,
            source_ref,
            ledger_target,
            ledger_sha,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            message,
        )
        test_sha, branch_test = read_file(api, test_target, source_ref)
        branch_test = re.sub(
            r'assert result\["rawCandidateCount"\] == \d+',
            f'assert result["rawCandidateCount"] == {discovery["rawCandidateCount"]}',
            branch_test,
            count=1,
        )
        branch_test = re.sub(
            r'assert result\["canonicalCandidateCount"\] == \d+',
            f'assert result["canonicalCandidateCount"] == {discovery["canonicalCandidateCount"]}',
            branch_test,
            count=1,
        )
        test_commit = update_file(api, source_ref, test_target, test_sha, branch_test, message)
        print(json.dumps({
            "status": "LLM_BOUNDARY_LEDGER_REFRESHED",
            "analysisRevision": analysis_revision,
            "rawCandidateCount": discovery["rawCandidateCount"],
            "canonicalCandidateCount": discovery["canonicalCandidateCount"],
            "newCandidateIds": sorted(observed_new),
            "ledgerSha256": payload["ledgerSha256"],
            "ledgerCommit": ledger_commit,
            "testCommit": test_commit,
        }, sort_keys=True))
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], check=False, timeout=90)
        shutil.rmtree(temp_parent, ignore_errors=True)


def _append_continuity(request: dict) -> None:
    repo_name = os.environ.get("REPO_FULL_NAME", "OuroborosCollective/Sovereign-Studio-ato")
    source_ref = str(request.get("source_ref") or "").strip()
    baseline_ref = str(request.get("baseline_ref") or "").strip()
    target = str(request.get("target") or "").strip()
    entry = str(request.get("entry") or "").rstrip("\r\n")
    message = str(request.get("commit_message") or "chore(continuity): exact append")
    if not source_ref or not baseline_ref or not target or not entry:
        fail("continuity append request is incomplete")
    parsed = json.loads(entry)
    if not isinstance(parsed, dict):
        fail("continuity entry must be an object")
    api = GitHubApi(repo_name, os.environ.get("GITHUB_TOKEN", ""))
    current_sha, _ = read_file(api, target, source_ref)
    _, baseline = read_file(api, target, baseline_ref)
    separator = "" if baseline.endswith("\n") else "\n"
    after = baseline + separator + entry + "\n"
    if not after.startswith(baseline):
        fail("exact continuity prefix was not preserved")
    commit_sha = update_file(api, source_ref, target, current_sha, after, message)
    print(json.dumps({"status": "EXACT_CONTINUITY_APPEND_COMPLETE", "target": target, "commit": commit_sha}, sort_keys=True))


def main() -> None:
    if len(sys.argv) != 2:
        fail("helper expects one request JSON")
    request = _load_request(sys.argv[1])
    operation = str(request.get("operation") or "")
    if operation == "refresh_llm_boundary_ledger":
        _refresh_llm_ledger(request)
    elif operation == "append_continuity":
        _append_continuity(request)
    else:
        fail(f"unsupported helper operation: {operation}")


if __name__ == "__main__":
    main()
