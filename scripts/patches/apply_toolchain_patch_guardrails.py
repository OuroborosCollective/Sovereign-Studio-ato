#!/usr/bin/env python3
"""
Apply the verified Toolchain patch-guardrail hardening to scripts/sovereign-backend/app.py.

Why this exists:
- Areghconnect SEARCH/REPLACE preview/apply was blocked in this conversation.
- The patch was applied locally against the latest uploaded main ZIP and verified with:
  python3 -m py_compile scripts/sovereign-backend/app.py
- This script preserves the exact safe SEARCH/REPLACE blocks so a later agent can
  apply them without doing a risky blind full-file replace.

Usage:
  python3 scripts/patches/apply_toolchain_patch_guardrails.py --repo-root . --check
  python3 scripts/patches/apply_toolchain_patch_guardrails.py --repo-root . --apply
"""

from __future__ import annotations

import argparse
import py_compile
from dataclasses import dataclass
from pathlib import Path

TARGET = Path("scripts/sovereign-backend/app.py")


@dataclass(frozen=True)
class Block:
    search: str
    replace: str


BLOCKS: tuple[Block, ...] = (
    Block(
        search='''# ── Internal helpers ──────────────────────────────────────────────────────────\n\ndef _tc_allowed(owner: str, repo: str) -> None:\n    slug = f"{owner}/{repo}".lower()\n    if "*" not in _TC_ALLOWED_REPOS and slug not in _TC_ALLOWED_REPOS:\n        raise PermissionError(f"Repo {owner}/{repo} ist nicht in der Allowlist")\n''',
        replace='''# ── Internal helpers ──────────────────────────────────────────────────────────\n\ndef _tc_safe_error(error: object) -> str:\n    text = str(error or "Unbekannter Toolchain-Fehler")\n    lowered = text.lower()\n    if any(marker in lowered for marker in ("authorization", "bearer ", "token", "secret", "api_key", "access_token", "password")):\n        return "Toolchain-Fehler; Details wegen möglicher Zugangsdaten ausgeblendet."\n    return text[:420]\n\n\ndef _tc_json_error(error: object, status: int):\n    return jsonify({"error": _tc_safe_error(error)}), status\n\n\ndef _tc_expected_sha(body: dict) -> str | None:\n    value = body.get("expectedSha") or body.get("expected_sha") or body.get("base_sha")\n    return value.strip() if isinstance(value, str) and value.strip() else None\n\n\ndef _tc_assert_expected_sha(current_sha: str, expected_sha: str | None) -> None:\n    if expected_sha and current_sha != expected_sha:\n        raise RuntimeError("SHA mismatch: Datei wurde seit der Vorschau geändert. Bitte neu laden und erneut previewen.")\n\n\ndef _tc_allowed(owner: str, repo: str) -> None:\n    slug = f"{owner}/{repo}".lower()\n    if "*" not in _TC_ALLOWED_REPOS and slug not in _TC_ALLOWED_REPOS:\n        raise PermissionError(f"Repo {owner}/{repo} ist nicht in der Allowlist")\n''',
    ),
    Block(
        search='''def _tc_apply_blocks(content: str, blocks: list) -> tuple:\n    """Apply strict SEARCH/REPLACE blocks. Each search must occur exactly once."""\n    updated = content\n    report = []\n    for i, block in enumerate(blocks):\n        search  = block.get("search", "")\n        replace = block.get("replace", "")\n        if not isinstance(search, str) or not isinstance(replace, str):\n            raise ValueError(f"Block {i}: search/replace müssen Strings sein")\n        if not search:\n            raise ValueError(f"Block {i}: search darf nicht leer sein")\n        count = updated.count(search)\n        if count != 1:\n            raise ValueError(\n                f"Block {i}: search muss genau einmal vorkommen, gefunden: {count}"\n            )\n        updated = updated.replace(search, replace, 1)\n        report.append({"index": i, "delta_chars": len(replace) - len(search)})\n    return updated, report\n''',
        replace='''def _tc_apply_blocks(content: str, blocks: list) -> tuple:\n    """Apply strict SEARCH/REPLACE blocks. Each search must occur exactly once."""\n    if not isinstance(blocks, list) or not blocks:\n        raise ValueError("blocks muss eine nicht-leere Liste sein")\n    if len(blocks) > 20:\n        raise ValueError("Zu viele Patch-Blöcke: maximal 20")\n    if len(content.encode("utf-8")) > 500_000:\n        raise ValueError("Datei ist zu groß: maximal 500000 Bytes")\n    updated = content\n    report = []\n    for i, block in enumerate(blocks):\n        search  = block.get("search", "") if isinstance(block, dict) else ""\n        replace = block.get("replace", "") if isinstance(block, dict) else ""\n        if not isinstance(search, str) or not isinstance(replace, str):\n            raise ValueError(f"Block {i}: search/replace müssen Strings sein")\n        if not search:\n            raise ValueError(f"Block {i}: search darf nicht leer sein")\n        if len(search.encode("utf-8")) > 8_000 or len(replace.encode("utf-8")) > 8_000:\n            raise ValueError(f"Block {i}: search/replace überschreitet Größenlimit")\n        count = updated.count(search)\n        if count != 1:\n            raise ValueError(\n                f"Block {i}: search muss genau einmal vorkommen, gefunden: {count}"\n            )\n        updated = updated.replace(search, replace, 1)\n        report.append({"index": i, "match_count": 1, "delta_chars": len(replace) - len(search)})\n    return updated, report\n''',
    ),
    Block(
        search='''        current = _tc_read_github_file(owner, repo, path, ref)\n        before  = current["content"]\n        after, report = _tc_apply_blocks(before, blocks)\n        diff    = _tc_unified_diff(before, after, path)\n''',
        replace='''        expected_sha = _tc_expected_sha(b)\n        current = _tc_read_github_file(owner, repo, path, ref)\n        _tc_assert_expected_sha(current["sha"], expected_sha)\n        before  = current["content"]\n        after, report = _tc_apply_blocks(before, blocks)\n        diff    = _tc_unified_diff(before, after, path)\n''',
    ),
    Block(
        search='''    except PermissionError as e:\n        return jsonify({"error": str(e)}), 403\n    except ValueError as e:\n        return jsonify({"error": str(e)}), 422\n    except Exception as e:\n        return jsonify({"error": str(e)}), 500\n\n\n@app.route("/api/toolchain/create-draft-pr", methods=["POST"])\n''',
        replace='''    except PermissionError as e:\n        return _tc_json_error(e, 403)\n    except ValueError as e:\n        return _tc_json_error(e, 422)\n    except Exception as e:\n        return _tc_json_error(e, 500)\n\n\n@app.route("/api/toolchain/create-draft-pr", methods=["POST"])\n''',
    ),
    Block(
        search='''            except Exception as prev_err:\n                diff, report = str(prev_err), []\n''',
        replace='''            except Exception as prev_err:\n                diff, report = _tc_safe_error(prev_err), []\n''',
    ),
    Block(
        search='''        current  = _tc_read_github_file(owner, repo, path)\n        new_content, report = _tc_apply_blocks(current["content"], blocks)\n''',
        replace='''        expected_sha = _tc_expected_sha(b)\n        current  = _tc_read_github_file(owner, repo, path, b.get("base_branch"))\n        _tc_assert_expected_sha(current["sha"], expected_sha)\n        new_content, report = _tc_apply_blocks(current["content"], blocks)\n''',
    ),
    Block(
        search='''        worker  = b.get("worker_url", _TC_WORKER_URL)\n\n        if not all([owner, repo, path, message, blocks]):\n            return jsonify({"error": "owner, repo, path, message und blocks erforderlich"}), 400\n\n        payload = {"owner": owner, "repo": repo, "path": path, "message": message, "blocks": blocks}\n\n        if not confirm:\n            return jsonify({\n                "sent":    False,\n                "reason":  "confirm=True ist erforderlich",\n                "payload": payload,\n                "worker":  worker,\n            })\n''',
        replace='''        worker  = _TC_WORKER_URL\n\n        if not all([owner, repo, path, message, blocks]):\n            return jsonify({"error": "owner, repo, path, message und blocks erforderlich"}), 400\n\n        _tc_allowed(owner, repo)\n        payload = {\n            "owner": owner,\n            "repo": repo,\n            "path": path,\n            "message": message,\n            "blocks": blocks,\n            "expectedSha": _tc_expected_sha(b),\n            "dryRun": False,\n        }\n\n        if not confirm:\n            return jsonify({\n                "sent":    False,\n                "reason":  "confirm=True ist erforderlich",\n                "write_action": False,\n                "worker":  worker,\n                "block_count": len(blocks),\n            })\n''',
    ),
    Block(
        search='''        _tc_allowed(owner, repo)\n        resp = requests.post(worker, json=payload, timeout=60)\n''',
        replace='''        resp = requests.post(worker, json=payload, timeout=60)\n''',
    ),
)


def apply_blocks(content: str) -> tuple[str, list[dict[str, int]]]:
    updated = content
    report: list[dict[str, int]] = []
    for index, block in enumerate(BLOCKS):
        count = updated.count(block.search)
        if count != 1:
            raise SystemExit(f"Block {index}: expected exactly 1 match, got {count}")
        updated = updated.replace(block.search, block.replace, 1)
        report.append({"index": index, "delta_chars": len(block.replace) - len(block.search)})
    return updated, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    target = Path(args.repo_root) / TARGET
    original = target.read_text(encoding="utf-8")
    patched, report = apply_blocks(original)

    print(f"target={target}")
    print(f"blocks={len(report)}")
    print(f"delta_chars={len(patched) - len(original)}")

    if args.apply:
        target.write_text(patched, encoding="utf-8")
        py_compile.compile(str(target), doraise=True)
        print("applied=true")
        print("py_compile=ok")
    else:
        print("applied=false")
        if args.check:
            temp = target.with_suffix(target.suffix + ".guardrails-check.tmp")
            try:
                temp.write_text(patched, encoding="utf-8")
                py_compile.compile(str(temp), doraise=True)
                print("py_compile=ok")
            finally:
                temp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
