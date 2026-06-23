#!/usr/bin/env bash
# =============================================================================
# download-repo-zip.sh
# =============================================================================
# Download Sovereign Studio as a 7MB ZIP and apply external patches
# 
# This script provides a shortcut to:
# 1. Download the latest repo as ZIP from GitHub
# 2. Extract and apply patches from /workspace
# 3. Push changes as a PR
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
REPO_OWNER="OuroborosCollective"
REPO_NAME="Sovereign-Studio-ato"
REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}"
WORK_DIR="/workspace/release-sync"
PATCHES_DIR="/workspace"
BRANCH_NAME="patch-$(date +%Y%m%d-%H%M%S)"

# Parse arguments
SHOW_HELP=false
DRY_RUN=false
DOWNLOAD_ONLY=false
APPLY_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            SHOW_HELP=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --download-only)
            DOWNLOAD_ONLY=true
            shift
            ;;
        --apply-only)
            APPLY_ONLY=true
            shift
            ;;
        --branch)
            BRANCH_NAME="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            SHOW_HELP=true
            ;;
    esac
done

if [[ "${SHOW_HELP}" == true ]]; then
    cat << 'EOF'
Usage: ./download-repo-zip.sh [OPTIONS]

Download Sovereign Studio repository as ZIP and apply patches from /workspace.

OPTIONS:
  --help, -h         Show this help message
  --dry-run           Show what would be done without making changes
  --download-only     Only download and extract the ZIP (no patches)
  --apply-only        Only apply patches (assume ZIP already extracted)
  --branch <name>     Custom branch name for the PR

EXAMPLES:
  # Download repo and apply patches
  ./download-repo-zip.sh

  # Download only
  ./download-repo-zip.sh --download-only

  # Apply patches to already downloaded repo
  ./download-repo-zip.sh --apply-only

  # Dry run to see what would happen
  ./download-repo-zip.sh --dry-run

PATCH SOURCES:
  - /workspace/*.patch
  - /workspace/*.diff
  - /workspace/*.sh
  - /workspace/patches/*

OUTPUT:
  - Draft Pull Request on GitHub
  - Branch pushed to origin

EOF
    exit 0
fi

log_info "=========================================="
log_info " Sovereign Studio - Repo Sync Tool"
log_info "=========================================="
echo ""
log_info "Repository: ${REPO_URL}"
log_info "Work Dir:   ${WORK_DIR}"
log_info "Patches:    ${PATCHES_DIR}"
log_info "Branch:     ${BRANCH_NAME}"
[[ "${DRY_RUN}" == true ]] && log_warn "DRY RUN MODE"
echo ""

# =============================================================================
# Step 1: Download and Extract ZIP (unless --apply-only)
# =============================================================================
if [[ "${APPLY_ONLY}" == false ]]; then
    log_info "Step 1: Downloading repository..."
    
    # Create work directory
    mkdir -p "${WORK_DIR}"
    
    # Download ZIP from GitHub
    ZIP_URL="${REPO_URL}/archive/refs/heads/main.zip"
    ZIP_FILE="${WORK_DIR}/repo.zip"
    
    log_info "Downloading: ${ZIP_URL}"
    
    if curl -L -o "${ZIP_FILE}" "${ZIP_URL}" --progress-bar; then
        log_success "Downloaded: $(du -h "${ZIP_FILE}" | cut -f1)"
    else
        log_error "Download failed!"
        exit 1
    fi
    
    # Extract
    log_info "Extracting..."
    cd "${WORK_DIR}"
    rm -rf extracted
    unzip -q repo.zip
    mv "Sovereign-Studio-ato-main" extracted
    cd extracted
    
    log_success "Extracted to: ${WORK_DIR}/extracted"
    
    # Initialize git
    log_info "Initializing git..."
    git init -q
    git remote add origin "${REPO_URL}"
    git fetch origin main
    git checkout -B main origin/main
    
    log_success "Git initialized"
else
    log_info "Step 1: Skipping download (--apply-only)"
    if [[ ! -d "${WORK_DIR}/extracted" ]]; then
        log_error "No extracted repo found at ${WORK_DIR}/extracted"
        log_info "Run without --apply-only first"
        exit 1
    fi
    cd "${WORK_DIR}/extracted"
fi

# =============================================================================
# Step 2: Find patches in /workspace
# =============================================================================
log_info ""
log_info "Step 2: Scanning for patches in ${PATCHES_DIR}..."

PATCH_FILES=()

# Scan workspace root
while IFS= read -r -d '' file; do
    PATCH_FILES+=("$file")
done < <(find "${PATCHES_DIR}" -maxdepth 1 -type f \( -name "*.patch" -o -name "*.diff" \) -print0 2>/dev/null || true)

# Scan patches subdirectory
if [[ -d "${PATCHES_DIR}/patches" ]]; then
    while IFS= read -r -d '' file; do
        PATCH_FILES+=("$file")
    done < <(find "${PATCHES_DIR}/patches" -type f \( -name "*.patch" -o -name "*.diff" -o -name "*.sh" \) -print0 2>/dev/null || true)
fi

# Remove duplicates
IFS=$'\n' PATCH_FILES=($(printf "%s\n" "${PATCH_FILES[@]}" | sort -u))
IFS=$' \t\n'

if [[ ${#PATCH_FILES[@]} -eq 0 ]]; then
    log_warn "No patch files found!"
    log_info "Place .patch or .diff files in:"
    echo "  - ${PATCHES_DIR}/*.patch"
    echo "  - ${PATCHES_DIR}/patches/*.patch"
    
    if [[ "${DOWNLOAD_ONLY}" == true ]]; then
        log_success "Download complete (no patches to apply)"
        exit 0
    fi
    
    log_info "Continuing anyway (will create clean branch)..."
else
    log_success "Found ${#PATCH_FILES[@]} patch file(s):"
    for patch in "${PATCH_FILES[@]}"; do
        echo "  - $(basename "$patch")"
    done
fi

if [[ "${DOWNLOAD_ONLY}" == true ]]; then
    log_success "Download complete!"
    exit 0
fi

# =============================================================================
# Step 3: Create branch and apply patches
# =============================================================================
log_info ""
log_info "Step 3: Creating branch and applying patches..."

git checkout -B "${BRANCH_NAME}"

APPLIED=0
FAILED=0

for patch_file in "${PATCH_FILES[@]}"; do
    log_info "Applying: $(basename "$patch_file")"
    
    if [[ "$patch_file" == *.sh ]]; then
        # Execute script
        if bash "$patch_file"; then
            log_success "Executed: $(basename "$patch_file")"
            ((APPLIED++))
        else
            log_error "Script failed: $(basename "$patch_file")"
            ((FAILED++))
        fi
    else
        # Apply patch
        if git apply --verbose --3way "$patch_file" 2>&1; then
            log_success "Applied: $(basename "$patch_file")"
            ((APPLIED++))
        else
            # Try without 3-way
            if git apply --verbose "$patch_file" --ignore-whitespace 2>&1; then
                log_success "Applied (ignore-whitespace): $(basename "$patch_file")"
                ((APPLIED++))
            else
                log_error "Failed: $(basename "$patch_file")"
                ((FAILED++))
            fi
        fi
    fi
done

log_info "Patches applied: ${APPLIED}, failed: ${FAILED}"

# =============================================================================
# Step 4: Show changes and commit
# =============================================================================
log_info ""
log_info "Step 4: Committing changes..."

if [[ ${APPLIED} -gt 0 ]]; then
    CHANGES=$(git status --porcelain)
    
    if [[ -n "${CHANGES}" ]]; then
        log_info "Changes:"
        git diff --stat
        
        git add -A
        
        # Generate commit message
        cat > .git/COMMIT_MSG << EOF
Apply external patches

Date: $(date '+%Y-%m-%d %H:%M:%S')

Patches applied: ${APPLIED}
Patches failed: ${FAILED}

Files:
$(git diff --stat origin/main...HEAD | tail -n +2)

Co-authored-by: Sovereign Studio Patch System <patch-system@sovereign.local>
EOF
        
        git commit -F .git/COMMIT_MSG
        log_success "Committed"
    else
        log_warn "No changes to commit"
        exit 0
    fi
else
    log_warn "No patches applied, nothing to commit"
    exit 0
fi

# =============================================================================
# Step 5: Push and create PR
# =============================================================================
log_info ""
log_info "Step 5: Pushing to remote..."

if [[ "${DRY_RUN}" == true ]]; then
    log_warn "DRY RUN - Would push and create PR"
    echo ""
    log_info "Branch: ${BRANCH_NAME}"
    log_info "Commits: $(git log --oneline origin/main..HEAD | wc -l)"
    log_info "Files changed: $(git diff --stat origin/main..HEAD | tail -1)"
    exit 0
fi

# Push
git push -u origin "${BRANCH_NAME}" --force-with-lease

log_success "Pushed to: origin/${BRANCH_NAME}"

# Create PR via GitHub CLI
log_info ""
log_info "Step 6: Creating Pull Request..."

if command -v gh &> /dev/null; then
    PR_URL=$(gh pr create \
        --repo "${REPO_OWNER}/${REPO_NAME}" \
        --title "External patches - $(date '+%Y-%m-%d')" \
        --body "$(cat << 'PREOF'
## External Patch Application

Applied patches from external/local instance.

### Summary
- Patches applied: **APPLIED_COUNT**
- Patches failed: **FAILED_COUNT**

### Changes
<!-- This will be filled with git diff stats -->

---
_Auto-generated by Sovereign Studio Patch System_
PREOF
    )" \
        --draft \
        --base main 2>&1)
    
    # Replace placeholders
    PR_URL=$(echo "${PR_URL}" | sed "s/APPLIED_COUNT/${APPLIED}/g" | sed "s/FAILED_COUNT/${FAILED}/g")
    
    log_success "Pull Request created!"
    echo ""
    echo -e "${CYAN}========================================${NC}"
    echo -e "${GREEN}  PR URL: ${PR_URL}${NC}"
    echo -e "${CYAN}========================================${NC}"
else
    log_warn "GitHub CLI (gh) not found"
    echo ""
    echo -e "${CYAN}========================================${NC}"
    log_info "Branch pushed. Create PR manually:"
    echo "  ${REPO_URL}/compare/${BRANCH_NAME}"
    echo -e "${CYAN}========================================${NC}"
fi

log_info ""
log_success "Done!"
