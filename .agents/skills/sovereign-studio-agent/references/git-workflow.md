# Git Workflow Reference

This document provides guidance on the Git workflow for Sovereign Studio development, including commit conventions, issue management, and verification gates.

## Patch Application Workflow

### Step 1: Analyze the Patch Bundle

When receiving a patch (`.zip` file):

1. **Extract using Python** (avoids missing `unzip`):
   ```bash
   python3 -c "import zipfile; zipfile.ZipFile('patch.zip').extractall('extracted')"
   ```

2. **Read patch instructions**:
   - Check for `APPLY_*.md` or `*_EXTERNAL_AGENT_PROMPT.md`
   - Identify which files to replace vs. modify

3. **Check current main state**:
   ```bash
   git fetch origin main && git pull origin main
   ```

### Step 2: Apply Changes

For each file:

1. **Compare with existing** to understand diff scope
2. **Make surgical edits** rather than wholesale replacements
3. **Preserve local style** (quote style, import order)

### Step 3: Verify Changes

Run all verification gates before committing:

```bash
# Unit tests for changed modules
npm test -- --run \
  src/features/product/runtime/<new-runtime>.test.ts \
  src/features/product/containers/BuilderContainer.test.tsx

# TypeScript type check
npx tsc --noEmit

# Production build
npm run build:web

# Static audit
node scripts/sovereign-static-audit.mjs
```

Optional (if script exists):
```bash
node scripts/sovereign-live-path-scan.mjs
```

### Step 4: Commit Changes

```bash
# Stage only relevant files (exclude auto-generated)
git add src/features/product/runtime/<file>.ts \
       src/features/product/runtime/<file>.test.ts \
       src/features/product/containers/BuilderContainer.tsx

# Write descriptive commit
git commit -m "feat(#ISSUE): Brief description

- What was added
- Key behavior changes
- Test coverage
- Integration points

Co-authored-by: openhands <openhands@all-hands.dev>"
```

### Step 5: Push to Main

```bash
git push origin main
```

### Step 6: Close Issues via GitHub API

After successful push:

```bash
# Post completion comment
curl -s -X POST \
  "https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/issues/{number}/comments" \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"body":"## ✅ Issue Completed\n\nAll acceptance criteria verified:\n- Criterion 1\n- Criterion 2\n\n**Implementation:** `COMMIT_SHA`\n\nThis comment was created by an AI agent (OpenHands) on behalf of the repository maintainer."}'

# Close the issue
curl -s -X PATCH \
  "https://api.github.com/repos/OuroborosCollective/Sovereign-Studio-ato/issues/{number}" \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"state":"closed","state_reason":"completed"}'
```

## Commit Message Convention

### Format

```
<type>(#ISSUE): <subject>

<body>

Co-authored-by: openhands <openhands@all-hands.dev>
```

### Types

| Type | Use Case |
|------|----------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation |
| `refactor` | Code refactoring |
| `test` | Adding/updating tests |
| `chore` | Maintenance tasks |

### Examples

**Feature:**
```
feat(#429): Android quick interactions - URL auto-detect, long-press copy and haptics

- Wire runtime helpers into existing chat surface
- Composer shows 'Repo erkannt · Laden' hint for pasted GitHub URLs
- Long-press menu: copy writes only visible bubble text
- Haptics use guarded runtime helper, silently no-op when unsupported
- 4 new tests for #429 behavior

Co-authored-by: openhands <openhands@all-hands.dev>
```

**Runtime Module:**
```
feat(#433): Runtime Inspectors for PAT, ORC, INT panels

- Add runtimeInspectorPanelRuntime with derivePatInspectorSignals, deriveOrcInspectorSignals, deriveIntInspectorSignals
- Integrate with quietInspectorHintPolicy.ts via toQuietInspectorSignal() helper
- Each signal includes lamp (green/yellow) and targetTab for unified inspector format
- 12 new runtime tests added

Co-authored-by: openhands <openhands@all-hands.dev>
```

## Issue Management

### Opening Issues

When creating new issues, include:
- Clear problem statement
- Goal with acceptance criteria
- File paths to modify
- Product rules that apply
- Example implementations

### Closing Issues

When closing issues after implementation:

1. **Post completion comment** with:
   - Summary of acceptance criteria verified
   - Commit SHA for implementation
   - AI disclosure note

2. **Close with `state_reason: "completed"`**:
   ```json
   { "state": "closed", "state_reason": "completed" }
   ```

### Parent Issue Closure

When all child issues are closed, close the parent:

1. **Post summary comment** listing all child issues:
   ```
   ## ✅ Parent Issue Completed
   
   | Issue | Title | Status |
   |-------|-------|--------|
   | #428 | Slash commands | ✅ Completed |
   | #429 | Android quick interactions | ✅ Completed |
   ...
   ```

2. **Close the parent issue**

## Common Git Commands

### Sync with Remote

```bash
# Fetch and merge latest main
git fetch origin main && git pull origin main

# Force reset to remote main (use with caution)
git fetch origin main && git reset --hard origin/main
```

### Amend Last Commit

```bash
# Modify commit message or add files
git add <files>
git commit --amend -m "Updated message"

# Force push (only for your own feature branches)
git push --force-with-lease origin <branch>
```

### View Commit History

```bash
# View recent commits
git log --oneline -10

# View diff of last commit
git show HEAD

# Search commits by message
git log --oneline --grep="#429"
```

### Branch Management

```bash
# Create feature branch
git checkout -b feat/issue-429

# Switch to main and update
git checkout main && git pull origin main

# Delete merged branch
git branch -d feat/issue-429
```

## Avoiding Common Mistakes

### Mistake: Working on Stale State

**Problem:** Applying patch causes conflicts because main has changed.

**Solution:** Always pull latest before starting:
```bash
git fetch origin main && git pull origin main
```

### Mistake: Forgetting to Close Issues

**Problem:** Code is pushed but issue remains open.

**Solution:** Always close via GitHub API after successful push.

### Mistake: Committing Auto-Generated Files

**Problem:** `dist/`, `node_modules/`, build artifacts in repository.

**Solution:** Stage only relevant files:
```bash
git add src/features/product/runtime/*.ts
git add src/features/product/containers/*.tsx
# NOT: git add dist/ android/ node_modules/
```

### Mistake: Force Pushing to Main

**Problem:** Rewrites shared history, affects collaborators.

**Solution:** Never force push to `main`. Use `--force-with-lease` only on feature branches when necessary.

### Mistake: Missing Co-Author

**Problem:** Commit doesn't follow repository conventions.

**Solution:** Always include:
```
Co-authored-by: openhands <openhands@all-hands.dev>
```

## Verification Checklist

Before pushing to main, verify:

- [ ] Pulled latest main
- [ ] Applied changes correctly
- [ ] Tests pass (`npm test -- --run`)
- [ ] TypeScript passes (`npx tsc --noEmit`)
- [ ] Build succeeds (`npm run build:web`)
- [ ] Static audit passes (`node scripts/sovereign-static-audit.mjs`)
- [ ] Only relevant files staged
- [ ] Commit message follows convention
- [ ] Issues closed via GitHub API
