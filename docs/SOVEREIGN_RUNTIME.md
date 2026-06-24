# Sovereign Runtime

Sovereign Runtime is the truth layer behind the product UI. It keeps repository automation grounded in loaded repo files, deterministic guards, workflow checks and visible user review.

## Truth path

The runtime path is:

1. Real GitHub repository tree is loaded.
2. Repo paths are converted into readiness signals.
3. A mission is classified against the loaded snapshot.
4. Provider output is normalized into the Sovereign brain contract.
5. Generated files are reviewed by functional guards.
6. Diff context is loaded when available.
7. Draft PR publishing creates a branch, tree, commit and PR.
8. Workflow watch reads GitHub Actions status for the produced commit.
9. UI/Coach state is derived from runtime state, not DOM scraping.

## Brain gate

Every accepted package must include these layers:

- perception
- analysis
- plan
- execution
- learning

A response without usable execution patches is not a release artifact. A response that touches forbidden paths, duplicates generated output or bypasses file review must be rejected before GitHub publishing.

## Provider policy

Provider output is treated as untrusted input until guards accept it.

Current route categories:

1. Existing no-key routes such as Mlvoca and Pollinations.
2. Optional configured provider routes such as Groq, Hugging Face, Together and OpenRouter.
3. Optional user-key routes.
4. Local-safe fallback for conservative, guardable output.

Provider failures may be recorded for diagnostics, but failed-provider text must not become product documentation or release truth.

## UI/UX runtime-state rule

The UI should show state from these runtime sources:

- repo snapshot readiness
- sequential runtime step state
- package review state
- Draft PR publishing state
- workflow watch report
- telemetry as side-channel diagnostics only

The UI must not infer release readiness from button labels, DOM text flicker or generated prompt transcripts.

## Checks

Recommended local and CI checks:

```bash
pnpm run type-check
pnpm run test:unit
pnpm run build:web
pnpm run audit:sovereign
```

Release checks should also include runtime/UX/live-path contract scans and Android debug APK generation.
