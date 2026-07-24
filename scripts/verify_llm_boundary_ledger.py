#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "sovereign-chatgpt-mcp"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from llm_boundary_ledger import generate_unreviewed_ledger, load_ledger, validate_ledger

DEFAULT_LEDGER = ROOT / "config" / "architecture" / "llm-tool-boundary-review-ledger.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the SHA-bound LLM/tool-boundary review ledger."
    )
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument(
        "--generate-unreviewed",
        action="store_true",
        help="Write the current candidate set with UNREVIEWED classifications for human review.",
    )
    args = parser.parse_args()
    ledger_path = args.ledger if args.ledger.is_absolute() else ROOT / args.ledger

    if args.generate_unreviewed:
        payload = generate_unreviewed_ledger(ROOT)
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": "LLM_BOUNDARY_LEDGER_GENERATED_UNREVIEWED",
                    "path": str(ledger_path.relative_to(ROOT)),
                    "rawCandidateCount": payload["rawCandidateCount"],
                    "canonicalCandidateCount": payload["canonicalCandidateCount"],
                    "ledgerSha256": payload["ledgerSha256"],
                },
                sort_keys=True,
            )
        )
        return 0

    if not ledger_path.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "status": "LLM_BOUNDARY_LEDGER_MISSING",
                    "path": str(ledger_path),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    result = validate_ledger(ROOT, load_ledger(ledger_path))
    stream = sys.stdout if result["ok"] else sys.stderr
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), file=stream)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
