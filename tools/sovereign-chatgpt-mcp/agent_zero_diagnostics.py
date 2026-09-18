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
# Agent Zero activates this dedicated framework runtime before starting run_ui.py.
# docker exec does not source that activation script, so invoke the same fixed
# interpreter directly instead of relying on the container's ambient PATH.
AGENT_ZERO_PYTHON = "/opt/venv-a0/bin/python"
AGENT_ZERO_WORKSPACE_HOST_ROOT = "/opt/sovereign-agent-workspaces"
AGENT_ZERO_WORKSPACE_CONTAINER_ROOT = "/a0/sovereign-workspaces"
EVIDENCE_ROOT = Path("/opt/sovereign-chatgpt-tools/runtime-evidence")
TERMINAL = {"completed", "failed", "canceled", "rejected"}
RECEIPT_NAME = re.compile(r"^agent-zero-canary-([0-9a-f]{32})\.json$")
QUARANTINE_NAME = re.compile(r"^agent-zero-canary-quarantine-([0-9a-f]{32})\.json$")


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

    def _workspace_mount(self, identity):
        mounts = self._run([
            "docker", "inspect", "--format", "{{json .Mounts}}", identity["id"],
        ])
        if not isinstance(mounts, list):
            raise RuntimeError("AGENT_ZERO_SHARED_WORKSPACE_MOUNT_INVALID")
        for item in mounts:
            if not isinstance(item, dict):
                continue
            if str(item.get("Destination") or "") != AGENT_ZERO_WORKSPACE_CONTAINER_ROOT:
                continue
            verified = bool(
                item.get("Type") == "bind"
                and item.get("Source") == AGENT_ZERO_WORKSPACE_HOST_ROOT
                and item.get("RW") is True
            )
            if not verified:
                break
            return {
                "type": "bind",
                "source": AGENT_ZERO_WORKSPACE_HOST_ROOT,
                "destination": AGENT_ZERO_WORKSPACE_CONTAINER_ROOT,
                "readWrite": True,
                "verified": True,
            }
        raise RuntimeError("AGENT_ZERO_SHARED_WORKSPACE_MOUNT_MISSING")

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
        interpreter = AGENT_ZERO_PYTHON if action == "agent-zero" else "python"
        result = self._run(["docker", "exec", "-i", "--user", "0", identity["id"],
                            interpreter, "-I", "-B", "-", *args], script=script, timeout=55)
        if action == "agent-zero":
            processes = result.get("serverProcesses") if isinstance(result, dict) else None
            if not isinstance(processes, list) or not processes:
                raise RuntimeError("AGENT_ZERO_SERVER_PROCESS_NOT_FOUND")
            if not any(isinstance(item, dict) and item.get("sameExecutableAsProbe") is True
                       for item in processes):
                raise RuntimeError("AGENT_ZERO_PYTHON_EXECUTABLE_MISMATCH")
            result["diagnosticInterpreterVerified"] = True
        return result

    def inspect(self, *, expected_revision, expected_image_digest):
        stage = "bind-backend-runtime"
        try:
            backend = self._bound_backend(expected_revision, expected_image_digest)
            stage = "probe-backend-worker"
            result = self._probe(backend, "inspect", expected_revision, expected_image_digest)
            if result.get("ok") is not True:
                result.update(diagnosticStage=stage, runtimeCanaryPassed=False,
                              secretValuesReturned=False)
                return result
            stage = "bind-agent-zero-runtime"
            agent_zero = self._identity(AGENT_ZERO)
            stage = "verify-agent-zero-shared-workspace"
            workspace_mount = self._workspace_mount(agent_zero)
            stage = "probe-agent-zero-runtime"
            result["agentZeroPackages"] = self._probe(agent_zero, "agent-zero")
            result["agentZeroWorkspaceMount"] = workspace_mount
            stage = "stability-readback"
            if self._identity(BACKEND) != backend or self._identity(AGENT_ZERO) != agent_zero:
                return {**blocked("RUNTIME_CHANGED_DURING_DIAGNOSTIC"),
                        "diagnosticStage": stage}
            result.update(backendIdentity=backend, agentZeroIdentity=agent_zero,
                          diagnosticStage="complete", runtimeCanaryPassed=False,
                          secretValuesReturned=False)
            return result
        except Exception as exc:
            # Preserve only bounded internal failure-family identifiers. Never expose
            # subprocess stderr, exception text, URLs, response bodies or headers.
            safe_family = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else ""
            if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,120}", safe_family):
                safe_family = "AGENT_ZERO_DIAGNOSTIC_UNAVAILABLE"
            return {**blocked(safe_family), "diagnosticStage": stage}

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

    @staticmethod
    def _receipt_summary(receipt):
        result = receipt.get("result", {}) if isinstance(receipt, dict) else {}
        binding = receipt.get("binding", {}) if isinstance(receipt, dict) else {}
        operation_id = str(receipt.get("operationId") or "") if isinstance(receipt, dict) else ""
        return {
            "operationId": operation_id if OPERATION.fullmatch(operation_id) else None,
            "status": str(receipt.get("status") or "")[:80] if isinstance(receipt, dict) else "",
            "taskIdPresent": bool(result.get("taskId")),
            "taskReadbackVerified": result.get("taskReadbackVerified") is True,
            "taskState": str(result.get("taskState") or "")[:40],
            "httpStatus": result.get("httpStatus") if isinstance(result.get("httpStatus"), int) else None,
            "bindingRevision": binding.get("revision") if SHA.fullmatch(str(binding.get("revision") or "")) else None,
            "bindingDigest": binding.get("digest") if DIGEST.fullmatch(str(binding.get("digest") or "")) else None,
        }

    @staticmethod
    def _quarantine_file(operation_id):
        return "agent-zero-canary-quarantine-" + operation_id + ".json"

    def _quarantine_present(self, fd, operation_id):
        try:
            marker = self._read(fd, self._quarantine_file(operation_id))
        except FileNotFoundError:
            return False
        return bool(
            isinstance(marker, dict)
            and marker.get("operationId") == operation_id
            and marker.get("unknownOutcomePreserved") is True
            and marker.get("sameOperationMayResubmit") is False
        )

    @staticmethod
    def _runtime_release_advanced(receipt, current_binding):
        old = receipt.get("binding", {}) if isinstance(receipt, dict) else {}
        old_revision = str(old.get("revision") or "")
        old_digest = str(old.get("digest") or "")
        current_revision = str(current_binding.get("revision") or "")
        current_digest = str(current_binding.get("digest") or "")
        return bool(
            SHA.fullmatch(old_revision)
            and DIGEST.fullmatch(old_digest)
            and SHA.fullmatch(current_revision)
            and DIGEST.fullmatch(current_digest)
            and (old_revision != current_revision or old_digest != current_digest)
        )

    def _quarantine_stale_unknowns(self, fd, names, current_binding):
        quarantined = []
        blockers = []
        for receipt_name in names:
            receipt = self._read(fd, receipt_name)
            if self._settled(receipt):
                continue
            summary = self._receipt_summary(receipt)
            operation_id = summary.get("operationId")
            if not operation_id:
                blockers.append(summary)
                continue
            if self._quarantine_present(fd, operation_id):
                continue
            result = receipt.get("result", {}) if isinstance(receipt, dict) else {}
            safe_candidate = bool(
                receipt.get("status") in {"SUBMIT_CLAIMED", "SUBMIT_UNRESOLVED"}
                and not result.get("taskId")
                and self._runtime_release_advanced(receipt, current_binding)
            )
            if not safe_candidate:
                blockers.append(summary)
                continue
            marker = {
                "status": "UNKNOWN_OUTCOME_QUARANTINED_FOR_NEW_RUNTIME_RELEASE",
                "operationId": operation_id,
                "unknownOutcomePreserved": True,
                "sameOperationMayResubmit": False,
                "allowsNewDistinctCanary": True,
                "sourceRevision": summary.get("bindingRevision"),
                "sourceDigest": summary.get("bindingDigest"),
                "supersedingRevision": current_binding["revision"],
                "supersedingDigest": current_binding["digest"],
                "secretValuesReturned": False,
            }
            self._write(fd, self._quarantine_file(operation_id), marker)
            quarantined.append(operation_id)
        return quarantined, blockers

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
            self._workspace_mount(agent_zero)
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
            names = sorted(n for n in os.listdir(fd) if RECEIPT_NAME.fullmatch(n))
            if name in names:
                receipt = self._read(fd, name)
                original_binding = receipt.get("binding") if isinstance(receipt, dict) else None
                if not isinstance(original_binding, dict):
                    return blocked("AGENT_ZERO_CANARY_RECEIPT_INVALID")
                if action == "submit":
                    if original_binding != binding:
                        return blocked("AGENT_ZERO_CANARY_RUNTIME_CHANGED")
                    return receipt  # Replay NEVER invokes message/send again.
                task_id = receipt.get("result", {}).get("taskId")
                if not task_id:
                    return blocked("AGENT_ZERO_A2A_SUBMIT_OUTCOME_UNKNOWN")
                # A known Task-ID belongs to the Agent Zero execution runtime, not
                # to the backend release that originally submitted it. Permit a
                # later exact backend release to perform a read-only poll only
                # while the bound Agent Zero container identity is unchanged.
                if original_binding.get("agentZero") != agent_zero:
                    return blocked("AGENT_ZERO_CANARY_AGENT_ZERO_RUNTIME_CHANGED")
            else:
                if action != "submit":
                    return blocked("AGENT_ZERO_CANARY_RECEIPT_NOT_FOUND")
                if len(names) >= 100:
                    return blocked("AGENT_ZERO_CANARY_RECEIPT_QUOTA")
                quarantined, unresolved = self._quarantine_stale_unknowns(fd, names, binding)
                if unresolved:
                    return {
                        **blocked("AGENT_ZERO_CANARY_UNRESOLVED_PRIOR_SUBMIT"),
                        "unresolvedOperations": unresolved[:20],
                        "quarantinedUnknownOperations": quarantined[:20],
                    }
                preflight = self._probe(backend, "inspect", expected_revision, expected_image_digest)
                if preflight.get("ok") is not True:
                    return preflight
                receipt = {"ok": False, "status": "SUBMIT_CLAIMED", "operationId": operation_id,
                           "binding": binding, "result": {}, "secretValuesReturned": False,
                           "quarantinedUnknownOperations": quarantined[:20]}
                self._write(fd, name, receipt)  # fsync before any message/send.
                task_id = ""
            result = self._probe(backend, action, expected_revision, expected_image_digest, task_id)
            # Persist submit outcome before further network/container reads.
            # On a poll transport failure retain the only known task ID.
            if action == "poll" and not result.get("taskId"):
                result["taskId"] = task_id
            if action == "poll":
                # Preserve submit provenance in `binding`; record the exact
                # backend/runtime identity used for this later readback separately.
                receipt["pollBinding"] = binding
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
