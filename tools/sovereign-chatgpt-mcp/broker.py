from __future__ import annotations

import grp
import json
import os
import re
import socketserver
import stat
import subprocess
from pathlib import Path
from typing import Any

from admin_mode import PrivateAdminRuntime
from command_contract import is_mutating_action
from github_admin import GitHubAdminRuntime
from managed_compose import ManagedComposeRuntime
from operations import OperationsRuntime
from policy import validate_container
from self_update import SelfUpdateRuntime

MAX_REQUEST_BYTES = 1_200_000
MAX_RESPONSE_BYTES = 1_000_000
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class BrokerRuntime:
    def __init__(self) -> None:
        self.private_owner_mode = os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE", "0").strip() == "1"
        self.allowed_containers = tuple(
            item.strip()
            for item in os.getenv(
                "SOVEREIGN_MCP_ALLOWED_CONTAINERS",
                "sovereign-backend,sovereign-chatgpt-mcp",
            ).split(",")
            if item.strip()
        )
        self.image_repository = os.getenv(
            "SOVEREIGN_BACKEND_IMAGE_REPOSITORY",
            "ghcr.io/ouroboroscollective/sovereign-backend",
        ).strip()
        self.operations = OperationsRuntime()
        self.managed_compose = ManagedComposeRuntime()
        self.admin = PrivateAdminRuntime(self.operations)
        self.self_update = SelfUpdateRuntime()
        self.github = GitHubAdminRuntime(self.self_update)

    @staticmethod
    def _run(argv: list[str], timeout: int = 60) -> dict[str, Any]:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={
                **os.environ,
                "PATH": os.environ.get(
                    "PATH",
                    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ),
            },
        )
        limit = 24_000
        return {
            "ok": completed.returncode == 0,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-limit:],
            "stderr": completed.stderr[-limit:],
        }

    def health(self, _arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "status": "BROKER_READY",
            "failure_family": None,
            "pid": os.getpid(),
            "socket_path": os.getenv(
                "SOVEREIGN_MCP_BROKER_SOCKET",
                "/run/sovereign-chatgpt-broker/operator.sock",
            ),
        }

    def container_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        container = validate_container(
            str(arguments.get("container") or ""),
            self.allowed_containers,
            allow_any=self.private_owner_mode,
        )
        result = self._run(
            ["docker", "inspect", "--format", "{{json .State}}", container],
            timeout=30,
        )
        if not result["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "container": container,
                "error": result["stderr"],
            }
        try:
            state = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            return {
                "ok": False,
                "status": "FAILED",
                "container": container,
                "error": f"Docker state is not valid JSON: {exc}",
            }
        return {"ok": True, "status": "VERIFIED", "container": container, "state": state}

    def container_logs(self, arguments: dict[str, Any]) -> dict[str, Any]:
        container = validate_container(
            str(arguments.get("container") or ""),
            self.allowed_containers,
            allow_any=self.private_owner_mode,
        )
        tail = max(1, min(int(arguments.get("tail", 200)), 1000))
        result = self._run(["docker", "logs", "--tail", str(tail), container], timeout=60)
        return {
            "ok": result["ok"],
            "status": "VERIFIED" if result["ok"] else "FAILED",
            "container": container,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }

    def resolve_backend_image(self, arguments: dict[str, Any]) -> dict[str, Any]:
        revision = str(arguments.get("revision") or "").strip()
        if not COMMIT_SHA_RE.fullmatch(revision):
            raise ValueError("revision muss ein vollständiger Commit-SHA sein")
        if not self.image_repository:
            raise RuntimeError("SOVEREIGN_BACKEND_IMAGE_REPOSITORY fehlt")
        tagged_image = f"{self.image_repository}:{revision}"
        pull = self._run(["docker", "pull", tagged_image], timeout=300)
        if not pull["ok"]:
            return {
                "ok": False,
                "status": "FAILED",
                "image": tagged_image,
                "error": pull["stderr"],
            }
        label = self._run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                tagged_image,
            ],
            timeout=30,
        )
        if not label["ok"] or label["stdout"].strip() != revision:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": "Image-Revision-Label stimmt nicht mit dem angeforderten Commit überein",
                "image": tagged_image,
            }
        digest_result = self._run(
            ["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tagged_image],
            timeout=30,
        )
        if not digest_result["ok"]:
            return {"ok": False, "status": "FAILED", "image": tagged_image, "error": digest_result["stderr"]}
        try:
            repo_digests = json.loads(digest_result["stdout"])
        except json.JSONDecodeError as exc:
            return {"ok": False, "status": "FAILED", "image": tagged_image, "error": str(exc)}
        prefix = f"{self.image_repository}@"
        resolved = next((entry for entry in repo_digests if isinstance(entry, str) and entry.startswith(prefix)), "")
        if not resolved:
            return {"ok": False, "status": "FAILED", "image": tagged_image, "error": "Kein Repository-Digest gefunden"}
        digest = resolved.split("@", 1)[1]
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            return {"ok": False, "status": "FAILED", "image": tagged_image, "error": "Ungültiger Repository-Digest"}
        return {
            "ok": True,
            "status": "VERIFIED",
            "revision": revision,
            "image": tagged_image,
            "image_digest": digest,
            "immutable_reference": resolved,
        }

    def dispatch(
        self,
        action: str,
        arguments: dict[str, Any],
        *,
        execution_origin: str = "socket",
    ) -> dict[str, Any]:
        if is_mutating_action(action) and execution_origin != "host_worker":
            return {
                "ok": False,
                "status": "BLOCKED",
                "failure_family": "INBOUND_MUTATION_FORBIDDEN",
                "blocker": "Mutierende Befehle dürfen nicht direkt von außen über den Broker-Socket ausgeführt werden",
                "next_action": "submit_validated_intent_to_host_command_queue",
            }
        handlers = {
            "broker_health": self.health,
            "host_worker_canary": lambda _values: {
                "ok": True,
                "status": "HOST_WORKER_READY",
                "execution_origin": execution_origin,
            },
            "container_status": self.container_status,
            "container_logs": self.container_logs,
            "resolve_backend_image": self.resolve_backend_image,
            "apply_verified_migration": lambda values: self.admin.apply_verified_migration_with_self_heal(
                workspace_id=str(values.get("workspace_id") or ""),
                path=str(values.get("path") or ""),
                confirmation_sha256=str(values.get("confirmation_sha256") or ""),
            ),
            "postgres_admin_sql": lambda values: self.admin.execute_sql(
                sql=str(values.get("sql") or ""),
                database=str(values.get("database") or ""),
                timeout_seconds=int(values.get("timeout_seconds") or 300),
            ),
            "git_push_main": lambda values: self.admin.push_workspace_to_main(
                workspace_id=str(values.get("workspace_id") or ""),
                commit_message=str(values.get("commit_message") or ""),
            ),
            "github_pr_status": lambda values: self.github.pr_status(
                pr_number=int(values.get("pr_number") or 0),
            ),
            "github_rerun_failed_workflows": lambda values: self.github.rerun_failed_workflows(
                pr_number=int(values.get("pr_number") or 0),
            ),
            "github_workflow_dispatch": lambda values: self.github.dispatch_workflow(
                workflow=str(values.get("workflow") or ""),
                ref=str(values.get("ref") or "main"),
                inputs=values.get("inputs") if isinstance(values.get("inputs"), dict) else {},
            ),
            "github_workflow_run_status": lambda values: self.github.workflow_run_status(
                run_id=int(values.get("run_id") or 0),
            ),
            "github_merge_pr": lambda values: self.github.merge_pr(
                pr_number=int(values.get("pr_number") or 0),
                expected_head_sha=str(values.get("expected_head_sha") or ""),
                merge_method=str(values.get("merge_method") or "squash"),
                self_update_after_merge=bool(values.get("self_update_after_merge", True)),
                owner_approved=bool(values.get("owner_approved", False)),
                mark_ready_if_draft=bool(values.get("mark_ready_if_draft", False)),
                allow_unrelated_android_pending=bool(values.get("allow_unrelated_android_pending", False)),
            ),
            "mcp_self_update_schedule": lambda values: self.self_update.schedule(
                expected_revision=str(values.get("expected_revision") or ""),
                reason=str(values.get("reason") or ""),
            ),
            "mcp_self_update_status": lambda _values: self.self_update.status(),
            "deploy_verified_release": lambda values: self.operations.deploy_verified_release(
                image_digest=str(values.get("image_digest") or ""),
                expected_revision=str(values.get("expected_revision") or ""),
                confirmation_revision=str(values.get("confirmation_revision") or ""),
            ),
            "rollback_release": lambda values: self.operations.rollback_release(
                target_image_digest=str(values.get("target_image_digest") or ""),
                confirmation_digest=str(values.get("confirmation_digest") or ""),
            ),
            "managed_compose_stack_plan": lambda values: self.managed_compose.plan(
                stack_id=str(values.get("stack_id") or ""),
            ),
            "litellm_provider_model_inventory": lambda _values: self.managed_compose.litellm_provider_model_inventory(),
            "litellm_model_aliases_activate": lambda values: self.managed_compose.activate_litellm_model_aliases(
                fast_provider_model=str(values.get("fast_provider_model") or ""),
                balanced_provider_model=str(values.get("balanced_provider_model") or ""),
                confirmation_inventory_sha256=str(values.get("confirmation_inventory_sha256") or ""),
            ),
            "deploy_managed_compose_stack": lambda values: self.managed_compose.deploy(
                stack_id=str(values.get("stack_id") or ""),
                confirmation_sha256=str(values.get("confirmation_sha256") or ""),
            ),
        }
        handler = handlers.get(action)
        if handler is None:
            return {
                "ok": False,
                "status": "BLOCKED",
                "blocker": f"Broker-Aktion ist nicht freigegeben: {action}",
            }
        try:
            return handler(arguments)
        except (ValueError, FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "status": "BLOCKED", "blocker": str(exc)[:2000]}


RUNTIME = BrokerRuntime()


class BrokerHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            return
        request_id = "unknown"
        try:
            request = json.loads(raw.decode("utf-8"))
            request_id = str(request.get("request_id") or "unknown")
            action = str(request.get("action") or "")
            arguments = request.get("arguments") or {}
            if not isinstance(arguments, dict):
                raise ValueError("arguments must be an object")
            result = RUNTIME.dispatch(action, arguments)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            result = {"ok": False, "status": "BLOCKED", "blocker": str(exc)[:2000]}
        payload = json.dumps(
            {"request_id": request_id, "result": result},
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        if len(payload) > MAX_RESPONSE_BYTES:
            payload = json.dumps(
                {
                    "request_id": request_id,
                    "result": {
                        "ok": False,
                        "status": "FAILED",
                        "error": "Broker response exceeded limit",
                    },
                },
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
        self.wfile.write(payload)


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def _prepare_socket(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        mode = path.lstat().st_mode
        if not stat.S_ISSOCK(mode):
            raise RuntimeError(f"Refusing to replace non-socket path: {path}")
        path.unlink()


def main() -> None:
    socket_path = Path(
        os.getenv(
            "SOVEREIGN_MCP_BROKER_SOCKET",
            "/run/sovereign-chatgpt-broker/operator.sock",
        )
    )
    group_name = os.getenv("SOVEREIGN_MCP_BROKER_GROUP", "sovereign-mcp")
    _prepare_socket(socket_path)
    previous_umask = os.umask(0o007)
    try:
        with ThreadingUnixServer(str(socket_path), BrokerHandler) as server:
            group_id = grp.getgrnam(group_name).gr_gid
            os.chown(socket_path, 0, group_id)
            os.chmod(socket_path, 0o660)
            server.serve_forever(poll_interval=0.5)
    finally:
        os.umask(previous_umask)
        if socket_path.exists() and stat.S_ISSOCK(socket_path.lstat().st_mode):
            socket_path.unlink()


if __name__ == "__main__":
    main()
