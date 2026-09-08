"""One-shot, revision-bound recovery of the public Sovereign HF shadow dataset."""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from huggingface_hub import HfApi, snapshot_download

from evidence_observatory_publisher import _load_huggingface_runtime_token
from shadow_inference_hf_recovery import (
    build_shadow_recovery_bundle,
    publish_shadow_recovery_bundle,
)

HF_REPO_ID = "Thorsu/sovereign-shadow-inference-bench"
SOURCE_REPOSITORY = "OuroborosCollective/Sovereign-Studio-ato"
GITHUB_API = f"https://api.github.com/repos/{SOURCE_REPOSITORY}"
DATASET_SERVER = "https://datasets-server.huggingface.co"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


def _valid_revision(value: str) -> str:
    revision = str(value or "").strip().lower()
    if not REVISION_RE.fullmatch(revision):
        raise RuntimeError("recovery_revision_invalid")
    return revision


def _github_commit_exists(revision: str) -> bool:
    response = requests.get(
        f"{GITHUB_API}/commits/{revision}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "sovereign-hf-recovery"},
        timeout=20,
    )
    if response.status_code == 200:
        body = response.json()
        return isinstance(body, dict) and str(body.get("sha") or "").lower() == revision
    if response.status_code == 422 or response.status_code == 404:
        return False
    raise RuntimeError(f"github_revision_readback_http_{response.status_code}")


def _hf_commit_exists(api: HfApi, revision: str) -> bool:
    try:
        info = api.repo_info(repo_id=HF_REPO_ID, repo_type="dataset", revision=revision)
    except Exception:
        return False
    return str(getattr(info, "sha", "") or "").lower() == revision


def _load_receipts(snapshot: Path) -> tuple[list[dict], list[str]]:
    receipts: list[dict] = []
    paths: list[str] = []

    receipt_root = snapshot / "data" / "receipts"
    for path in sorted(receipt_root.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"receipt_not_object:{path.name}")
        receipts.append(value)
        paths.append(path.relative_to(snapshot).as_posix())

    seed_path = snapshot / "data" / "shadow_receipts.jsonl"
    if seed_path.is_file():
        for line_number, line in enumerate(seed_path.read_text(encoding="utf-8").splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, dict):
                raise RuntimeError(f"seed_receipt_not_object:{line_number}")
            receipts.append(value)
            paths.append(f"data/shadow_receipts.jsonl#{line_number}")

    if not receipts:
        raise RuntimeError("recovery_no_public_receipts")
    return receipts, paths


def _supersede_old_candidate_section(readme: str, *, candidate_revision: str) -> str:
    replacement = f"""## Historical repository candidate — superseded

The previously published `artifacts/repository-candidate-*` package is retained for audit only. Its published candidate label and the candidate identity carried by the archived patch/bundle were not one causal Git identity, so that package is **not current source, merge, deployment, or runtime truth**.

The current source candidate for this recovery is `{candidate_revision}` and is accepted only after independent GitHub resolution plus revisions-equal deployment readback.
"""
    pattern = re.compile(r"## Reproducible repository candidate\n[\s\S]*?(?=\n## |\Z)")
    if pattern.search(readme):
        return pattern.sub(replacement.rstrip(), readme, count=1)
    return readme.rstrip() + "\n\n" + replacement


def _current_hf_head(api: HfApi) -> str:
    info = api.repo_info(repo_id=HF_REPO_ID, repo_type="dataset", revision="main")
    return _valid_revision(str(getattr(info, "sha", "") or ""))


def _dataset_server_json(path: str, *, params: dict[str, str]) -> tuple[int, dict]:
    response = requests.get(f"{DATASET_SERVER}/{path}", params=params, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {}
    return response.status_code, body if isinstance(body, dict) else {}


def _verify_live_viewer(*, verified_count: int, legacy_count: int, timeout_seconds: int = 300) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        split_status, split_body = _dataset_server_json("splits", params={"dataset": HF_REPO_ID})
        current_status, current_body = _dataset_server_json(
            "first-rows",
            params={"dataset": HF_REPO_ID, "config": "receipts_current", "split": "train"},
        )
        legacy_status, legacy_body = _dataset_server_json(
            "first-rows",
            params={"dataset": HF_REPO_ID, "config": "provenance_legacy", "split": "train"},
        )
        split_names = {
            str(item.get("config") or "")
            for item in (split_body.get("splits") or [])
            if isinstance(item, dict)
        }
        current_rows = current_body.get("rows") if isinstance(current_body.get("rows"), list) else []
        legacy_rows = legacy_body.get("rows") if isinstance(legacy_body.get("rows"), list) else []
        last = {
            "splitStatus": split_status,
            "currentStatus": current_status,
            "legacyStatus": legacy_status,
            "configs": sorted(split_names),
            "currentRows": len(current_rows),
            "legacyRows": len(legacy_rows),
        }
        if (
            split_status == 200
            and current_status == 200
            and "receipts_current" in split_names
            and "receipts" not in split_names
            and len(current_rows) == verified_count
            and (
                (legacy_count == 0 and "provenance_legacy" in split_names)
                or (legacy_count > 0 and legacy_status == 200 and len(legacy_rows) == legacy_count)
            )
        ):
            return last
        time.sleep(10)
    raise RuntimeError("hf_viewer_live_readback_not_ready:" + json.dumps(last, sort_keys=True, separators=(",", ":")))


def recover(*, expected_hf_revision: str, candidate_revision: str, owner_approved: bool) -> dict:
    expected_hf_revision = _valid_revision(expected_hf_revision)
    candidate_revision = _valid_revision(candidate_revision)
    if owner_approved is not True:
        raise RuntimeError("owner_approval_required")

    token = _load_huggingface_runtime_token()
    api = HfApi(token=token)
    observed_hf_head = _current_hf_head(api)
    if observed_hf_head != expected_hf_revision:
        raise RuntimeError("hf_head_changed_before_recovery")
    if not _github_commit_exists(candidate_revision):
        raise RuntimeError("candidate_not_resolved_in_sovereign_github")

    local = Path(snapshot_download(
        repo_id=HF_REPO_ID,
        repo_type="dataset",
        revision=expected_hf_revision,
        token=token,
    ))
    receipts, receipt_paths = _load_receipts(local)
    claimed_revisions = {
        str(receipt.get("sourceRevision") or "").strip().lower()
        for receipt in receipts
        if str(receipt.get("sourceRevision") or "").strip()
    }

    sovereign_revisions = {candidate_revision}
    hf_publication_revisions: set[str] = set()
    unresolved: set[str] = set()
    for revision in sorted(claimed_revisions):
        if not REVISION_RE.fullmatch(revision):
            unresolved.add(revision)
        elif _github_commit_exists(revision):
            sovereign_revisions.add(revision)
        elif _hf_commit_exists(api, revision):
            hf_publication_revisions.add(revision)
        else:
            unresolved.add(revision)

    readme_path = local / "README.md"
    existing_readme = readme_path.read_text(encoding="utf-8") if readme_path.is_file() else "# Sovereign Shadow Inference Bench\n"
    existing_readme = _supersede_old_candidate_section(existing_readme, candidate_revision=candidate_revision)

    bundle = build_shadow_recovery_bundle(
        receipts=receipts,
        receipt_paths=receipt_paths,
        sovereign_revisions=sovereign_revisions,
        hf_publication_revisions=hf_publication_revisions,
        source_repository=SOURCE_REPOSITORY,
        candidate_revision=candidate_revision,
        hf_repo_id=HF_REPO_ID,
        expected_hf_revision=expected_hf_revision,
        existing_readme=existing_readme,
    )

    preflight = {
        "status": "HF_SHADOW_RECOVERY_PREFLIGHT_VERIFIED",
        "canonicalReceiptCount": len(receipts),
        "verifiedViewerReceiptCount": len(bundle["verifiedRows"]),
        "legacyProvenanceCount": len(bundle["supersessions"]),
        "sovereignRevisionCount": len(sovereign_revisions),
        "misboundHfRevisionCount": len(hf_publication_revisions),
        "unresolvedRevisionCount": len(unresolved),
        "candidateRevision": candidate_revision,
        "prewriteHfRevision": expected_hf_revision,
        "canonicalReceiptsMutated": False,
        "secretValuesReturned": False,
    }
    print(json.dumps(preflight, sort_keys=True, separators=(",", ":")))

    published = publish_shadow_recovery_bundle(
        bundle=bundle,
        repo_id=HF_REPO_ID,
        expected_hf_revision=expected_hf_revision,
        owner_approved=True,
    )
    viewer = _verify_live_viewer(
        verified_count=len(bundle["verifiedRows"]),
        legacy_count=len(bundle["supersessions"]),
    )

    result = {
        "status": "HF_SHADOW_RECOVERY_LIVE_VERIFIED",
        "sourceRevision": candidate_revision,
        "hfCommitOid": published["commitOid"],
        "canonicalReceiptCount": len(receipts),
        "verifiedViewerReceiptCount": len(bundle["verifiedRows"]),
        "legacyProvenanceCount": len(bundle["supersessions"]),
        "unresolvedRevisionCount": len(unresolved),
        "viewerReadback": viewer,
        "readbackVerified": published["readbackVerified"] is True,
        "canonicalReceiptsMutated": False,
        "secretValuesReturned": False,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-hf-revision", required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--owner-approved", action="store_true")
    args = parser.parse_args()
    result = recover(
        expected_hf_revision=args.expected_hf_revision,
        candidate_revision=args.candidate_revision,
        owner_approved=args.owner_approved,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
