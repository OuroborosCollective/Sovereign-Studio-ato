#!/usr/bin/env python3
"""Fail-closed environment validator for the isolated desktop worker template."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ATTEMPT_RE = re.compile(r"^attempt-[0-9a-f]{24}$")
ADMISSION_RE = re.compile(r"^desktop-admission-[0-9a-f]{24}$")
SESSION_RE = re.compile(r"^[a-z0-9._:-]{1,160}$")
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$")


def fail(message: str) -> None:
    print(f"desktop-worker configuration rejected: {message}", file=sys.stderr)
    raise SystemExit(2)


def required(name: str) -> str:
    value = os.environ.get(name, "").strip().lower()
    if not value:
        fail(f"{name} is required")
    return value


def required_path(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        fail(f"{name} is required")
    return value


def require_hash(name: str) -> None:
    if not HASH_RE.fullmatch(required(name)):
        fail(f"{name} must be a sha256 hash")


def require_revision(name: str) -> None:
    if not REVISION_RE.fullmatch(required(name)):
        fail(f"{name} must be an exact revision")


def require_identifier(name: str, pattern: re.Pattern[str]) -> None:
    if not pattern.fullmatch(required(name)):
        fail(f"{name} is invalid")


def _command_output(arguments: list[str], *, purpose: str) -> str:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        fail(f"{purpose} readback is unavailable")
    if result.returncode != 0:
        fail(f"{purpose} readback was rejected")
    return result.stdout.strip().lower()


def _normalise_image_digest(name: str) -> str:
    value = required(name)
    if value.startswith("sha256:"):
        value = value.removeprefix("sha256:")
    if not HASH_RE.fullmatch(value):
        fail(f"{name} must be a local image digest")
    return "sha256:" + value


def _repo_digests(readback_ref: str) -> tuple[str, ...]:
    raw = _command_output(
        ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", readback_ref],
        purpose="worker repository digest",
    )
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        fail("worker repository digest readback is invalid")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        fail("worker repository digest readback is invalid")
    return tuple(value.strip().lower() for value in values)


def validate_worker(*, local_canary_only: bool) -> tuple[str, str]:
    worker_image = required("DESKTOP_WORKER_IMAGE")
    if not IMAGE_RE.fullmatch(worker_image):
        fail("DESKTOP_WORKER_IMAGE must be a repository digest reference")
    image_digest = _normalise_image_digest("DESKTOP_IMAGE_DIGEST")
    require_identifier("DESKTOP_SESSION_ID", SESSION_RE)
    for name in (
        "DESKTOP_SESSION_BINDING_HASH",
        "DESKTOP_RUNTIME_IDENTITY_HASH",
        "DESKTOP_CONTAINER_IDENTITY_HASH",
        "DESKTOP_INPUT_SCOPE_HASH",
        "DESKTOP_VIEW_SCOPE_HASH",
        "DESKTOP_ATTEMPT_HASH",
        "DESKTOP_WORKTREE_IDENTITY_HASH",
    ):
        require_hash(name)
    if required("DESKTOP_INPUT_SCOPE_HASH") == required("DESKTOP_VIEW_SCOPE_HASH"):
        fail("view and input scope hashes must differ")
    require_identifier("DESKTOP_ATTEMPT_ID", ATTEMPT_RE)
    expected_revision = required("DESKTOP_HEAD_REVISION")
    require_revision("DESKTOP_HEAD_REVISION")
    admission = os.environ.get("DESKTOP_ADMISSION_ID", "").strip().lower()
    if admission and not ADMISSION_RE.fullmatch(admission):
        fail("DESKTOP_ADMISSION_ID is invalid")
    raw_workspace = Path(required_path("ATTEMPT_WORKTREE"))
    if not raw_workspace.is_absolute():
        fail("ATTEMPT_WORKTREE must be an absolute bounded directory")
    workspace = raw_workspace.resolve()
    if workspace == Path("/") or not workspace.is_dir() or ".." in workspace.parts:
        fail("ATTEMPT_WORKTREE must be an existing bounded directory")
    if not (workspace / ".git").is_dir():
        fail("ATTEMPT_WORKTREE must be a self-contained revision checkout")
    if _command_output(["git", "-C", str(workspace), "rev-parse", "--verify", "HEAD"], purpose="attempt revision") != expected_revision:
        fail("ATTEMPT_WORKTREE revision must equal DESKTOP_HEAD_REVISION")
    if _command_output(["git", "-C", str(workspace), "remote"], purpose="attempt remote"):
        fail("ATTEMPT_WORKTREE must not retain a remote")
    readback_ref = required("DESKTOP_LOCAL_IMAGE_READBACK_REF") if local_canary_only else worker_image
    if _command_output(["docker", "image", "inspect", "--format", "{{.Id}}", readback_ref], purpose="worker local config identity") != image_digest:
        fail("worker local config identity must equal DESKTOP_IMAGE_DIGEST")
    if not local_canary_only and worker_image not in _repo_digests(readback_ref):
        fail("worker repository digest readback must include DESKTOP_WORKER_IMAGE")
    if _command_output(["docker", "image", "inspect", "--format", "{{ index .Config.Labels \"org.opencontainers.image.revision\" }}", readback_ref], purpose="worker image revision") != expected_revision:
        fail("worker image revision label must equal DESKTOP_HEAD_REVISION")
    return image_digest, expected_revision, readback_ref


def validate_gateway(*, image_digest: str, expected_revision: str, readback_ref: str) -> None:
    if _normalise_image_digest("DESKTOP_GATEWAY_IMAGE_DIGEST") != image_digest:
        fail("DESKTOP_GATEWAY_IMAGE_DIGEST must equal DESKTOP_IMAGE_DIGEST")
    require_hash("DESKTOP_VIEW_GATEWAY_RUNTIME_IDENTITY_HASH")
    require_hash("DESKTOP_VIEW_GATEWAY_CONTAINER_IDENTITY_HASH")
    require_hash("DESKTOP_WORKER_BACKPLANE_NETWORK_IDENTITY_HASH")
    require_hash("DESKTOP_VIEW_CLIENT_NETWORK_IDENTITY_HASH")
    if required("DESKTOP_WORKER_BACKPLANE_NETWORK_IDENTITY_HASH") == required("DESKTOP_VIEW_CLIENT_NETWORK_IDENTITY_HASH"):
        fail("gateway private network identities must differ")
    require_identifier("DESKTOP_GATEWAY_ADMISSION_ID", ADMISSION_RE)
    # A path is case-sensitive on the runner. Do not normalise it like an
    # identifier: mktemp may emit uppercase directory characters.
    key_file = Path(required_path("DESKTOP_VIEW_GATEWAY_KEY_FILE")).resolve()
    try:
        mode = key_file.stat().st_mode
    except OSError:
        fail("DESKTOP_VIEW_GATEWAY_KEY_FILE is unavailable")
    if not key_file.is_file() or mode & 0o077:
        fail("DESKTOP_VIEW_GATEWAY_KEY_FILE must be a private regular file")
    if _command_output(["docker", "image", "inspect", "--format", "{{ index .Config.Labels \"org.opencontainers.image.revision\" }}", readback_ref], purpose="gateway image revision") != expected_revision:
        fail("gateway image revision label must equal DESKTOP_HEAD_REVISION")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--require-gateway", action="store_true")
    parser.add_argument("--local-canary-only", action="store_true")
    options = parser.parse_args()
    if options.local_canary_only and os.environ.get("GITHUB_ACTIONS", "").strip().lower() != "true":
        fail("--local-canary-only is restricted to GitHub Actions evidence")
    image_digest, expected_revision, readback_ref = validate_worker(local_canary_only=options.local_canary_only)
    if options.require_gateway:
        validate_gateway(image_digest=image_digest, expected_revision=expected_revision, readback_ref=readback_ref)
    print("desktop-worker configuration accepted")


if __name__ == "__main__":
    main()
