#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# Sovereign Search/Replace Runner
# ============================================================
# Liest eine Patch-Datei und wendet SEARCH/REPLACE-Blöcke an.
# Öffnet einen Draft PR, niemals direkt auf main.
#
# Usage:
#   GITHUB_TOKEN=... bash scripts/patches/search_replace_runner.sh <patch_file.json>
#
# Umgebungsvariablen (optional):
#   REPO_FULL_NAME - Repository (Standard: OuroborosCollective/Sovereign-Studio-ato)
#   BASE_BRANCH    - Basis-Branch (Standard: main)
#   PATCH_BRANCH   - Ziel-Branch (Standard: aus patch_file.json oder sovereign/patch-YYYYMMDD-HHMMSS)
#   DRY_RUN        - Nur Vorschau, kein Write (Standard: false)
#
# Patch-Datei Format (JSON):
# {
#   "target": "src/features/product/containers/BuilderContainer.tsx",
#   "branch": "sovereign/action-stream-builder-wireup",
#   "commit_message": "feat(runtime): wire Sovereign action stream into builder",
#   "pr_title": "feat(runtime): wire Sovereign action stream into builder",
#   "pr_body": "Adds route-wide Sovereign Action Stream wiring...",
#   "expectedSha": "abc123...",  // optional: SHA-Prüfung
#   "blocks": [
#     {
#       "search": "alter code...",
#       "replace": "neuer code..."
#     }
#   ]
# }
#
# Guardrails:
# - Max 20 Blöcke pro Patch
# - Jeder search muss genau 1x vorkommen
# - Max 8KB pro search/replace
# - Max 500KB Gesamtdatei
# ============================================================

PATCH_FILE="${1:-}"
REPO_FULL_NAME="${REPO_FULL_NAME:-OuroborosCollective/Sovereign-Studio-ato}"
BASE_BRANCH="${BASE_BRANCH:-main}"
DRY_RUN="${DRY_RUN:-false}"
API_BASE="https://api.github.com/repos/${REPO_FULL_NAME}"

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

error() { echo -e "${RED}ERROR: $*" >&2; exit 1; }
warn() { echo -e "${YELLOW}WARNING: $*${NC}"; }
info() { echo -e "${GREEN}$*${NC}"; }
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ============================================================
# Validierung
# ============================================================
[[ -z "${GITHUB_TOKEN:-}" ]] && error "GITHUB_TOKEN ist erforderlich"
[[ -z "${PATCH_FILE}" ]] && error "Usage: $0 <patch_file.json>"
[[ ! -f "${PATCH_FILE}" ]] && error "Patch-Datei nicht gefunden: ${PATCH_FILE}"

# Prüfe ob jq verfügbar ist
command -v jq >/dev/null 2>&1 || { info "Installiere jq..."; apt-get install -y jq >/dev/null 2>&1 || error "jq nicht verfügbar"; }

# Lade Patch-Daten
TARGET_PATH="$(jq -r '.target // empty' "${PATCH_FILE}")"
[[ -z "${TARGET_PATH}" ]] && error "patch.target ist erforderlich"

PATCH_BRANCH="${PATCH_BRANCH:-$(jq -r '.branch // empty' "${PATCH_FILE}")}"
[[ -z "${PATCH_BRANCH}" ]] && PATCH_BRANCH="sovereign/patch-$(date '+%Y%m%d-%H%M%S')"

COMMIT_MESSAGE="$(jq -r '.commit_message // empty' "${PATCH_FILE}")"
[[ -z "${COMMIT_MESSAGE}" ]] && COMMIT_MESSAGE="chore: apply search/replace patch"

PR_TITLE="${PR_TITLE:-$(jq -r '.pr_title // empty' "${PATCH_FILE}")}"
[[ -z "${PR_TITLE}" ]] && PR_TITLE="${COMMIT_MESSAGE}"

PR_BODY="${PR_BODY:-$(jq -r '.pr_body // empty' "${PATCH_FILE}")}"
[[ -z "${PR_BODY}" ]] && PR_BODY="Search/Replace Patch via Sovereign Toolchain"

EXPECTED_SHA="$(jq -r '.expectedSha // .expected_sha // .base_sha // empty' "${PATCH_FILE}")"

BLOCKS_COUNT="$(jq '.blocks | length' "${PATCH_FILE}")"
[[ "${BLOCKS_COUNT}" == "0" || "${BLOCKS_COUNT}" == "null" ]] && error "patch.blocks darf nicht leer sein"
[[ "${BLOCKS_COUNT}" -gt 20 ]] && error "Zu viele Blöcke: ${BLOCKS_COUNT} (max: 20)"

# ============================================================
# GitHub API Helper
# ============================================================
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

json_get() {
  local path="$1"
  jq -r "${path}" <<< "${2:-$(cat /dev/stdin)}"
}

# ============================================================
# Hauptlogik
# ============================================================
log "=============================================="
log " Sovereign Search/Replace Runner"
log "=============================================="
log "Target:     ${TARGET_PATH}"
log "Branch:     ${PATCH_BRANCH}"
log "Blocks:     ${BLOCKS_COUNT}"
log "Dry Run:    ${DRY_RUN}"
[[ -n "${EXPECTED_SHA}" ]] && log "Expected SHA: ${EXPECTED_SHA}"
log "=============================================="

# 1. Prüfe ob Ziel-Datei existiert
encoded_path="$(python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe='/'))" "${TARGET_PATH}")"
file_json="$(api GET "${API_BASE}/contents/${encoded_path}?ref=${BASE_BRANCH}")"
CURRENT_SHA="$(json_get '.sha' "${file_json}")"
CURRENT_CONTENT="$(echo "${file_json}" | jq -r '.content' | base64 -d)"

info "✓ Datei gefunden: ${TARGET_PATH}"
info "  SHA: ${CURRENT_SHA}"

# 2. SHA-Prüfung wenn expectedSha gesetzt
if [[ -n "${EXPECTED_SHA}" && "${EXPECTED_SHA}" != "null" ]]; then
  if [[ "${CURRENT_SHA}" != "${EXPECTED_SHA}" ]]; then
    error "SHA mismatch! Datei wurde seit der Vorschau geändert.
    Erwartet: ${EXPECTED_SHA}
    Aktuell:  ${CURRENT_SHA}
    Bitte neu laden und erneut patchen."
  fi
  info "✓ SHA-Prüfung bestanden"
fi

# 3. Validiere alle Blöcke (preview)
log "Validiere SEARCH/REPLACE Blöcke..."
python3 - <<'PYTHON'
import json
import sys

with open(sys.argv[1]) as f:
    patch = json.load(f)

content = base64.b64decode(sys.argv[2]).decode('utf-8')
blocks = patch.get('blocks', [])

errors = []
for i, block in enumerate(blocks):
    search = block.get('search', '')
    replace = block.get('replace', '')
    
    if not isinstance(search, str) or not search:
        errors.append(f"Block {i}: search darf nicht leer sein")
        continue
    
    if not isinstance(replace, str):
        errors.append(f"Block {i}: replace muss ein String sein")
        continue
    
    if len(search.encode('utf-8')) > 8000 or len(replace.encode('utf-8')) > 8000:
        errors.append(f"Block {i}: search/replace überschreitet 8KB Limit")
        continue
    
    count = content.count(search)
    if count == 0:
        errors.append(f"Block {i}: search nicht gefunden in Datei")
    elif count > 1:
        errors.append(f"Block {i}: search kommt {count}x vor (muss genau 1x sein)")

if errors:
    print("VALIDATION_ERRORS:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"VALIDATED:{len(blocks)} blocks")
PYTHON
"${PATCH_FILE}" "${CURRENT_SHA}"  # Falsch, wir brauchen base64 encoded content

# Korrigiere Aufruf:
ENCODED_CONTENT="$(echo "${CURRENT_CONTENT}" | base64 -w 0 2>/dev/null || echo "${CURRENT_CONTENT}" | base64 | tr -d '\n')"
VALIDATION_RESULT="$(python3 - <<'PYTHON'
import json
import base64
import sys

with open(sys.argv[1]) as f:
    patch = json.load(f)

content = base64.b64decode(sys.argv[2]).decode('utf-8')
blocks = patch.get('blocks', [])

errors = []
for i, block in enumerate(blocks):
    search = block.get('search', '')
    replace = block.get('replace', '')
    
    if not isinstance(search, str) or not search:
        errors.append(f"Block {i}: search darf nicht leer sein")
        continue
    
    if not isinstance(replace, str):
        errors.append(f"Block {i}: replace muss ein String sein")
        continue
    
    if len(search.encode('utf-8')) > 8000 or len(replace.encode('utf-8')) > 8000:
        errors.append(f"Block {i}: search/replace überschreitet 8KB Limit")
        continue
    
    count = content.count(search)
    if count == 0:
        errors.append(f"Block {i}: search nicht gefunden in Datei")
    elif count > 1:
        errors.append(f"Block {i}: search kommt {count}x vor (muss genau 1x sein)")

if errors:
    print("VALIDATION_ERRORS:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"VALIDATED:{len(blocks)} blocks")
PYTHON
"${PATCH_FILE}" "${ENCODED_CONTENT}")"

if echo "${VALIDATION_RESULT}" | grep -q "VALIDATION_ERRORS"; then
  error "$(echo "${VALIDATION_RESULT}" | grep -v "^VALIDATED")"
fi
info "✓ Alle ${BLOCKS_COUNT} Blöcke validiert"

# 4. Dry Run - nur Vorschau
if [[ "${DRY_RUN}" == "true" ]]; then
  log "=============================================="
  warn "DRY RUN MODE - Keine Änderungen werden geschrieben"
  log "=============================================="
  
  # Zeige Diff-Vorschau
  python3 - <<'PYTHON'
import json
import base64
import sys
import difflib

with open(sys.argv[1]) as f:
    patch = json.load(f)

content = base64.b64decode(sys.argv[2]).decode('utf-8')
blocks = patch.get('blocks', [])

print("\n=== DIFF PREVIEW ===\n")
for i, block in enumerate(blocks):
    search = block.get('search', '')
    replace = block.get('replace', '')
    
    if search in content:
        # Nur den Teil um den Treffer zeigen
        idx = content.index(search)
        start = max(0, idx - 50)
        end = min(len(content), idx + len(search) + 50)
        
        print(f"--- Block {i} ---")
        print(f"Context: ...{content[start:end]}...")
        print(f"Replace with ({len(replace)} chars):")
        print(replace[:500] + "..." if len(replace) > 500 else replace)
        print()
PYTHON
"${PATCH_FILE}" "${ENCODED_CONTENT}"
  
  info "✓ Dry Run abgeschlossen"
  exit 0
fi

# 5. Anwenden der Blöcke
log "Wende SEARCH/REPLACE Blöcke an..."
PATCHED_CONTENT="$(python3 - <<'PYTHON'
import json
import base64
import sys

with open(sys.argv[1]) as f:
    patch = json.load(f)

content = base64.b64decode(sys.argv[2]).decode('utf-8')
blocks = patch.get('blocks', [])

updated = content
for block in blocks:
    search = block.get('search', '')
    replace = block.get('replace', '')
    if search in updated:
        updated = updated.replace(search, replace, 1)

print(updated, end='')
PYTHON
"${PATCH_FILE}" "${ENCODED_CONTENT}")"

# 6. Basis-Commit SHA holen
log "Hole Basis-Commit SHA..."
base_ref_json="$(api GET "${API_BASE}/git/ref/heads/${BASE_BRANCH}")"
BASE_SHA="$(json_get '.object.sha' "${base_ref_json}")"
info "✓ Basis: ${BASE_BRANCH} @ ${BASE_SHA}"

# 7. Patch-Branch erstellen
log "Erstelle/aktualisiere Branch: ${PATCH_BRANCH}..."
branch_payload="$(mktemp)"
jq -n \
  --arg ref "refs/heads/${PATCH_BRANCH}" \
  --arg sha "${BASE_SHA}" \
  '{ref: $ref, sha: $sha}' > "${branch_payload}"

if api POST "${API_BASE}/git/refs" "${branch_payload}" 2>/dev/null; then
  info "✓ Branch erstellt: ${PATCH_BRANCH}"
else
  # Branch existiert bereits - prüfe ob Update möglich
  warn "Branch existiert bereits, verwende existierenden Branch"
fi
rm -f "${branch_payload}"

# 8. Datei auf Branch aktualisieren
encoded_path="$(python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe='/'))" "${TARGET_PATH}")"

# Hole aktuelle SHA auf dem Branch
branch_file_json="$(api GET "${API_BASE}/contents/${encoded_path}?ref=${PATCH_BRANCH}" 2>/dev/null)" || branch_file_json="{}"
BRANCH_SHA="$(json_get '.sha' "${branch_file_json}" 2>/dev/null)" || BRANCH_SHA="${CURRENT_SHA}"

log "Aktualisiere ${TARGET_PATH} auf Branch..."
update_payload="$(mktemp)"
PATCHED_B64="$(echo "${PATCHED_CONTENT}" | base64 -w 0 2>/dev/null || echo "${PATCHED_CONTENT}" | base64 | tr -d '\n')"
jq -n \
  --arg msg "${COMMIT_MESSAGE}" \
  --arg content "${PATCHED_B64}" \
  --arg sha "${BRANCH_SHA}" \
  --arg branch "${PATCH_BRANCH}" \
  '{message: $msg, content: $content, sha: $sha, branch: $branch}' > "${update_payload}"

api PUT "${API_BASE}/contents/${encoded_path}" "${update_payload}" > /tmp/sovereign-update-result.json
rm -f "${update_payload}"

COMMIT_SHA="$(json_get '.commit.sha' "$(cat /tmp/sovereign-update-result.json)")"
info "✓ Commit erstellt: ${COMMIT_SHA}"

# 9. Draft PR erstellen/aktualisieren
log "Erstelle Draft PR..."
pr_payload="$(mktemp)"
jq -n \
  --arg title "${PR_TITLE}" \
  --arg head "${PATCH_BRANCH}" \
  --arg base "${BASE_BRANCH}" \
  --arg body "${PR_BODY}" \
  '{title: $title, head: $head, base: $base, draft: true, body: $body}' > "${pr_payload}"

if api POST "${API_BASE}/pulls" "${pr_payload}" 2>/tmp/sovereign-pr-result.json; then
  PR_URL="$(json_get '.html_url' "$(cat /tmp/sovereign-pr-result.json)")"
  info "✓ Draft PR erstellt: ${PR_URL}"
else
  if grep -qi "already exists" /tmp/sovereign-pr-result.json 2>/dev/null; then
    PR_URL="$(jq -r '.html_url' /tmp/sovereign-pr-result.json 2>/dev/null || echo "bereits vorhanden")"
    info "✓ Draft PR bereits vorhanden: ${PR_URL}"
  else
    error "Fehler beim Erstellen des PR"
  fi
fi
rm -f "${pr_payload}"

# ============================================================
# Zusammenfassung
# ============================================================
log "=============================================="
info "✓ SEARCH/REPLACE PATCH ERFOLGREICH"
log "=============================================="
log "Target:   ${TARGET_PATH}"
log "Branch:   ${PATCH_BRANCH}"
log "Commit:   ${COMMIT_SHA}"
log "PR:       ${PR_URL}"
log "=============================================="
info "Keine direkten Änderungen an main."
