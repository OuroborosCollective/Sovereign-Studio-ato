from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from flask import jsonify, request

from .manifest import SkillContractError, parse_manifest
from .progressive_loader import ProgressiveLoadError, load_references
from .resolver import CandidateStatus, resolve_candidate

RevisionResolver = Callable[[], str]


def _runtime_revision() -> str:
    return str(
        os.getenv("SOVEREIGN_SOURCE_REVISION")
        or os.getenv("SOURCE_REVISION")
        or os.getenv("GIT_SHA")
        or ""
    ).strip().lower()


def register_progressive_skill_routes(
    app,
    *,
    require_session,
    repository_root: Path,
    revision_resolver: RevisionResolver = _runtime_revision,
) -> None:
    """Extend the existing agent API with read-only skill resolution.

    The route selects a candidate and progressively reads only declared,
    hash-bound repository references. It never authorizes or performs effects.
    """

    @app.route("/api/user/agent/skills/resolve", methods=["POST"])
    @require_session
    def user_resolve_progressive_skill():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"ok": False, "blocker": "json_object_required"}), 400
        try:
            manifest = parse_manifest(body.get("manifest"))
            request_text = str(body.get("requestText") or "").strip()
            staged = body.get("stagedCapabilities")
            if not request_text or not isinstance(staged, list):
                return jsonify({"ok": False, "blocker": "request_and_capabilities_required"}), 400
            decision = resolve_candidate(
                manifest,
                request_text=request_text,
                staged_capabilities=[str(item) for item in staged],
                context_trust=str(body.get("contextTrust") or "untrusted"),
                owner_policy_hash=str(body.get("ownerPolicyHash") or ""),
            )
            response = {
                "ok": decision.status is CandidateStatus.SELECTED,
                "runtime": "sovereign-agent",
                "schemaVersion": "sovereign-skill-resolution.v1",
                "summary": manifest.summary(),
                "decision": {
                    "status": decision.status.value,
                    "score": decision.score,
                    "matchedTriggers": list(decision.matched_triggers),
                    "matchedAntiTriggers": list(decision.matched_anti_triggers),
                    "missingCapabilities": list(decision.missing_capabilities),
                    "reasons": list(decision.reasons),
                },
                "loadedReferences": [],
                "truthNotice": "Skill selection does not authorize a capability, permission, workspace mutation or external effect.",
            }
            if decision.status is not CandidateStatus.SELECTED:
                return jsonify(response), 409

            expected_revision = str(body.get("repositoryRevision") or "").strip().lower()
            runtime_revision = revision_resolver()
            if not expected_revision or runtime_revision != expected_revision:
                response["ok"] = False
                response["decision"]["status"] = "BLOCKED_REVISION_MISMATCH"
                response["decision"]["reasons"] = ["deployed repository revision is not attested or does not match"]
                return jsonify(response), 409

            root = repository_root.resolve()

            def read_bound(path: str, revision: str) -> bytes:
                if revision != runtime_revision:
                    raise ProgressiveLoadError("reference revision mismatch")
                candidate = (root / path).resolve()
                if root not in candidate.parents and candidate != root:
                    raise ProgressiveLoadError("reference escaped repository root")
                return candidate.read_bytes()

            loaded = load_references(
                manifest,
                repository_revision=expected_revision,
                owner=str(body.get("owner") or "OuroborosCollective"),
                trust_class=str(body.get("contextTrust") or "untrusted"),
                truth_boundary=str(body.get("truthBoundary") or "repository-reference-only"),
                workflow_step=str(body.get("workflowStep") or "skill-resolve"),
                load_reason=str(body.get("loadReason") or "deterministic-candidate-selection"),
                read_bound_content=read_bound,
                matched=True,
                explicit_paths=[str(item) for item in body.get("explicitPaths", [])]
                if isinstance(body.get("explicitPaths"), list)
                else (),
            )
            response["loadedReferences"] = [
                {
                    "repositoryRevision": item.repository_revision,
                    "path": item.path,
                    "declaredBlobHash": item.declared_blob_hash,
                    "observedSha256": item.observed_sha256,
                    "owner": item.owner,
                    "trustClass": item.trust_class,
                    "truthBoundary": item.truth_boundary,
                    "skillId": item.skill_id,
                    "manifestHash": item.manifest_hash,
                    "workflowStep": item.workflow_step,
                    "loadReason": item.load_reason,
                    "content": item.content,
                }
                for item in loaded
            ]
            return jsonify(response), 200
        except (SkillContractError, ProgressiveLoadError, ValueError, OSError) as exc:
            return jsonify({
                "ok": False,
                "runtime": "sovereign-agent",
                "blocker": "progressive_skill_resolution_rejected",
                "error": str(exc)[:500],
            }), 400
