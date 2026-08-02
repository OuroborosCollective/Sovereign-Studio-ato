#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = ROOT / "tools" / "sovereign-chatgpt-mcp"
sys.path.insert(0, str(MCP_ROOT))

from ci_repair_tools import (  # noqa: E402
    DEFAULT_LEDGER_RELATIVE,
    append_boundary_reconciliation_continuity,
)
from llm_boundary_ledger import load_ledger, reconcile_ledger  # noqa: E402


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    ).stdout.strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview or apply a classification-preserving LLM boundary-ledger reconciliation."
    )
    parser.add_argument("--ledger", default=DEFAULT_LEDGER_RELATIVE)
    parser.add_argument("--expected-head", default="")
    parser.add_argument("--owner-decisions", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--append-continuity", action="store_true")
    args = parser.parse_args()

    head = _head()
    expected = str(args.expected_head or "").strip().lower()
    if expected and expected != head:
        raise SystemExit(f"EXPECTED_HEAD_MISMATCH: expected {expected}, actual {head}")
    ledger_path = (ROOT / args.ledger).resolve()
    if ROOT.resolve() not in ledger_path.parents:
        raise SystemExit("LEDGER_PATH_OUTSIDE_REPOSITORY")
    owner_decisions: dict[str, dict[str, str]] = {}
    if args.owner_decisions:
        decision_path = (ROOT / args.owner_decisions).resolve()
        if ROOT.resolve() not in decision_path.parents:
            raise SystemExit("OWNER_DECISIONS_PATH_OUTSIDE_REPOSITORY")
        payload = json.loads(decision_path.read_text("utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("OWNER_DECISIONS_MUST_BE_AN_OBJECT")
        owner_decisions = payload

    preview = reconcile_ledger(
        ROOT,
        load_ledger(ledger_path),
        owner_decisions=owner_decisions,
    )
    result = preview
    if args.write:
        if preview["ownerDecisionCandidateIds"]:
            result = preview
        else:
            result = reconcile_ledger(
                ROOT,
                load_ledger(ledger_path),
                owner_decisions=owner_decisions,
                write_path=ledger_path,
            )
            if args.append_continuity:
                result = {
                    **result,
                    "continuity": append_boundary_reconciliation_continuity(
                        ROOT,
                        source_revision=head,
                        reconciliation=result,
                    ),
                }

    serialized = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        report_path = (ROOT / args.report).resolve()
        if ROOT.resolve() not in report_path.parents:
            raise SystemExit("REPORT_PATH_OUTSIDE_REPOSITORY")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(serialized, "utf-8")
    print(serialized, end="")
    if result.get("ownerDecisionCandidateIds"):
        return 3
    if args.write:
        return 0 if result.get("status") == "BOUNDARY_LEDGER_RECONCILED" else 1
    drift = bool(result.get("newCandidates") or result.get("removedCandidates") or result.get("bindingDrift"))
    return 2 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
