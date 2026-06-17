# Scan Finding Registry

The Scan Finding Registry is the categorized issue/warning collection layer for Sovereign Studio.

It was inspired by the GitForge-style `CodeIssue` idea, but implemented with stricter honesty rules:

```txt
Finding category
Severity
Status
Direct file path
Optional line number
Description
Fix tips
Confidence
Source
Scan run summary
```

## Flow

```txt
Repo snapshot loaded
↓
Repo path scan runs
↓
Findings are categorized
↓
Registry merges repeated findings
↓
Missing previous findings become resolved
↓
Findings tab groups active findings by category
↓
Draft PR body includes scan findings summary
```

## Categories

```txt
architecture
type-error
build-logic
warning
security-leak
test-doubles
build-artifact
runtime-guard
auth
workflow
ci-failure
learning-memory
diff-preview
generated-file
docs
```

## Severity

```txt
low
medium
high
critical
```

## Confidence

The first scanner is path-only. That means it does not claim to have read file contents.

```txt
path-only
content-scanned
runtime-observed
manual
```

Path-only findings are useful for triage and prioritization, but they are not content proof.

Workflow Watch findings use `runtime-observed`, because they come from actual check status output.

## Repo path scan

Repo path scans can detect path-based findings such as:

```txt
.env                         -> security-leak
node_modules / dist / build  -> build-artifact
mock / stub / fake           -> test-doubles
todo / fixme / wip           -> warning
missing workflow             -> workflow
missing tests                -> warning
missing README               -> docs
large files                  -> architecture
```

## Workflow Watch scan

Workflow Watch findings convert CI/check-run state into categorized findings.

Examples:

```txt
lint failed       -> ci-failure, eslint.config.*
tsc failed        -> type-error, tsconfig.json
build failed      -> build-logic, vite.config.*
test failed       -> ci-failure, src/**/*.test.ts
auth/token error  -> auth, GitHub Auth Session
workflow error    -> workflow, .github/workflows/*
```

These findings should be applied with the stable source name:

```txt
workflow-watch
```

That stable source is what allows the next workflow scan to prove whether the old CI finding is still active or resolved.

## Active vs resolved

Every scan creates a run summary.

If a finding appears again, its `hits` count increases.

If a finding from the same scan source no longer appears, it becomes `resolved`.

This lets the app say:

```txt
Scan repo-path-scan abgeschlossen: 7 finding(s), 2 high/critical.
```

and later:

```txt
.env finding resolved after new repo scan.
```

For CI findings:

```txt
scan 1: lint failed -> active
scan 2: lint still failed -> active, hits +1
scan 3: lint no longer found -> resolved
```

## Bookkeeping adapter

`scanFindingBookkeeping.ts` keeps active and resolved records instead of deleting old findings. Use it for history-sensitive scans.

```txt
applyScanFindingsWithBookkeeping
applyWorkflowWatchFindingsWithBookkeeping
markSourceResolvedByCleanScan
```

This is the layer that makes the registry behave like a real logbook.

## Publish gate

The publish gate checks active findings before Draft PR publishing.

It treats these as publish blockers until a later scan proves them resolved:

```txt
security-leak
auth
ci-failure
critical severity
```

The intent is not to hide the Draft PR button forever. The intent is to make unresolved findings visible until a new scan proves they are fixed.

## Safety rules

The registry validates itself:

- known category
- known severity
- valid status
- required file path
- required description
- required fix tips
- positive hits
- valid timestamps
- no raw secret-like text
- max finding count
- max scan run count

Secret-like text is rejected/redacted for patterns such as:

```txt
ghp_...
github_pat_...
sk-...
Bearer ...
password=...
token=...
```

## Related files

```txt
src/features/product/runtime/scanFindingRegistry.ts
src/features/product/runtime/scanFindingBookkeeping.ts
src/features/product/runtime/scanFindingRegistry.test.ts
src/features/product/components/ScanFindingRegistryPanel.tsx
src/App.tsx
src/features/product/runtime/runtimeValidationCoverage.ts
src/features/product/runtime/sovereignStructure.test.ts
```
