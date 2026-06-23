#!/usr/bin/env bash
# =============================================================================
# apply-external-patches.sh
# =============================================================================
# Apply patches from external local instance and push as PR to main repo
# Usage: ./apply-external-patches.sh <path-to-external-patches> [--dry-run]
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
REPO_OWNER="OuroborosCollective"
REPO_NAME="Sovereign-Studio-ato"
REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"
WORK_DIR="/workspace/release-sync"
PATCHES_DIR="${WORK_DIR}/patches"
EXTRACTED_DIR="${WORK_DIR}/extracted"
BRANCH_NAME="external-patch-$(date +%Y%m%d-%H%M%S)"

# Check for dry-run mode
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_warn "DRY RUN MODE - No changes will be pushed"
fi

# Get patches directory from argument or use default
if [[ -n "${1:-}" && "${1}" != "--dry-run" ]]; then
    PATCHES_INPUT="$1"
else
    PATCHES_INPUT="${WORK_DIR}/patches"
fi

log_info "Repository: ${REPO_URL}"
log_info "Branch: ${BRANCH_NAME}"
log_info "Patches source: ${PATCHES_INPUT}"

# =============================================================================
# Step 1: Clone the repository
# =============================================================================
log_info "Cloning repository..."

rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"

if [[ -d "/workspace/project/Sovereign-Studio-ato/.git" ]]; then
    log_info "Using existing local repo as base..."
    cp -r /workspace/project/Sovereign-Studio-ato "${EXTRACTED_DIR}"
    cd "${EXTRACTED_DIR}"
    git fetch origin
    git checkout main
    git pull origin main
else
    git clone --depth 1 "${REPO_URL}" "${EXTRACTED_DIR}"
    cd "${EXTRACTED_DIR}"
fi

log_success "Repository ready"

# =============================================================================
# Step 2: Find and apply patches
# =============================================================================
log_info "Scanning for patches..."

PATCH_FILES=()

# Check if input is a directory
if [[ -d "${PATCHES_INPUT}" ]]; then
    log_info "Scanning directory: ${PATCHES_INPUT}"
    while IFS= read -r -d '' file; do
        PATCH_FILES+=("$file")
    done < <(find "${PATCHES_INPUT}" -type f \( -name "*.patch" -o -name "*.sh" \) -print0 2>/dev/null || true)
    
    # Also scan for loose patch files in WORK_DIR
    while IFS= read -r -d '' file; do
        PATCH_FILES+=("$file")
    done < <(find "${WORK_DIR}" -maxdepth 1 -type f \( -name "*.patch" -o -name "*.diff" \) -print0 2>/dev/null || true)

# Check if input is a single file
elif [[ -f "${PATCHES_INPUT}" ]]; then
    PATCH_FILES+=("${PATCHES_INPUT}")
fi

if [[ ${#PATCH_FILES[@]} -eq 0 ]]; then
    log_warn "No patch files found in ${PATCHES_INPUT}"
    log_info "Looking for alternative patch locations..."
    
    # Check common locations
    for dir in "/workspace" "/tmp" "$HOME"; do
        while IFS= read -r -d '' file; do
            PATCH_FILES+=("$file")
        done < <(find "$dir" -maxdepth 2 -type f \( -name "*.patch" -o -name "*.diff" \) -newer "${EXTRACTED_DIR}/.git" -print0 2>/dev/null || true)
    done
fi

if [[ ${#PATCH_FILES[@]} -eq 0 ]]; then
    log_error "No patch files found. Please provide:"
    echo "  - A directory containing .patch or .sh files"
    echo "  - A single .patch file"
    exit 1
fi

log_info "Found ${#PATCH_FILES[@]} patch file(s):"
for patch in "${PATCH_FILES[@]}"; do
    echo "  - $(basename "$patch")"
done

# =============================================================================
# Step 3: Create feature branch
# =============================================================================
log_info "Creating feature branch: ${BRANCH_NAME}"
git checkout -b "${BRANCH_NAME}"

# =============================================================================
# Step 4: Apply patches
# =============================================================================
APPLIED_COUNT=0
FAILED_COUNT=0

for patch_file in "${PATCH_FILES[@]}"; do
    log_info "Applying: $(basename "$patch_file")"
    
    if [[ "$patch_file" == *.patch ]] || [[ "$patch_file" == *.diff ]]; then
        # Try to apply as patch
        if git apply --verbose --3way "$patch_file" 2>&1; then
            log_success "Applied: $(basename "$patch_file")"
            ((APPLIED_COUNT++))
        else
            log_warn "Failed to apply patch, trying alternative..."
            if git apply --verbose "$patch_file" --ignore-whitespace 2>&1; then
                log_success "Applied (ignore-whitespace): $(basename "$patch_file")"
                ((APPLIED_COUNT++))
            else
                log_error "Failed: $(basename "$patch_file")"
                ((FAILED_COUNT++))
            fi
        fi
    elif [[ "$patch_file" == *.sh ]]; then
        # Execute shell script in repo context
        log_info "Executing: $(basename "$patch_file")"
        if bash "$patch_file"; then
            log_success "Executed: $(basename "$patch_file")"
            ((APPLIED_COUNT++))
        else
            log_error "Script failed: $(basename "$patch_file")"
            ((FAILED_COUNT++))
        fi
    fi
done

log_info "Patches applied: ${APPLIED_COUNT}, failed: ${FAILED_COUNT}"

# =============================================================================
# Step 5: Show changes
# =============================================================================
if [[ ${APPLIED_COUNT} -gt 0 ]]; then
    log_info "Changes to be committed:"
    git diff --stat
    
    # Commit changes
    git add -A
    git commit -m "Apply external patches

$(date '+%Y-%m-%d %H:%M:%S')

Patches applied:
$(for patch in "${PATCH_FILES[@]}"; do echo "- $(basename "$patch")"; done)

Co-authored-by: Sovereign Studio Patch System <patch-system@sovereign.local>"
    
    log_success "Changes committed"
    
    # =============================================================================
    # Step 6: Push and create PR
    # =============================================================================
    if [[ "${DRY_RUN}" == true ]]; then
        log_warn "DRY RUN - Would push branch and create PR"
        log_info "Branch: ${BRANCH_NAME}"
        log_info "Run without --dry-run to actually push"
    else
        log_info "Pushing branch..."
        git push -u origin "${BRANCH_NAME}" --force-with-lease
        
        # Create PR via GitHub CLI
        if command -v gh &> /dev/null; then
            log_info "Creating Pull Request..."
            gh pr create \
                --repo "${REPO_OWNER}/${REPO_NAME}" \
                --title "External patches - $(date '+%Y-%m-%d')" \
                --body "## External Patch Application

Applied patches from external instance.

### Files Modified
$(git diff --stat origin/main...HEAD | tail -n +2)

### Details
- Applied: ${APPLIED_COUNT} patches
- Failed: ${FAILED_COUNT} patches
- Timestamp: $(date '+%Y-%m-%d %H:%M:%S')

---
_This PR was created by the Sovereign Studio Patch System_" \
                --draft \
                --base main
            
            log_success "Pull Request created!"
        else
            log_warn "GitHub CLI not found. Branch pushed to:"
            log_info "  ${REPO_URL}/compare/${BRANCH_NAME}"
            log_info "Please create PR manually"
        fi
    fi
else
    log_error "No patches were successfully applied"
    exit 1
fi

log_success "Done!"
