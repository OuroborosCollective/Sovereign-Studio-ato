#!/usr/bin/env bash
set -euo pipefail

# Apply Toolchain backend patch guardrails and publish the result through the
# GitHub REST Contents API as a Draft PR.
#
# This script intentionally writes to a new branch and opens a Draft PR.
# It never pushes directly to main.
#
# Requirements:
#   - bash
#   - curl
#   - python3
#   - base64
#   - GITHUB_TOKEN with repo contents + pull request write permission
#
# Usage:
#   GITHUB_TOKEN=... scripts/patches/apply_toolchain_patch_guardrails_via_github_api.sh
#
# Optional env:
#   REPO_FULL_NAME=OuroborosCollective/Sovereign-Studio-ato
#   BASE_BRANCH=main
#   PATCH_BRANCH=sovereign/apply-toolchain-guardrails
#   TARGET_PATH=scripts/sovereign-backend/app.py
#   COMMIT_MESSAGE='fix(toolchain): apply backend patch guardrails'
#   PR_TITLE='fix(toolchain): apply backend patch guardrails'

REPO_FULL_NAME="${REPO_FULL_NAME:-OuroborosCollective/Sovereign-Studio-ato}"
BASE_BRANCH="${BASE_BRANCH:-main}"
PATCH_BRANCH="${PATCH_BRANCH:-sovereign/apply-toolchain-guardrails}"
TARGET_PATH="${TARGET_PATH:-scripts/sovereign-backend/app.py}"
COMMIT_MESSAGE="${COMMIT_MESSAGE:-fix(toolchain): apply backend patch guardrails}"
PR_TITLE="${PR_TITLE:-fix(toolchain): apply backend patch guardrails}"
PR_BODY="${PR_BODY:-Applies the verified Toolchain backend guardrails patch from scripts/patches/apply_toolchain_patch_guardrails.py.}"
API_BASE="https://api.github.com/repos/${REPO_FULL_NAME}"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GITHUB_TOKEN is required" >&2
  exit 2
fi

if [[ ! -f "scripts/patches/apply_toolchain_patch_guardrails.py" ]]; then
  echo "ERROR: scripts/patches/apply_toolchain_patch_guardrails.py not found" >&2
  exit 2
fi

if [[ ! -f "${TARGET_PATH}" ]]; then
  echo "ERROR: target file not found: ${TARGET_PATH}" >&2
  exit 2
fi

api() {
  local method="$1"
  local url="$2"
  local data_file="${3:-}"
  if [[ -n "${data_file}" ]]; then
    curl --fail-with-body -sS \
      -X "${method}" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      --data-binary "@${data_file}" \
      "${url}"
  else
    curl --fail-with-body -sS \
      -X "${method}" \
      -H "Authorization: Bearer ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      "${url}"
  fi
}

json_get_string() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); path=sys.argv[1].split("."); cur=data
for part in path:
    cur=cur[part]
print(cur)' "$1"
}

json_payload() {
  python3 - "$@" <<'PY'
import json
import sys
pairs = sys.argv[1:]
out = {}
for item in pairs:
    key, value = item.split('=', 1)
    if value == 'true':
        out[key] = True
    elif value == 'false':
        out[key] = False
    else:
        out[key] = value
print(json.dumps(out, ensure_ascii=False))
PY
}

printf '\n== Apply verified local patch ==\n'
python3 scripts/patches/apply_toolchain_patch_guardrails.py --repo-root . --apply
python3 -m py_compile "${TARGET_PATH}"

printf '\n== Resolve base commit ==\n'
base_ref_json="$(api GET "${API_BASE}/git/ref/heads/${BASE_BRANCH}")"
base_sha="$(printf '%s' "${base_ref_json}" | json_get_string object.sha)"
echo "base=${BASE_BRANCH} sha=${base_sha}"

printf '\n== Create patch branch if needed ==\n'
branch_payload="$(mktemp)"
json_payload "ref=refs/heads/${PATCH_BRANCH}" "sha=${base_sha}" > "${branch_payload}"
if api POST "${API_BASE}/git/refs" "${branch_payload}" >/tmp/sovereign-create-ref.json 2>/tmp/sovereign-create-ref.err; then
  echo "created branch ${PATCH_BRANCH}"
else
  if grep -qi 'Reference already exists' /tmp/sovereign-create-ref.err /tmp/sovereign-create-ref.json 2>/dev/null; then
    echo "branch ${PATCH_BRANCH} already exists; continuing"
  else
    cat /tmp/sovereign-create-ref.err >&2 || true
    cat /tmp/sovereign-create-ref.json >&2 || true
    exit 1
  fi
fi
rm -f "${branch_payload}"

printf '\n== Resolve current target file SHA on patch branch ==\n'
encoded_path="$(python3 - <<'PY' "${TARGET_PATH}"
import sys, urllib.parse
print(urllib.parse.quote(sys.argv[1], safe='/'))
PY
)"
file_json="$(api GET "${API_BASE}/contents/${encoded_path}?ref=${PATCH_BRANCH}")"
file_sha="$(printf '%s' "${file_json}" | json_get_string sha)"
echo "target=${TARGET_PATH} sha=${file_sha}"

printf '\n== Upload patched file through Contents API ==\n'
content_b64="$(base64 -w 0 "${TARGET_PATH}" 2>/dev/null || base64 "${TARGET_PATH}" | tr -d '\n')"
update_payload="$(mktemp)"
python3 - <<'PY' "${COMMIT_MESSAGE}" "${content_b64}" "${file_sha}" "${PATCH_BRANCH}" > "${update_payload}"
import json
import sys
print(json.dumps({
    'message': sys.argv[1],
    'content': sys.argv[2],
    'sha': sys.argv[3],
    'branch': sys.argv[4],
}, ensure_ascii=False))
PY
api PUT "${API_BASE}/contents/${encoded_path}" "${update_payload}" >/tmp/sovereign-update-file.json
rm -f "${update_payload}"
commit_sha="$(cat /tmp/sovereign-update-file.json | json_get_string commit.sha)"
echo "commit=${commit_sha}"

printf '\n== Open Draft PR ==\n'
pr_payload="$(mktemp)"
python3 - <<'PY' "${PR_TITLE}" "${PATCH_BRANCH}" "${BASE_BRANCH}" "${PR_BODY}" > "${pr_payload}"
import json
import sys
print(json.dumps({
    'title': sys.argv[1],
    'head': sys.argv[2],
    'base': sys.argv[3],
    'draft': True,
    'body': sys.argv[4],
}, ensure_ascii=False))
PY
if api POST "${API_BASE}/pulls" "${pr_payload}" >/tmp/sovereign-create-pr.json 2>/tmp/sovereign-create-pr.err; then
  pr_url="$(cat /tmp/sovereign-create-pr.json | json_get_string html_url)"
  echo "draft_pr=${pr_url}"
else
  if grep -qi 'A pull request already exists' /tmp/sovereign-create-pr.err /tmp/sovereign-create-pr.json 2>/dev/null; then
    echo "Draft PR already exists for ${PATCH_BRANCH}; inspect GitHub for the open PR."
  else
    cat /tmp/sovereign-create-pr.err >&2 || true
    cat /tmp/sovereign-create-pr.json >&2 || true
    exit 1
  fi
fi
rm -f "${pr_payload}"

printf '\nDone. No direct main write was performed.\n'
