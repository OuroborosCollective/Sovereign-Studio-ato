#!/usr/bin/env python3
"""Generate the checked-in Wolfram CAG quickstart example receipts (#1465).

This stdlib-only generator produces the three complete example receipts that
:file:`docs/WOLFRAM_CAG_QUICKSTART.md` references, by running three public
benchmark cases through the *real* verifier in
:mod:`agent_runtime.wolfram_cag_evidence`:

- ``quickstart-supported.receipt.json``    (cag-bench-001)
- ``quickstart-contradicted.receipt.json`` (cag-bench-002)
- ``quickstart-inconclusive.receipt.json`` (cag-bench-012)

Truth boundary
--------------
The generator uses fixed sentinel identities (``QUICKSTART_RUN_ID``,
``QUICKSTART_REVISION``, empty ``recorded_at``) so regeneration is byte-stable
and never leaks a local machine state into the checked-in artifacts. The
transport receipt of every example is the honest fail-closed ``UNAVAILABLE``
receipt, because real CAG provisioning (#1458) does not exist yet. The
deterministic *comparison* verdict is reported next to it and is never
promoted into the transport receipt. Real runs must bind the actual Git
revision via ``SOVEREIGN_CAG_REVISION`` when calling the benchmark runner;
the checked-in examples deliberately do not.

Usage
-----
    python scripts/generate-wolfram-cag-quickstart-receipts.py            # write
    python scripts/generate-wolfram-cag-quickstart-receipts.py --check    # verify
    python scripts/generate-wolfram-cag-quickstart-receipts.py --list     # show map

``--check`` regenerates every receipt in memory and fails non-zero if any
checked-in file is missing, drifted or fails the secret-value scan. This is
the reproducible docs gate referenced by the quickstart and by the contract
test in ``backend/tests/test_wolfram_cag_quickstart.py``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from agent_runtime.wolfram_cag_benchmark_cases import (  # noqa: E402
    BenchmarkCase,
    case_by_id,
    comparison_verdict,
)
from agent_runtime.wolfram_cag_evidence import (  # noqa: E402
    TRUTH_NOTICE,
    VerificationInput,
    verify_cag_claim,
)

OUTPUT_DIR: Final[Path] = ROOT / "docs" / "examples" / "wolfram-cag"

# Fixed sentinel identities. runtime_revision must be a lowercase full Git SHA
# or empty (see wolfram_cag_evidence._normalize_revision), so the sentinel is
# 40 zero nibbles. recorded_at stays empty so no wall-clock value can enter
# the canonical receipt hash.
QUICKSTART_RUN_ID: Final[str] = "quickstart-example"
QUICKSTART_REVISION: Final[str] = "0" * 40

# case id -> file stem. The stem mirrors the expected comparison verdict so a
# reader can match file name to verdict class without opening the file.
QUICKSTART_EXAMPLES: Final[tuple[tuple[str, str], ...]] = (
    ("cag-bench-001", "quickstart-supported"),
    ("cag-bench-002", "quickstart-contradicted"),
    ("cag-bench-012", "quickstart-inconclusive"),
)

# Secret-shaped value markers, mirroring the benchmark runner's own scan so a
# checked-in example can never carry secret-looking values.
_SECRET_MARKERS: Final[tuple[str, ...]] = (
    "password", "passwd", "token", "authorization",
    "api_key", "apikey", "private_key", "client_secret", "cookie",
    "raw_prompt", "prompt_text", "file_content", "database_row",
)


def _scan_secret_markers(obj: Any) -> list[str]:
    found: list[str] = []

    def _walk(value: Any) -> None:
        if isinstance(value, str):
            folded = value.casefold()
            for marker in _SECRET_MARKERS:
                if marker in folded:
                    found.append(marker)
        elif isinstance(value, dict):
            for item in value.values():
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(obj)
    return found


def build_example_receipt(case: BenchmarkCase) -> dict[str, Any]:
    """Run one case through the real verifier and shape the example payload."""
    receipt = verify_cag_claim(
        VerificationInput(
            claim=case.to_claim(
                sovereign_run_id=QUICKSTART_RUN_ID,
                runtime_revision=QUICKSTART_REVISION,
            ),
            input_text=case.claim_text,
            result=case.to_result(),
            tolerance=case.tolerance,
            recorded_at="",
            transport_receipt=None,
        )
    )
    comparison = comparison_verdict(case)
    if comparison != case.expected_comparison_verdict:
        raise RuntimeError(
            f"{case.case_id}: comparison {comparison} != expected "
            f"{case.expected_comparison_verdict}"
        )
    return {
        "schemaVersion": "sovereign.wolfram-cag-quickstart-example.v1",
        "title": case.title,
        "case_id": case.case_id,
        "component_id": case.component_id,
        "claim_text": case.claim_text,
        "claim_value": case.claim_value,
        "comparison_verdict": comparison,
        "transport_receipt": receipt.to_dict(),
        "transport_verdict": receipt.verdict.value,
        "truth_notice": TRUTH_NOTICE,
        "provisioning_blocker": "#1458 (Wolfram owner provisioning) not available",
    }


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _verify_examples() -> list[str]:
    """Return a list of drift/error descriptions; empty means in sync."""
    problems: list[str] = []
    for case_id, stem in QUICKSTART_EXAMPLES:
        path = OUTPUT_DIR / f"{stem}.receipt.json"
        try:
            case = case_by_id(case_id)
        except KeyError as exc:
            problems.append(f"{case_id}: unknown benchmark case ({exc})")
            continue
        payload = build_example_receipt(case)
        leaked = _scan_secret_markers(payload)
        if leaked:
            problems.append(f"{path.name}: secret markers {sorted(set(leaked))}")
        expected = _render(payload)
        if not path.is_file():
            problems.append(f"{path.name}: missing checked-in file")
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            problems.append(
                f"{path.name}: drifted — run "
                f"`python scripts/generate-wolfram-cag-quickstart-receipts.py`"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the checked-in Wolfram CAG quickstart receipts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the checked-in receipts match a fresh regeneration.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the example map (case id -> file) without writing anything.",
    )
    args = parser.parse_args(argv)

    if args.list:
        for case_id, stem in QUICKSTART_EXAMPLES:
            print(f"{case_id} -> {OUTPUT_DIR / (stem + '.receipt.json')}")
        return 0

    if args.check:
        problems = _verify_examples()
        if problems:
            print("Quickstart example receipts are out of sync:")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        print(f"All {len(QUICKSTART_EXAMPLES)} quickstart receipts are in sync.")
        return 0

    problems = _verify_examples()
    blocking = [p for p in problems if "missing checked-in file" not in p and "drifted" not in p]
    if blocking:
        for problem in blocking:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for case_id, stem in QUICKSTART_EXAMPLES:
        path = OUTPUT_DIR / f"{stem}.receipt.json"
        path.write_text(_render(build_example_receipt(case_by_id(case_id))), encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
