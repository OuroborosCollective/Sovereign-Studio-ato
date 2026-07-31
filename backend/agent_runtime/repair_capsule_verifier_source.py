"""Offline verifier source embedded in Zero-Trust Repair Capsules."""

REPAIR_CAPSULE_VERIFIER_SOURCE = r'''#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
INDEX = re.compile(r"^index [0-9a-f]{7,64}\.\.[0-9a-f]{7,64}(?: (100644|100755|120000|160000))?$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(?: .*)?$")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SECRET = (
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}", re.I),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{8,}", re.I),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{10,}", re.I),
    re.compile(r"Authorization:\s*(?:Bearer\s+)?[^\s\n]+", re.I),
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: object) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def safe_path(value: str) -> str:
    if (
        not value
        or value.startswith(("/", "\\"))
        or re.match(r"^[A-Za-z]:/", value)
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value)
    ):
        raise ValueError("unsafe path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or ".git" in parts:
        raise ValueError("unsafe path")
    return value


def marker(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        raise ValueError("header mismatch")
    return safe_path(value[len(prefix):])


def patch_paths(patch: bytes) -> list[str]:
    if not patch or len(patch) > 2_000_000 or b"\0" in patch:
        raise ValueError("invalid patch")
    text = patch.decode("utf-8")
    if any(pattern.search(text) for pattern in SECRET):
        raise ValueError("secret material")
    if "GIT binary patch" in text or "Binary files " in text:
        raise ValueError("binary patch")
    if "Subproject commit " in text:
        raise ValueError("submodule patch")
    lines = text.split("\n")
    paths: list[str] = []
    seen: set[str] = set()
    cursor = 0
    while cursor < len(lines):
        if cursor == len(lines) - 1 and not lines[cursor]:
            break
        header = DIFF.fullmatch(lines[cursor])
        if not header:
            raise ValueError("unsupported diff header")
        old_path, new_path = map(safe_path, header.groups())
        if old_path != new_path or new_path in seen:
            raise ValueError("rename or duplicate path")
        seen.add(new_path)
        paths.append(new_path)
        cursor += 1
        kind = "modify"
        saw_index = False
        while cursor < len(lines) and not lines[cursor].startswith("--- "):
            line = lines[cursor]
            index_match = INDEX.fullmatch(line)
            if index_match:
                if index_match.group(1) in {"120000", "160000"}:
                    raise ValueError("unsafe object mode")
                saw_index = True
            elif line == "new file mode 100644" and kind == "modify":
                kind = "add"
            elif line == "deleted file mode 100644" and kind == "modify":
                kind = "delete"
            elif line.startswith(("new file mode ", "deleted file mode ", "old mode ", "new mode ")):
                raise ValueError("unsafe mode change")
            elif line.startswith(("similarity index ", "dissimilarity index ", "rename from ", "rename to ", "copy from ", "copy to ")):
                raise ValueError("rename or copy")
            else:
                raise ValueError("unknown metadata")
            cursor += 1
        if not saw_index or cursor + 1 >= len(lines) or not lines[cursor + 1].startswith("+++ "):
            raise ValueError("missing file headers")
        old_marker, new_marker = lines[cursor][4:], lines[cursor + 1][4:]
        cursor += 2
        headers_valid = (
            kind == "modify" and marker(old_marker, "a/") == new_path and marker(new_marker, "b/") == new_path
        ) or (
            kind == "add" and old_marker == "/dev/null" and marker(new_marker, "b/") == new_path
        ) or (
            kind == "delete" and marker(old_marker, "a/") == new_path and new_marker == "/dev/null"
        )
        if not headers_valid:
            raise ValueError("header path mismatch")
        saw_hunk = False
        while cursor < len(lines) and not lines[cursor].startswith("diff --git "):
            line = lines[cursor]
            if cursor == len(lines) - 1 and not line:
                cursor += 1
                break
            if HUNK.fullmatch(line):
                saw_hunk = True
            elif not (saw_hunk and (line.startswith((" ", "+", "-")) or line == r"\ No newline at end of file")):
                raise ValueError("unknown hunk syntax")
            cursor += 1
        if not saw_hunk:
            raise ValueError("missing hunk")
    if not paths or len(paths) > 12:
        raise ValueError("invalid path count")
    return sorted(paths)


def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, text=True, capture_output=True, shell=False, check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--manifest", default="manifest.json")
    parser.add_argument("--patch", default="repair.patch")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / arguments.manifest).read_text(encoding="utf-8"))
    patch = (root / arguments.patch).read_bytes()
    payload = {key: value for key, value in manifest.items() if key != "capsuleSha256"}
    derived_paths = patch_paths(patch)
    checks = [
        manifest.get("schemaVersion") == "sovereign.repair-capsule.v1",
        manifest.get("product") == "sovereign-rescue",
        manifest.get("ready") is True,
        manifest.get("blockers") == [],
        manifest.get("productionMutationIncluded") is False,
        manifest.get("secretValuesReturned") is False,
        SHA40.fullmatch(str(manifest.get("baseSha") or "")),
        SHA256.fullmatch(str(manifest.get("repositoryIdentitySha256") or "")),
        SHA256.fullmatch(str(manifest.get("outcomeContractSha256") or "")),
        SHA256.fullmatch(str(manifest.get("testEvidenceSha256") or "")),
        canonical_sha256(payload) == manifest.get("capsuleSha256"),
        digest(patch) == manifest.get("patchSha256"),
        manifest.get("patchByteCount") == len(patch),
        derived_paths == manifest.get("changedFiles"),
        manifest.get("maxChangedFiles") == 12,
        digest(Path(__file__).read_bytes()) == manifest.get("verifierSha256"),
        digest((root / "README.md").read_bytes()) == manifest.get("readmeSha256"),
    ]
    repository = Path(arguments.repo).resolve()
    head = run(["git", "-C", str(repository), "rev-parse", "--verify", "HEAD"])
    checks.append(head.returncode == 0 and head.stdout.strip().lower() == manifest.get("baseSha"))
    apply_check = run(["git", "-C", str(repository), "apply", "--check", str((root / arguments.patch).resolve())])
    checks.append(apply_check.returncode == 0)
    ok = bool(all(checks))
    print(json.dumps({"ok": ok, "status": "VERIFIED" if ok else "BLOCKED", "mutationPerformed": False}, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"ok": false, "status": "BLOCKED", "mutationPerformed": false}')
        raise SystemExit(1)
'''
