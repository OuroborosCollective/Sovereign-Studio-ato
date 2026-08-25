from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import continuity


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Sovereign continuity policy and append-only completion evidence.")
    parser.add_argument("--base", default="", help="Exact baseline Git revision. Defaults to HEAD.")
    parser.add_argument("--head", default="HEAD", help="Head revision used to calculate the changed path set.")
    parser.add_argument("--repository", default="", help="Repository root. Defaults to the current checkout root.")
    args = parser.parse_args()

    repository = Path(args.repository).resolve() if args.repository else Path(__file__).resolve().parents[2]
    baseline = args.base.strip() or _git(repository, "rev-parse", "HEAD")
    head = args.head.strip() or "HEAD"
    changed_output = _git(repository, "diff", "--name-only", f"{baseline}...{head}")
    changed_paths = [line.strip() for line in changed_output.splitlines() if line.strip()]

    try:
        result = continuity.validate_workspace_completion(
            repository,
            changed_paths,
            baseline_revision=baseline,
        )
    except Exception as exc:
        payload = {
            "ok": True,
            "status": "CONTINUITY_COMPLETION_ADVISORY",
            "advisory": True,
            "blocking": False,
            "failureFamily": type(exc).__name__,
            "message": str(exc),
            "baselineRevision": baseline,
            "headRevision": _git(repository, "rev-parse", head),
            "changedPaths": changed_paths,
            "mutationPerformed": False,
            "secretValuesReturned": False,
            "truthNotice": "Continuity completion is historical provenance only and cannot authorize or block repository, merge, release, deployment or runtime work.",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(json.dumps(
        {
            **result,
            "headRevision": _git(repository, "rev-parse", head),
            "changedPaths": changed_paths,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
