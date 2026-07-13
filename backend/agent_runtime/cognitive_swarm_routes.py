"""Authenticated Flask routes for the Sovereign cognitive swarm."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from flask import jsonify, request

from .cognitive_swarm_agents import run_cognitive_swarm
from .cognitive_swarm_manifest import manifest_payload


_SECRET_MARKERS = (
    "sk-proj-",
    "github_pat_",
    "ghp_",
    "authorization: bearer",
    "begin openssh private key",
    "begin rsa private key",
)


def _contains_secret_shaped_text(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _allowed_models() -> frozenset[str]:
    configured = os.getenv("SOVEREIGN_AGENTS_ALLOWED_MODELS", "gpt-5.6")
    values = frozenset(item.strip() for item in configured.split(",") if item.strip())
    return values or frozenset({"gpt-5.6"})


def register_cognitive_swarm_routes(app, *, require_session) -> None:
    @app.route("/api/user/agent/swarm/manifest", methods=["GET"])
    @require_session
    def user_get_cognitive_swarm_manifest():
        return jsonify({
            "ok": True,
            "runtime": "openai-agents-sdk",
            "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "allowedModels": sorted(_allowed_models()),
            "manifest": manifest_payload(),
        })

    @app.route("/api/user/agent/swarm/run", methods=["POST"])
    @require_session
    def user_run_cognitive_swarm():
        body: dict[str, Any] = request.get_json(force=True) or {}
        mission = str(body.get("mission") or "").strip()
        evidence = str(body.get("evidence") or body.get("evidenceText") or "").strip()
        model = str(body.get("model") or "").strip() or None

        if not mission:
            return jsonify({"error": "mission is required"}), 400
        if len(mission) > 20_000:
            return jsonify({"error": "mission exceeds the bounded input limit"}), 400
        if len(evidence) > 250_000:
            return jsonify({"error": "evidence exceeds the bounded input limit"}), 400
        if _contains_secret_shaped_text(mission) or _contains_secret_shaped_text(evidence):
            return jsonify({"error": "secret-shaped material is forbidden in swarm input"}), 400
        if model and model not in _allowed_models():
            return jsonify({"error": "model is not allowlisted"}), 400

        try:
            result = asyncio.run(
                run_cognitive_swarm(
                    mission,
                    evidence=evidence,
                    model=model,
                )
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({
                "ok": False,
                "status": "FAILED",
                "runtime": "openai-agents-sdk",
                "error": type(exc).__name__,
            }), 502

        status_code = 200 if result.get("ok") else 503
        return jsonify({"runtime": "openai-agents-sdk", **result}), status_code
