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
src/features/product/runtime/scanFindingRegistry.test.ts
src/features/product/components/ScanFindingRegistryPanel.tsx
src/App.tsx
src/features/product/runtime/runtimeValidationCoverage.ts
src/features/product/runtime/sovereignStructure.test.ts
```
