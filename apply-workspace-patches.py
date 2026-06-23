#!/usr/bin/env python3
"""
apply-workspace-patches.py
==========================
Apply patches from /workspace directory and push as PR to GitHub.

This script is triggered from the external instance or via shortcut.
It watches /workspace for new patch files and applies them.

Usage:
    python3 apply-workspace-patches.py [--watch] [--dry-run]
    python3 apply-workspace-patches.py /path/to/patches
"""

import argparse
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional

# Colors
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def log_info(msg: str):
    print(f"{BLUE}[INFO]{NC} {msg}")

def log_success(msg: str):
    print(f"{GREEN}[SUCCESS]{NC} {msg}")

def log_warn(msg: str):
    print(f"{YELLOW}[WARN]{NC} {msg}")

def log_error(msg: str):
    print(f"{RED}[ERROR]{NC} {msg}")

# Configuration
REPO_OWNER = "OuroborosCollective"
REPO_NAME = "Sovereign-Studio-ato"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
WORK_DIR = Path("/workspace/release-sync")
PATCHES_DIR = WORK_DIR / "patches"
EXTRACTED_DIR = WORK_DIR / "extracted"


def run_cmd(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    log_info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    if result.stdout:
        for line in result.stdout.strip().split('\n'):
            if line:
                print(f"  {line}")
    if result.stderr:
        for line in result.stderr.strip().split('\n'):
            if line:
                print(f"  {RED}{line}{NC}", file=sys.stderr)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def find_patch_files(search_path: Path) -> List[Path]:
    """Find all patch files in the given path."""
    patches = []
    
    if search_path.is_file():
        if search_path.suffix in ['.patch', '.diff', '.sh']:
            patches.append(search_path)
    elif search_path.is_dir():
        # Find all .patch, .diff, and .sh files
        for pattern in ['*.patch', '*.diff', '*.sh', '*.patchset']:
            patches.extend(search_path.rglob(pattern))
    
    return sorted(set(patches))


def get_repo_info() -> dict:
    """Get current repository info."""
    result = run_cmd(['git', 'remote', 'get-url', 'origin'], check=False)
    remote_url = result.stdout.strip() if result.returncode == 0 else "unknown"
    
    result = run_cmd(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], check=False)
    branch = result.stdout.strip() if result.returncode == 0 else "unknown"
    
    return {
        'remote_url': remote_url,
        'branch': branch,
        'owner': REPO_OWNER,
        'repo': REPO_NAME
    }


def prepare_repository() -> Path:
    """Clone or update the repository."""
    log_info("Preparing repository...")
    
    # Use the existing repo if available
    if Path("/workspace/project/Sovereign-Studio-ato/.git").exists():
        repo_path = Path("/workspace/project/Sovereign-Studio-ato")
        log_info(f"Using existing repo: {repo_path}")
        
        # Fetch latest
        run_cmd(['git', 'fetch', 'origin'], cwd=repo_path)
        run_cmd(['git', 'checkout', 'main'], cwd=repo_path)
        run_cmd(['git', 'pull', 'origin', 'main'], cwd=repo_path)
        
        return repo_path
    
    # Otherwise clone fresh
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    run_cmd(['git', 'clone', '--depth', '1', REPO_URL, str(EXTRACTED_DIR)])
    return EXTRACTED_DIR


def apply_patches(repo_path: Path, patches: List[Path], dry_run: bool = False) -> tuple:
    """Apply patches to the repository."""
    applied = 0
    failed = 0
    applied_files = []
    
    for patch_file in patches:
        log_info(f"Processing: {patch_file.name}")
        
        if patch_file.suffix == '.sh':
            # Execute shell script
            log_info(f"Executing script: {patch_file}")
            try:
                result = subprocess.run(
                    ['bash', str(patch_file)],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    log_success(f"Executed: {patch_file.name}")
                    applied += 1
                else:
                    log_error(f"Script failed: {patch_file.name}")
                    failed += 1
            except subprocess.TimeoutExpired:
                log_error(f"Script timed out: {patch_file.name}")
                failed += 1
        else:
            # Apply as patch
            log_info(f"Applying patch: {patch_file}")
            
            # Try standard apply first
            result = subprocess.run(
                ['git', 'apply', '--verbose', '--3way', str(patch_file)],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Try with ignore whitespace
                result = subprocess.run(
                    ['git', 'apply', '--verbose', str(patch_file), '--ignore-whitespace'],
                    cwd=repo_path,
                    capture_output=True,
                    text=True
                )
            
            if result.returncode == 0:
                log_success(f"Applied: {patch_file.name}")
                applied += 1
                applied_files.append(str(patch_file))
            else:
                log_warn(f"Failed to apply: {patch_file.name}")
                log_warn(f"  Error: {result.stderr[:200] if result.stderr else 'Unknown error'}")
                failed += 1
    
    return applied, failed, applied_files


def commit_and_push(repo_path: Path, applied_files: List[str], dry_run: bool = False) -> Optional[str]:
    """Commit changes and push to remote."""
    branch_name = f"patch-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Check if there are changes
    result = run_cmd(['git', 'status', '--porcelain'], cwd=repo_path, check=False)
    if not result.stdout.strip():
        log_warn("No changes to commit")
        return None
    
    # Create branch
    log_info(f"Creating branch: {branch_name}")
    run_cmd(['git', 'checkout', '-b', branch_name], cwd=repo_path)
    
    # Stage all changes
    run_cmd(['git', 'add', '-A'], cwd=repo_path)
    
    # Create commit message
    patch_names = '\n'.join([f"- {Path(f).name}" for f in applied_files])
    commit_msg = f"""Apply external patches

{datetime.now().isoformat()}

Patches applied:
{patch_names}

Co-authored-by: Sovereign Studio Patch System <patch-system@sovereign.local>
"""
    
    run_cmd(['git', 'commit', '-m', commit_msg], cwd=repo_path)
    log_success("Changes committed")
    
    if dry_run:
        log_warn("DRY RUN - Would push to remote")
        return None
    
    # Push to remote
    log_info("Pushing to remote...")
    run_cmd(['git', 'push', '-u', 'origin', branch_name, '--force-with-lease'], cwd=repo_path)
    
    return branch_name


def create_pr(branch_name: str, repo_path: Path) -> Optional[str]:
    """Create a Pull Request via GitHub CLI."""
    log_info("Creating Pull Request...")
    
    # Try GitHub CLI
    result = subprocess.run(
        ['gh', 'pr', 'create',
         '--repo', f"{REPO_OWNER}/{REPO_NAME}",
         '--title', f"External patches - {datetime.now().strftime('%Y-%m-%d')}",
         '--body', f"""## External Patch Application

Applied patches from external instance.

### Details
- Branch: `{branch_name}`
- Timestamp: {datetime.now().isoformat()}

---
_This PR was created by the Sovereign Studio Patch System_
""",
         '--draft',
         '--base', 'main'
        ],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        pr_url = result.stdout.strip()
        log_success(f"PR created: {pr_url}")
        return pr_url
    
    log_warn("GitHub CLI not available or PR creation failed")
    return None


def main():
    parser = argparse.ArgumentParser(description='Apply workspace patches to repo')
    parser.add_argument('patches', nargs='?', default='/workspace',
                        help='Path to patches directory or file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--output', '-o', default=None,
                        help='Output directory for working files')
    parser.add_argument('--watch', '-w', action='store_true',
                        help='Watch for new patches (not implemented)')
    
    args = parser.parse_args()
    
    log_info("=" * 50)
    log_info("Sovereign Studio - Patch Application")
    log_info("=" * 50)
    log_info(f"Target repo: {REPO_URL}")
    log_info(f"Patch source: {args.patches}")
    log_info(f"Dry run: {args.dry_run}")
    log_info("")
    
    # Get repo info
    repo_info = get_repo_info()
    log_info(f"Current branch: {repo_info['branch']}")
    log_info(f"Remote: {repo_info['remote_url']}")
    
    # Find patches
    patches_path = Path(args.patches)
    if not patches_path.exists():
        # Try /workspace as fallback
        patches_path = Path("/workspace")
    
    patches = find_patch_files(patches_path)
    
    if not patches:
        log_error("No patch files found!")
        log_info(f"Searched in: {patches_path}")
        log_info("Supported formats: .patch, .diff, .sh")
        sys.exit(1)
    
    log_info(f"Found {len(patches)} patch file(s):")
    for p in patches:
        log_info(f"  - {p.name}")
    
    # Prepare repository
    repo_path = prepare_repository()
    
    # Apply patches
    applied, failed, applied_files = apply_patches(repo_path, patches, args.dry_run)
    
    log_info(f"\nPatch results: {applied} applied, {failed} failed")
    
    if applied == 0:
        log_error("No patches were successfully applied")
        sys.exit(1)
    
    # Commit and push
    if not args.dry_run:
        branch_name = commit_and_push(repo_path, applied_files)
        
        if branch_name:
            pr_url = create_pr(branch_name, repo_path)
            
            if pr_url:
                log_success(f"\nPull Request created: {pr_url}")
            else:
                log_info(f"\nBranch pushed: {REPO_URL}/compare/{branch_name}")
                log_info("Create PR manually or use GitHub UI")
    
    log_success("\nDone!")


if __name__ == '__main__':
    main()
