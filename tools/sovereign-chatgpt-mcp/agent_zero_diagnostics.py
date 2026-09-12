"""Fixed Agent Zero diagnostics through the existing broker/host-worker boundary."""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
OPERATION = re.compile(r"^[0-9a-f]{32}$")
BACKEND = "sovereign-backend"
AGENT_ZERO = "agent-zero-xrev-agent-zero-1"
EVIDENCE_ROOT = Path("/opt/sovereign-chatgpt-tools/runtime-evidence")
TERMINAL = {"completed", "failed", "canceled", "rejected"}


def blocked(family):
    return {"ok": False, "status": "BLOCKED", "failureFamily": family,
            "secretValuesReturned": False}


class AgentZeroDiagnosticsRuntime:
    def __init__(self):
        self.evidence_root = EVIDENCE_ROOT

    def _run(self, argv, *, script=None, timeout=15):
        """Never return stderr or exception text from a subprocess."""
        result = subprocess.run(argv, input=script, text=True, capture_output=True,
                                timeout=timeout, check=False)
        if result.returncode or len(result.stdout) > 32000:
            raise RuntimeError("DIAGNOSTIC_PROCESS_FAILED")
        return json.loads(result.stdout)

    def _identity(self, container):
        # Only fixed callers select the target; never inspect Config.Env or logs.
        value = self._run(["docker", "inspect", "--format",
            '{"id":{{json .Id}},"image":{{json .Image}},"startedAt":{{json .State.StartedAt}},'
            '"running":{{json .State.Running}},"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}}}',
            container])
        if (not isinstance(value, dict) or not re.fullmatch(r"[0-9a-f]{64}", value.get("id", ""))
                or not DIGEST.fullmatch(value.get("image", "")) or value.get("running") is not True
                or not re.fullmatch(r"[0-9TZ:.+-]{10,40}", value.get("startedAt", ""))):
            raise RuntimeError("CONTAINER_IDENTITY_INVALID")
        revision = value.get("revision")
        value["revision"] = revision if isinstance(revision, str) and SHA.fullmatch(revision) else None
        return value

    def _bound_backend(self, revision, digest):
        if not SHA.fullmatch(revision) or not DIGEST.fullmatch(digest):
            raise ValueError("EXACT_RUNTIME_IDENTITY_REQUIRED")
        identity = self._identity(BACKEND)
        digests = self._run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", identity["image"]])
        expected = "ghcr.io/ouroboroscollective/sovereign-backend@" + digest
        if identity["revision"] != revision or not isinstance(digests, list) or expected not in digests:
            raise RuntimeError("BACKEND_REVISION_OR_DIGEST_MISMATCH")
        return identity

    def _probe(self, identity, action, revision="", digest="", task_id=""):
        script = Path(__file__).with_name("agent_zero_backend_probe.py").read_text("utf-8")
        args = [action] if action == "agent-zero" else [action, revision, digest, task_id]
        return self._run(["docker", "exec", "-i", "--user", "0", identity["id"],
                          "python", "-I", "-B", "-", *args], script=script, timeout=55)

    def inspect(self, *, expected_revision, expected_image_digest):
        try:
            backend = self._bound_backend(expected_revision, expected_image_digest)
            result = self._probe(backend, "inspect", expected_revision, expected_image_digest)
            agent_zero = self._identity(AGENT_ZERO)
            result["agentZeroPackages"] = self._probe(agent_zero, "agent-zero")
            if self._identity(BACKEND) != backend or self._identity(AGENT_ZERO) != agent_zero:
                return blocked("RUNTIME_CHANGED_DURING_DIAGNOSTIC")
            result.update(backendIdentity=backend, agentZeroIdentity=agent_zero,
                          runtimeCanaryPassed=False, secretValuesReturned=False)
            return result
        except Exception:
            return blocked("AGENT_ZERO_DIAGNOSTIC_UNAVAILABLE")

    def _root_fd(self):
        fd = os.open(self.evidence_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            os.close(fd)
            raise RuntimeError("EVIDENCE_ROOT_NOT_PRIVATE")
        return fd

    @staticmethod
    def _read(fd, name):
        leaf = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
                raise RuntimeError("RECEIPT_NOT_PRIVATE")
            raw = os.read(leaf, 32001)
            if len(raw) > 32000:
                raise RuntimeError("RECEIPT_TOO_LARGE")
            return json.loads(raw)
        finally:
            os.close(leaf)

    @staticmethod
    def _write(fd, name, value):
        temporary = ".agent-zero-" + uuid.uuid4().hex
        leaf = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(leaf, "w") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.rename(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)

    @staticmethod
    def _settled(receipt):
        # A missing task ID after a 2xx/5xx/timeout is never safe to resubmit.
        result = receipt.get("result", {})
        status = result.get("httpStatus")
        return (result.get("taskReadbackVerified") is True and result.get("taskState") in TERMINAL
                or not result.get("taskId") and isinstance(status, int) and 300 <= status < 500)

    def canary(self, *, expected_revision, expected_image_digest, operation_id,
               action="submit", owner_approved=False):
        if (os.getenv("SOVEREIGN_MCP_PRIVATE_OWNER_MODE") != "1" or owner_approved is not True):
            return blocked("AGENT_ZERO_CANARY_OWNER_REQUIRED")
        if (action not in {"submit", "poll"} or not isinstance(operation_id, str)
                or not OPERATION.fullmatch(operation_id)):
            return blocked("AGENT_ZERO_CANARY_ARGUMENT_INVALID")
        fd = lock = None
        try:
            backend = self._bound_backend(expected_revision, expected_image_digest)
            agent_zero = self._identity(AGENT_ZERO)
            binding = {"backend": backend, "agentZero": agent_zero,
                       "revision": expected_revision, "digest": expected_image_digest}
            fd = self._root_fd()
            lock = os.open("agent-zero-canary.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            lock_info = os.fstat(lock)
            if (not stat.S_ISREG(lock_info.st_mode) or lock_info.st_mode & 0o077
                    or lock_info.st_uid != os.geteuid()):
                raise RuntimeError("CANARY_LOCK_NOT_PRIVATE")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            name = "agent-zero-canary-" + operation_id + ".json"
            names = [n for n in os.listdir(fd) if n.startswith("agent-zero-canary-") and n.endswith(".json")]
            if name in names:
                receipt = self._read(fd, name)
                if receipt["binding"] != binding:
                    return blocked("AGENT_ZERO_CANARY_RUNTIME_CHANGED")
                if action == "submit":
                    return receipt  # Replay NEVER invokes message/send again.
                task_id = receipt.get("result", {}).get("taskId")
                if not task_id:
                    return blocked("AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN")
            else:
                if action != "submit":
                    return blocked("AGENT_ZERO_CANARY_RECEIPT_NOT_FOUND")
                if len(names) >= 100:
                    return blocked("AGENT_ZERO_CANARY_RECEIPT_QUOTA")
                if any(not self._settled(self._read(fd, n)) for n in names):
                    return blocked("AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT")
                preflight = self._probe(backend, "inspect", expected_revision, expected_image_digest)
                if preflight.get("ok") is not True:
                    return preflight
                receipt = {"ok": False, "status": "SUBMIT_CLAIMED", "operationId": operation_id,
                           "binding": binding, "result": {}, "secretValuesReturned": False}
                self._write(fd, name, receipt)  # fsync before any message/send.
                task_id = ""
            result = self._probe(backend, action, expected_revision, expected_image_digest, task_id)
            # Persist submit outcome before further network/container reads.
            # On a poll transport failure retain the only known task ID.
            if action == "poll" and not result.get("taskId"):
                result["taskId"] = task_id
            passed = (action == "poll" and result.get("ok") is True
                      and result.get("taskReadbackVerified") is True and result.get("taskState") == "completed")
            receipt.update(result=result, ok=False, status="TASK_OBSERVED" if result.get("taskId") else "SUBMIT_UNRESOLVED")
            self._write(fd, name, receipt)
            if self._identity(BACKEND) != backend or self._identity(AGENT_ZERO) != agent_zero:
                receipt.update(status="RUNTIME_CHANGED", failureFamily="AGENT_ZERO_CANARY_RUNTIME_CHANGED")
            else:
                receipt.update(ok=passed, status="AGENT_ZERO_A2A_CANARY_PASS" if passed else receipt["status"])
            receipt.update(repositoryE2ePassed=False, repositoryMutationVerified=False)
            self._write(fd, name, receipt)
            return receipt
        except Exception:
            return {**blocked("AGENT_ZERO_CANARY_OUTCOME_UNVERIFIED"), "operationId": operation_id,
                    "nextAction": "Poll the existing operation; never repeat an unknown submit."}
        finally:
            if lock is not None:
                os.close(lock)
            if fd is not None:
                os.close(fd)
