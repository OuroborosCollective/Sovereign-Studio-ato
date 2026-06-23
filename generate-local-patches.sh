#!/usr/bin/env bash
# =============================================================================
# generate-local-patches.sh
# =============================================================================
# Generate patches from local changes for external application
# This script is meant to be run in the LOCAL EXTERNAL INSTANCE
# Usage: ./generate-local-patches.sh [--output-dir <dir>] [--all]
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
OUTPUT_DIR="${PATCH_OUTPUT_DIR:-./patches-to-share}"
INCLUDE_UNTRACKED=false
INCLUDE_ALL=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --all)
            INCLUDE_ALL=true
            shift
            ;;
        --untracked)
            INCLUDE_UNTRACKED=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output-dir <dir>   Output directory (default: ./patches-to-share)"
            echo "  --all               Include all changes including uncommitted"
            echo "  --untracked         Include untracked files"
            echo "  --help, -h          Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

log_info "Output directory: ${OUTPUT_DIR}"

# Create output directory
mkdir -p "${OUTPUT_DIR}"

# Detect if we're in a git repo
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    log_error "Not in a git repository"
    exit 1
fi

# Get repo info
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "unknown")
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

log_info "Repository: ${REPO_NAME}"
log_info "Remote: ${REMOTE_URL}"

# =============================================================================
# Generate patches from commits not in main
# =============================================================================
log_info "Checking for unpushed commits..."

# Find the main branch
MAIN_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
if [[ "${MAIN_BRANCH}" != "main" ]]; then
    # Check if there's a main branch
    if git show-ref --quiet refs/heads/main 2>/dev/null; then
        MAIN_BRANCH="main"
    elif git show-ref --quiet refs/heads/master 2>/dev/null; then
        MAIN_BRANCH="master"
    fi
fi

log_info "Base branch: ${MAIN_BRANCH}"

# Get commits not in main
COMMIT_COUNT=$(git log "${MAIN_BRANCH}..HEAD" --oneline 2>/dev/null | wc -l)

if [[ ${COMMIT_COUNT} -gt 0 ]]; then
    log_info "Found ${COMMIT_COUNT} unpushed commit(s)"
    
    PATCH_FILE="${OUTPUT_DIR}/${REPO_NAME}-commits-${TIMESTAMP}.patch"
    git format-patch "${MAIN_BRANCH}" --stdout > "${PATCH_FILE}"
    log_success "Generated: ${PATCH_FILE}"
else
    log_warn "No unpushed commits found"
fi

# =============================================================================
# Generate diff of staged changes
# =============================================================================
if ! git diff --cached --stat &>/dev/null; then
    if [[ -n "$(git diff --cached --name-only)" ]]; then
        STAGED_PATCH="${OUTPUT_DIR}/${REPO_NAME}-staged-${TIMESTAMP}.patch"
        git diff --cached > "${STAGED_PATCH}"
        log_success "Generated staged changes: ${STAGED_FILE}"
    fi
fi

# =============================================================================
# Generate diff of unstaged changes
# =============================================================================
if [[ -n "$(git diff --name-only)" ]]; then
    UNSTAGED_PATCH="${OUTPUT_DIR}/${REPO_NAME}-unstaged-${TIMESTAMP}.patch"
    git diff > "${UNSTAGED_PATCH}"
    log_success "Generated unstaged changes: ${UNSTAGED_PATCH}"
fi

# =============================================================================
# Generate patches for new/untracked files
# =============================================================================
if [[ "${INCLUDE_UNTRACKED}" == true ]] || [[ "${INCLUDE_ALL}" == true ]]; then
    UNTRACKED_FILES=$(git ls-files --others --exclude-standard)
    
    if [[ -n "${UNTRACKED_FILES}" ]]; then
        UNTRACKED_ARCHIVE="${OUTPUT_DIR}/${REPO_NAME}-new-files-${TIMESTAMP}.tar.gz"
        
        # Create archive of new files
        git ls-files --others --exclude-standard | tar -czf "${UNTRACKED_ARCHIVE}" -T -
        
        log_success "Generated new files archive: ${UNTRACKED_ARCHIVE}"
        
        # Also create a manifest
        MANIFEST="${OUTPUT_DIR}/${REPO_NAME}-new-files-${TIMESTAMP}.manifest"
        echo "# New files since last commit" > "${MANIFEST}"
        echo "# Generated: $(date)" >> "${MANIFEST}"
        echo "" >> "${MANIFEST}"
        git ls-files --others --exclude-standard >> "${MANIFEST}"
        
        log_success "Generated file manifest: ${MANIFEST}"
    fi
fi

# =============================================================================
# Generate complete diff if requested
# =============================================================================
if [[ "${INCLUDE_ALL}" == true ]]; then
    FULL_DIFF="${OUTPUT_DIR}/${REPO_NAME}-full-diff-${TIMESTAMP}.diff"
    git diff HEAD > "${FULL_DIFF}"
    log_success "Generated full diff: ${FULL_DIFF}"
fi

# =============================================================================
# Create summary file
# =============================================================================
SUMMARY="${OUTPUT_DIR}/${REPO_NAME}-patch-summary-${TIMESTAMP}.txt"
cat > "${SUMMARY}" << EOF
# Patch Summary
# Generated: $(date)
# Repository: ${REPO_NAME}
# Remote: ${REMOTE_URL}
# Branch: ${MAIN_BRANCH}

UNPUSHED COMMITS: ${COMMIT_COUNT}
EOF

echo "" >> "${SUMMARY}"
echo "FILES GENERATED:" >> "${SUMMARY}"
ls -la "${OUTPUT_DIR}"/*.patch "${OUTPUT_DIR}"/*.diff "${OUTPUT_DIR}"/*.tar.gz 2>/dev/null | awk '{print "  " $9 " (" $5 " bytes)"}' >> "${SUMMARY}" || true

log_success "Generated summary: ${SUMMARY}"

# =============================================================================
# Output instructions
# =============================================================================
echo ""
log_info "=========================================="
log_info "Patch files generated in:"
log_info "  ${OUTPUT_DIR}"
log_info "=========================================="
echo ""
log_info "To apply these patches:"
echo ""
echo "  1. Copy the patches to the main instance:"
echo "     rsync -av ${OUTPUT_DIR}/ user@main-server:/workspace/release-sync/patches/"
echo ""
echo "  2. Or mount ${OUTPUT_DIR} to the main instance"
echo ""
echo "  3. Run the apply script:"
echo "     ./apply-external-patches.sh ${OUTPUT_DIR}"
echo ""
echo "  4. Or use the shortcut in the main instance UI"
echo ""
echo "=========================================="

# Create a ready-to-use package
PACKAGE_NAME="${OUTPUT_DIR}/${REPO_NAME}-patches-${TIMESTAMP}.tar.gz"
tar -czf "${PACKAGE_NAME}" -C "${OUTPUT_DIR}" .

log_success "Package created: ${PACKAGE_NAME}"
echo ""
log_info "Share this file with the main instance"
