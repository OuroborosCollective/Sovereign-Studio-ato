# Generated File Diff Preview

Generated File Diff Preview is a review layer between generated files and Draft PR publishing.

It answers a simple question:

```txt
What would actually change compared with the current repository source?
```

## Flow

```txt
Sovereign package built
↓
Generated file review passes
↓
User opens Diff tab
↓
App loads source snapshots from GitHub contents API
↓
Diff report compares source snapshots with generated files
↓
Draft PR body can include the diff summary
```

## What it shows

For each generated file, it shows:

- path
- created / modified / unchanged / source-missing
- old line count
- new line count
- added line count
- removed line count
- short unified-like preview

## Honesty rules

Diff Preview only compares against source snapshots that were explicitly loaded.

If a source snapshot is not loaded, the file is marked as `source-missing`.

If GitHub returns `404`, the file is treated as `created`.

It does not claim a full semantic diff. It is a human-readable preview for review and PR context.

## Safety rules

Diff Preview does not replace:

- functional guards
- generated file review
- Draft PR publisher validation
- Workflow Watch
- CI checks

It only improves transparency before publishing.

## Related files

```txt
src/features/product/runtime/generatedFileDiffPreview.ts
src/features/product/runtime/generatedFileDiffPreview.test.ts
src/features/product/components/GeneratedFileDiffPreviewPanel.tsx
src/App.tsx
src/features/product/runtime/runtimeValidationCoverage.ts
src/features/product/runtime/sovereignStructure.test.ts
```
