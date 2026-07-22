"""Build isolated OpenAI Agents SDK RunConfig objects for direct LLM routes."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from llm_transport import (
    FREELLM_TRANSPORT,
    OPENROUTER_TRANSPORT,
    route_api_base,
    route_config,
    route_is_direct_freellm,
    route_is_openrouter_paid,
    route_provider_model,
    route_transport,
)

_KEY_MAX_BYTES: Final[int] = 8192
_SAFE_KEY_MIN_BYTES: Final[int] = 16
_OPENROUTER_KEY_FILENAME: Final[str] = "openrouter_api_key.txt"
_FREELLM_KEY_FILENAME: Final[str] = "freellmapi_unified_key.txt"


class RouteRuntimeError(RuntimeError):
    """Typed failure that never contains key material or raw provider responses."""

    def __init__(self, family: str, next_action: str) -> None:
        super().__init__(family)
        self.family = str(family)[:160]
        self.next_action = str(next_action)[:240]


@dataclass(frozen=True, slots=True)
class RouteRunConfig:
    model: str
    transport: str
    run_config: Any


def _key_spec(transport: str) -> tuple[str, str]:
    if transport == OPENROUTER_TRANSPORT:
        return "SOVEREIGN_OPENROUTER_API_KEY_FILE", _OPENROUTER_KEY_FILENAME
    if transport == FREELLM_TRANSPORT:
        return "SOVEREIGN_FREELLMAPI_UNIFIED_KEY_FILE", _FREELLM_KEY_FILENAME
    raise RouteRuntimeError("UNSUPPORTED_LLM_TRANSPORT", "SELECT_OPENROUTER_OR_FREELLM_ROUTE")


def _read_protected_key(transport: str) -> str:
    env_name, filename = _key_spec(transport)
    expected_root = Path(
        os.getenv("SOVEREIGN_OWNER_INPUT_ROOT", "/opt/sovereign-owner-managed")
    ).resolve()
    configured = os.getenv(env_name, str(expected_root / filename)).strip()
    candidate_path = Path(configured)
    if candidate_path.is_symlink():
        raise RouteRuntimeError(
            f"{transport.upper()}_KEY_FILE_REJECTED",
            f"VERIFY_{transport.upper()}_PROTECTED_KEY_FILE",
        )
    candidate = candidate_path.resolve()
    if (
        candidate.parent != expected_root
        or candidate.name != filename
        or not candidate.is_file()
    ):
        raise RouteRuntimeError(
            f"{transport.upper()}_KEY_FILE_MISSING",
            f"PROVIDE_{transport.upper()}_PROTECTED_KEY",
        )
    protected = bytearray()
    try:
        try:
            if candidate.stat().st_mode & 0o077:
                raise RouteRuntimeError(
                    f"{transport.upper()}_KEY_FILE_PERMISSIONS_INVALID",
                    f"CHMOD_600_{transport.upper()}_KEY_FILE",
                )
            protected = bytearray(candidate.read_bytes())
        except RouteRuntimeError:
            raise
        except OSError as exc:
            raise RouteRuntimeError(
                f"{transport.upper()}_KEY_FILE_UNREADABLE",
                f"VERIFY_{transport.upper()}_PROTECTED_KEY_FILE",
            ) from exc
        if not (_SAFE_KEY_MIN_BYTES <= len(protected) <= _KEY_MAX_BYTES):
            raise RouteRuntimeError(
                f"{transport.upper()}_KEY_VALUE_INVALID",
                f"REPLACE_{transport.upper()}_PROTECTED_KEY",
            )
        try:
            value = protected.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise RouteRuntimeError(
                f"{transport.upper()}_KEY_VALUE_INVALID",
                f"REPLACE_{transport.upper()}_PROTECTED_KEY",
            ) from exc
        if len(value) < _SAFE_KEY_MIN_BYTES or any(
            marker in value for marker in ("\x00", "\n", "\r")
        ):
            raise RouteRuntimeError(
                f"{transport.upper()}_KEY_VALUE_INVALID",
                f"REPLACE_{transport.upper()}_PROTECTED_KEY",
            )
        return value
    finally:
        for index in range(len(protected)):
            protected[index] = 0


def _openrouter_policy(route: dict[str, Any]) -> dict[str, Any]:
    policy = route_config(route).get("providerPolicy")
    if not isinstance(policy, dict):
        raise RouteRuntimeError(
            "OPENROUTER_PROVIDER_POLICY_MISSING",
            "CONFIGURE_OPENROUTER_PROVIDER_POLICY",
        )
    required = {
        "require_parameters": True,
        "allow_fallbacks": False,
        "data_collection": "deny",
    }
    if any(policy.get(key) != value for key, value in required.items()):
        raise RouteRuntimeError(
            "OPENROUTER_PROVIDER_POLICY_REJECTED",
            "CONFIGURE_OPENROUTER_PROVIDER_POLICY",
        )
    return dict(required)


def build_route_run_config(
    route: dict[str, Any],
    *,
    output_token_limit: int,
) -> RouteRunConfig:
    """Return one request-local SDK config for an exact persisted route."""

    transport = route_transport(route)
    if transport == OPENROUTER_TRANSPORT:
        if not route_is_openrouter_paid(route):
            raise RouteRuntimeError(
                "OPENROUTER_PAID_ROUTE_REJECTED",
                "ACTIVATE_VERIFIED_OPENROUTER_PAID_ROUTE",
            )
        extra_body: dict[str, Any] | None = {
            "provider": _openrouter_policy(route),
        }
    elif transport == FREELLM_TRANSPORT:
        if not route_is_direct_freellm(route):
            raise RouteRuntimeError(
                "FREELLM_DIRECT_ROUTE_REJECTED",
                "ACTIVATE_VERIFIED_DIRECT_FREELLM_ROUTE",
            )
        extra_body = None
    else:
        raise RouteRuntimeError(
            "UNSUPPORTED_LLM_TRANSPORT",
            "SELECT_OPENROUTER_OR_FREELLM_ROUTE",
        )

    model = route_provider_model(route)
    if not model or len(model) > 200:
        raise RouteRuntimeError(
            f"{transport.upper()}_MODEL_INVALID",
            f"VERIFY_{transport.upper()}_PROVIDER_MODEL",
        )
    api_key = _read_protected_key(transport)
    try:
        provider_module = importlib.import_module("agents.models.openai_provider")
        provider_class = getattr(provider_module, "OpenAIProvider")
        run_config_module = importlib.import_module("agents.run_config")
        run_config_class = getattr(run_config_module, "RunConfig")
        model_settings_module = importlib.import_module("agents.model_settings")
        model_settings_class = getattr(model_settings_module, "ModelSettings")
    except (AttributeError, ImportError) as exc:
        raise RouteRuntimeError(
            "AGENTS_SDK_PROVIDER_API_UNAVAILABLE",
            "VERIFY_PINNED_OPENAI_AGENTS_SDK",
        ) from exc

    try:
        provider = provider_class(
            api_key=api_key,
            base_url=route_api_base(route),
            use_responses=False,
        )
        settings_kwargs: dict[str, Any] = {
            "max_tokens": int(output_token_limit),
            "include_usage": True,
        }
        if extra_body is not None:
            settings_kwargs["extra_body"] = extra_body
        model_settings = model_settings_class(**settings_kwargs)
        run_config = run_config_class(
            model=model,
            model_provider=provider,
            model_settings=model_settings,
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
    except (TypeError, ValueError) as exc:
        raise RouteRuntimeError(
            f"{transport.upper()}_SDK_CONFIGURATION_REJECTED",
            "VERIFY_OPENAI_AGENTS_SDK_ROUTE_CONTRACT",
        ) from exc
    return RouteRunConfig(
        model=model,
        transport=transport,
        run_config=run_config,
    )
