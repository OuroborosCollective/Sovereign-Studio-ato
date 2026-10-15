"""Bounded live Observatory/Wolfram capture; optional gated HF staging publish.

No HF Jobs or Sandboxes are created. The runner uses the already provisioned
Thorsu Gradio Space and Sovereign's existing protected Wolfram CAG transport.
It never changes hardware allocations or writes Notion as a runtime source.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evidence_observatory_four_layer import (
    DATASET_ID,
    SPACE_ID,
    FourLayerEvidenceError,
    build_four_layer_public_row,
    build_four_layer_run,
    validate_four_layer_run,
)

# Research references are methodological context only, not verdict witnesses.
RESEARCH_ANCHORS = (
    "https://www.alphaxiv.org/abs/2607.28374",
    "https://www.alphaxiv.org/abs/2608.18312",
    "https://www.alphaxiv.org/abs/2606.18874",
)
HF_STAGING_REVISION = "staging-atlas"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_claim(claim: str) -> tuple[str, int]:
    from evidence_observatory_four_layer import _PRIME
    if not isinstance(claim, str) or len(claim.encode("utf-8")) > 2000:
        raise FourLayerEvidenceError("invalid_live_formal_claim")
    normalized = " ".join(claim.split())
    match = _PRIME.fullmatch(normalized)
    if match is None or len(match.group(1)) > 20:
        raise FourLayerEvidenceError("unsupported_live_formal_claim")
    n = int(match.group(1))
    if n >= 2**64:
        raise FourLayerEvidenceError("live_claim_outside_deterministic_64bit")
    return normalized, n


def _bool_from_wolfram_result(value: Any) -> bool:
    if not isinstance(value, str):
        raise FourLayerEvidenceError("wolfram_cag_result_missing")
    parsed = value.strip()
    if parsed in {"True", "true", '"True"'}:
        return True
    if parsed in {"False", "false", '"False"'}:
        return False
    raise FourLayerEvidenceError("wolfram_cag_result_not_exact_boolean")


def capture_live_four_layer_case(
    *, claim: str, research_anchors: tuple[str, ...] = RESEARCH_ANCHORS,
) -> dict[str, Any]:
    """Perform a real, read-only Space API call and one real Wolfram CAG call.

    The final Space SHA is re-read after both calls; any moving revision,
    unavailable CPU Space, unsigned receipt, missing Wolfram entitlement or
    indeterminate result aborts before publication. Network call failures are
    propagated as failures, never replaced by test fixtures or cached green.
    """
    claim, n = _clean_claim(claim)
    try:
        from huggingface_hub import HfApi, hf_hub_download
        from gradio_client import Client
    except ImportError as exc:
        raise FourLayerEvidenceError("live_space_dependencies_not_installed") from exc
    from agent_runtime.adapters.wolfram_agenttools import (
        WolframCagStatus,
        execute_live_cag_request,
    )

    api = HfApi()
    info = api.space_info(SPACE_ID)
    space_sha = str(getattr(info, "sha", "") or "")
    if len(space_sha) != 40 or any(ch not in "0123456789abcdef" for ch in space_sha):
        raise FourLayerEvidenceError("space_revision_not_immutable_sha")
    runtime = api.get_space_runtime(SPACE_ID)
    stage = getattr(runtime, "stage", None)
    if getattr(stage, "value", stage) != "RUNNING":
        raise FourLayerEvidenceError("space_runtime_not_running")

    path = hf_hub_download(
        repo_id=SPACE_ID, filename="issuer_trust_anchor.json",
        repo_type="space", revision=space_sha,
    )
    public_path = Path(path)
    if public_path.stat().st_size > 4096:
        raise FourLayerEvidenceError("revision_trust_anchor_unbounded")
    anchor = json.loads(public_path.read_text(encoding="utf-8"))
    client = Client(SPACE_ID, verbose=False)
    response = client.predict(claim, api_name="/formal_ui")
    if not isinstance(response, (list, tuple)) or not response or not isinstance(response[0], dict):
        raise FourLayerEvidenceError("space_formal_api_invalid_response")
    receipt = response[0]
    if api.space_info(SPACE_ID).sha != space_sha:
        raise FourLayerEvidenceError("space_revision_changed_during_receipt")

    provider = execute_live_cag_request(
        capability_id="wolfram.cag.compute",
        payload={"code": f"PrimeQ[{n}]", "maxChars": 64, "timeConstraint": 10},
        normalized_result_limit=256,
    )
    status = getattr(provider.status, "value", str(provider.status))
    if status != WolframCagStatus.SUCCEEDED_UNVERIFIED.value:
        raise FourLayerEvidenceError("wolfram_cag_transport_not_successful")
    normalized_result = str(getattr(provider, "normalized_result", "") or "").strip()
    observed = _bool_from_wolfram_result(normalized_result)
    provider_receipt = {
        "component": "WolframLanguageComputation",
        "status": "SUCCEEDED_UNVERIFIED",
        "requestSha256": provider.request_hash,
        "responseSha256": provider.response_hash,
        "normalizedResult": "True" if observed else "False",
        "truthBoundary": "provider_transport_not_semantic_truth",
    }
    capture_time = _now()
    # Use one latest Space identity; a running Space revision may have changed
    # during the paid-independent CAG call, invalidating source provenance.
    last_runtime = api.get_space_runtime(SPACE_ID)
    last_stage = getattr(last_runtime, "stage", None)
    if api.space_info(SPACE_ID).sha != space_sha or getattr(last_stage, "value", last_stage) != "RUNNING":
        raise FourLayerEvidenceError("space_revision_or_stage_changed_during_run")

    wolfram_observation = {
        "source": "Wolfram",
        "tool": "WolframCAG",
        "expression": f"PrimeQ[{n}]",
        "result": observed,
        "observedAt": capture_time,
        "providerReceipt": provider_receipt,
    }
    # observedAt here is the public reference-binding time; arXiv paper content
    # and peer-review status are explicitly not independently re-fetched.
    refs = [{"url": url, "observedAt": capture_time} for url in research_anchors]
    run = build_four_layer_run(
        claim=claim, space_revision=space_sha,
        receipt=receipt, trust_anchor=anchor,
        wolfram_observation=wolfram_observation,
        research_refs=refs, captured_at=capture_time,
    )
    validate_four_layer_run(run)
    row = build_four_layer_public_row(run)
    return {
        "status": "LIVE_SPACE_AND_CAG_CAPTURED",
        "spaceRevision": space_sha,
        "spaceRuntimeStage": "RUNNING",
        "spaceHardware": str(getattr(getattr(runtime, "hardware", None), "value", getattr(runtime, "hardware", "UNKNOWN")) or "UNKNOWN"),
        "run": run,
        "publicRow": row,
        "publicationStatus": "NOT_PUBLISHED",
        "notionStatus": "NOT_INDEXED",
        "runtimeTruthScope": "Space execution/readback and Wolfram CAG transport; no claim of Sovereign backend deployment or arXiv contents verification",
    }


def publish_captured_four_layer_case(capture: dict[str, Any]) -> dict[str, Any]:
    """Staging-only publish through the existing owner/rights/secret readback gate.

    Must be called only after the live capture returned. No unverified record,
    direct main promotion or bypass around the existing Publisher policy.
    """
    if capture.get("status") != "LIVE_SPACE_AND_CAG_CAPTURED":
        raise FourLayerEvidenceError("publication_requires_live_space_and_cag_capture")
    run = capture.get("run")
    if not isinstance(run, dict) or not validate_four_layer_run(run):
        raise FourLayerEvidenceError("publication_run_invalid")
    row = build_four_layer_public_row(run)
    if row != capture.get("publicRow"):
        raise FourLayerEvidenceError("publication_case_drift")
    from evidence_observatory_publisher import publish_huggingface_batch
    outcome = publish_huggingface_batch(
        rows=[row],
        repo_id=DATASET_ID,
        revision=HF_STAGING_REVISION,
    )
    return {
        "status": outcome.get("status"),
        "runBundleSha256": run["bundleSha256"],
        "readbackVerified": outcome.get("readbackVerified") is True,
        "repoId": outcome.get("repoId"),
        "revision": outcome.get("revision"),
        "commitOid": outcome.get("commitOid"),
        "batchId": outcome.get("batchId"),
        "batchSha256": outcome.get("batchSha256"),
        "dataSha256": outcome.get("dataSha256"),
        "manifestSha256": outcome.get("manifestSha256"),
        "publicationReceiptSha256": outcome.get("publicationReceiptSha256"),
        "truthBoundary": "HF target readback is not proof of general semantic truth or Notion indexing",
    }


def notion_evidence_index(capture: dict[str, Any], publication: dict[str, Any] | None = None) -> dict[str, Any]:
    """A secret-free Notion projection. The connector performs actual writes."""
    if capture.get("status") != "LIVE_SPACE_AND_CAG_CAPTURED":
        raise FourLayerEvidenceError("notion_projection_requires_live_capture")
    run = capture.get("run")
    if not isinstance(run, dict) or not validate_four_layer_run(run):
        raise FourLayerEvidenceError("notion_projection_run_invalid")
    published = bool(
        publication is not None
        and publication.get("status") == "PUBLISHED_VERIFIED"
        and publication.get("readbackVerified") is True
        and publication.get("repoId") == DATASET_ID
        and publication.get("revision") == HF_STAGING_REVISION
        and publication.get("runBundleSha256") == run["bundleSha256"]
        and re.fullmatch(r"[0-9a-f]{40}", str(publication.get("commitOid") or "")) is not None
    )
    return {
        "runId": run["runId"],
        "claim": run["claim"],
        "verdict": run["verdict"],
        "space": SPACE_ID,
        "spaceRevision": run["spaceRevision"],
        "signedReceiptSha256": run["receiptSha256"],
        "bundleSha256": run["bundleSha256"],
        "wolframObservationSha256": run["wolfram"]["normalizedObservationSha256"],
        "wolframTransportStatus": run["wolfram"].get("providerReceipt", {}).get("status", "UNVERIFIED"),
        "researchContextUrls": [ref["url"] for ref in run["research"]],
        "publicationStatus": "HF_PUBLISHED_VERIFIED" if published else "NOT_HF_PUBLISHED_VERIFIED",
        "hfCommitOid": publication.get("commitOid") if published else None,
        "hfRepo": DATASET_ID,
        "hfRevision": HF_STAGING_REVISION,
        "truthBoundary": run["truthBoundary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only live Space/Wolfram evidence run; gated staging publication")
    parser.add_argument("--claim", required=True, help="Bounded expression like '173 is prime'")
    parser.add_argument("--publish-staging", action="store_true", help="Requires existing owner-managed HF rights and credential gates")
    args = parser.parse_args(argv)
    try:
        capture = capture_live_four_layer_case(claim=args.claim)
        publication = publish_captured_four_layer_case(capture) if args.publish_staging else None
        output = {
            "captureStatus": capture["status"],
            "spaceRevision": capture["spaceRevision"],
            "runId": capture["run"]["runId"],
            "bundleSha256": capture["run"]["bundleSha256"],
            "publish": publication,
            "notionIndex": notion_evidence_index(capture, publication),
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
        return 0 if not args.publish_staging or (
            publication is not None and publication.get("status") == "PUBLISHED_VERIFIED"
            and publication.get("readbackVerified")
        ) else 2
    except Exception as exc:
        # Return an error class only. Never print credential-bearing provider
        # exception bodies, response payloads, or raw account path material.
        print(json.dumps({"ok": False, "status": "FAIL_CLOSED", "errorClass": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
