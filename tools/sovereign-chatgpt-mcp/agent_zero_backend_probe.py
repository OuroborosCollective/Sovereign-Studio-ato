"""Fixed, stdin-only diagnostic executed inside the selected live container.

No repository writes, package installation, arbitrary command, URL or prompt.
The helper reproduces a Gunicorn worker's startup environment and credentials;
it does not pretend to inspect that worker's Python heap.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import urlsplit
import uuid

PROMPT = (
    "Transport canary only. Reply with SOVEREIGN_A2A_CANARY_OK and finish. "
    "Do not use tools, access files, repositories, memory, network or secrets, "
    "run commands, delegate, or perform any other action."
)
KEY_NAMES = (
    "SOVEREIGN_AGENT_ZERO_BASE_URL", "SOVEREIGN_OWNER_INPUT_ROOT",
    "SOVEREIGN_AGENT_ZERO_API_KEY_FILE",
)
STATES = {"submitted", "working", "completed", "failed", "canceled", "rejected",
          "input_required", "auth_required"}


class ProbeFailure(Exception):
    pass


def fail(code):
    raise ProbeFailure(code)


def safe_config(env):
    root = env.get(KEY_NAMES[1], "/opt/sovereign-owner-managed")
    raw = env.get(KEY_NAMES[0], "https://agent-zero-xrev.srv1491137.hstgr.cloud")
    try:
        url = urlsplit(raw)
        valid = (url.scheme == "https" and url.hostname and not url.username
                 and not url.password and not url.query and not url.fragment
                 and url.path in {"", "/"})
    except ValueError:
        valid = False
    path = env.get(KEY_NAMES[2], root + "/agent_zero_api_key.txt")
    return {
        KEY_NAMES[0]: raw if valid else "REDACTED_INVALID_VALUE",
        KEY_NAMES[1]: root if re.fullmatch(r"/[A-Za-z0-9/_.-]{1,240}", root) else "REDACTED_INVALID_VALUE",
        KEY_NAMES[2]: path if re.fullmatch(r"/[A-Za-z0-9/_.-]{1,280}", path) else "REDACTED_INVALID_VALUE",
        "explicitlySet": {key: key in env for key in KEY_NAMES},
    }


def process_snapshot(proc=Path("/proc")):
    candidates = []
    for item in proc.iterdir():
        if not item.name.isdigit():
            continue
        try:
            cmd = (item / "cmdline").read_bytes().replace(b"\0", b" ")
            if b"gunicorn" not in cmd or int(item.name) == os.getpid():
                continue
            status = dict(line.split(":", 1) for line in (item / "status").read_text().splitlines() if ":" in line)
            env = dict(part.split(b"=", 1) for part in (item / "environ").read_bytes().split(b"\0") if b"=" in part)
            env = {k.decode(): v.decode() for k, v in env.items()}
            candidates.append({"pid": int(item.name), "ppid": int(status["PPid"]),
                               "uid": int(status["Uid"].split()[1]), "gid": int(status["Gid"].split()[1]),
                               "groups": sorted(map(int, status["Groups"].split())), "env": env,
                               "cwd": str((item / "cwd").resolve(strict=True)),
                               "executable": str((item / "exe").resolve(strict=True)),
                               "startTicks": int((item / "stat").read_text().rsplit(")", 1)[1].split()[19])})
        except FileNotFoundError:
            continue  # Process exited during inventory; consensus below remains mandatory.
    ids = {p["pid"] for p in candidates}
    workers = [p for p in candidates if p["ppid"] in ids]
    if not workers:
        fail("BACKEND_GUNICORN_WORKER_NOT_FOUND")
    binding = lambda p: (p["uid"], p["gid"], p["groups"], p["env"], p["cwd"], p["executable"])
    if any(binding(p) != binding(workers[0]) for p in workers):
        fail("BACKEND_WORKER_CONTEXT_DIVERGED")
    return sorted(workers, key=lambda p: p["pid"])[0]


def adopt_worker(worker):
    os.environ.clear()
    os.environ.update(worker["env"])
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    if Path(sys.executable).resolve() != Path(worker["executable"]):
        fail("BACKEND_PYTHON_EXECUTABLE_MISMATCH")
    os.setgroups(worker["groups"])
    os.setgid(worker["gid"])
    os.setuid(worker["uid"])
    if (os.geteuid(), os.getegid(), sorted(os.getgroups())) != (worker["uid"], worker["gid"], worker["groups"]):
        fail("BACKEND_WORKER_CREDENTIAL_MISMATCH")
    os.chdir(worker["cwd"])
    sys.path.insert(0, worker["cwd"])


def key_readback(config):
    """Open every component without following symlinks, under worker credentials."""
    root = config[KEY_NAMES[1]]
    key = config[KEY_NAMES[2]]
    if (not root.startswith("/") or ".." in Path(root).parts
            or key != root.rstrip("/") + "/agent_zero_api_key.txt"):
        fail("AGENT_ZERO_KEY_FILE_REJECTED")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in Path(root).parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open("agent_zero_api_key.txt", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                fail("AGENT_ZERO_KEY_FILE_PERMISSIONS_INVALID")
            data = os.read(leaf, 8193)
            if not 16 <= len(data) <= 8192:
                fail("AGENT_ZERO_KEY_LENGTH_INVALID")
            del data
            return {"exists": True, "readableAsWorker": True, "symlinkFree": True,
                    "regularFile": True, "mode": oct(stat.S_IMODE(info.st_mode)),
                    "ownerUid": info.st_uid, "ownerGid": info.st_gid}
        finally:
            os.close(leaf)
    except FileNotFoundError:
        fail("AGENT_ZERO_KEY_FILE_MISSING")
    except PermissionError:
        fail("AGENT_ZERO_KEY_FILE_UNREADABLE")
    except OSError:
        fail("AGENT_ZERO_KEY_FILE_REJECTED")
    finally:
        os.close(fd)


def rpc(module, action, task_id, evidence):
    client = module.AgentZeroA2AClient.from_env()
    original = module.requests.post

    def observed_post(*args, **kwargs):
        response = original(*args, **kwargs)
        evidence["httpStatus"] = response.status_code
        return response

    module.requests.post = observed_post
    evidence["submitAttempted"] = action == "submit"
    try:
        if action == "submit":
            call_id = str(uuid.uuid4())
            payload = {"jsonrpc": "2.0", "id": call_id, "method": "message/send", "params": {
                "message": {"messageId": "sovereign-canary-" + call_id, "kind": "message", "role": "user",
                            "parts": [{"kind": "text", "text": PROMPT}]},
                "configuration": {"blocking": False, "acceptedOutputModes": ["text", "text/plain"]}}}
            task = module._parse_task(client._post_rpc(payload, submit=True))
        else:
            task = client.get_task(task_id)
        evidence.update(taskId=task.task_id, taskState=task.state,
                        taskReadbackVerified=action == "poll")
        return evidence
    finally:
        module.requests.post = original


def backend_probe(action, revision, digest, task_id=""):
    result = {"ok": False, "status": "BLOCKED", "secretValuesReturned": False,
              "submitAttempted": False, "httpStatus": None,
              "workerHeapInspected": False, "processContextSource": "proc-startup-environment"}
    try:
        worker = process_snapshot()
        result["worker"] = {k: worker[k] for k in ("pid", "uid", "gid", "groups", "startTicks")}
        result["configuration"] = safe_config(worker["env"])
        if (worker["env"].get("SOVEREIGN_SOURCE_REVISION") != revision
                or worker["env"].get("SOVEREIGN_IMAGE_DIGEST") != digest):
            fail("BACKEND_PROCESS_REVISION_MISMATCH")
        adopt_worker(worker)
        result["keyReadback"] = key_readback(result["configuration"])
        if action == "inspect":
            result.update(ok=True, status="BACKEND_PROCESS_READBACK_VERIFIED")
            return result
        module = importlib.import_module("agent_runtime.agent_zero_a2a")
        rpc(module, action, task_id, result)
        result.update(ok=True, status="A2A_TASK_OBSERVED")
    except Exception as exc:
        family = exc.args[0] if isinstance(exc, ProbeFailure) else getattr(exc, "family", "BACKEND_PROBE_FAILED")
        # Only known adapter families, never exception details, URLs, bodies or headers.
        if not isinstance(family, str) or not re.fullmatch(r"(?:AGENT_ZERO|BACKEND)_[A-Z_]{1,100}", family):
            family = "BACKEND_PROBE_FAILED"
        result["failureFamily"] = family
        status_code = getattr(exc, "http_status", None)
        if isinstance(status_code, int) and 100 <= status_code <= 599:
            result["httpStatus"] = status_code
    return result


def agent_zero_inventory():
    packages = {}
    for name in ("fasta2a", "litellm"):
        try:
            version = importlib.metadata.version(name)
            packages[name] = version if re.fullmatch(r"[0-9A-Za-z.+-]{1,50}", version) else None
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    servers = []
    for item in Path("/proc").iterdir():
        if not item.name.isdigit() or int(item.name) == os.getpid():
            continue
        try:
            command = (item / "cmdline").read_bytes()
            if b"run_ui.py" not in command:
                continue
            servers.append({
                "pid": int(item.name),
                "startTicks": int((item / "stat").read_text().rsplit(")", 1)[1].split()[19]),
                "sameExecutableAsProbe": (item / "exe").resolve() == Path(sys.executable).resolve(),
            })
        except FileNotFoundError:
            continue
    return {"installedVersions": packages, "requiredVersions": {"fasta2a": "0.5.0", "litellm": "1.88.1"},
            "serverProcesses": servers, "clockTicksPerSecond": os.sysconf("SC_CLK_TCK"),
            "loadedVersionsVerified": False, "fasta2aAvailableInRunningServer": None,
            "restartAfterPackageInstallationVerified": False,
            "evidenceLimit": "Fresh metadata read in diagnostic interpreter; server import state is unobserved."}


def main():
    output_fd = os.dup(1)
    # Suppress imported application/client logs, including native writes to stderr.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
        try:
            if sys.argv[1] == "agent-zero":
                result = agent_zero_inventory()
            else:
                result = backend_probe(*sys.argv[1:])
        except Exception:
            result = {"ok": False, "failureFamily": "BACKEND_PROBE_FAILED"}
    with os.fdopen(output_fd, "w") as output:
        json.dump(result, output)


if __name__ == "__main__":
    main()
