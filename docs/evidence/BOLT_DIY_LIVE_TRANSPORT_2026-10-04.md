# Bolt.diy live transport evidence — 2026-10-04

## Observed self-hosted surface

Live instance:

```text
https://boltdiy-m3bq.srv1491137.hstgr.cloud/
```

A live page read returned HTTP 200 and exposed repository-import links in the form:

```text
/git?url=https://github.com/<owner>/<repo>.git
```

A domain URL inventory exposed only the web application root; no stable public execution, archive-upload or result-readback API was discovered.

## Upstream behavior relevant to the boundary

Upstream bolt.diy Git integration history (PR #421) implements browser-side cloning with `isomorphic-git` into the WebContainer filesystem using:

```text
depth: 1
singleBranch: true
```

The same upstream discussion explicitly calls out the reload problem: the WebContainer project disappears and re-cloning later may produce different files. That is consistent with the current Sovereign decision to model Bolt as a remote snapshot rather than a durable local workspace.

Source:

```text
https://github.com/stackblitz-labs/bolt.diy/pull/421
```

## Safe transport modes

### UI Git import

Sovereign may produce a clickable `/git?url=...` launch URL for exploratory development.

It is **not revision-bound** and therefore cannot satisfy Sovereign snapshot provenance or serve as merge evidence.

### Exact revision archive

Sovereign may produce:

```text
https://github.com/<owner>/<repo>/archive/<40-char-sha>.zip
```

This URL is revision-pinned input. It still does not prove that Bolt imported, executed or tested those bytes. Until the self-hosted instance exposes an authenticated archive-upload + result-readback contract, Sovereign requires an external upload/execution receipt and keeps `executionEvidenceAuthoritative=false`.

## Add-ons

Python, headless Blender, Ninja and game-development tools remain capability observations. Their availability must be probed inside the actual execution environment; the web UI itself is not evidence that a tool ran.

## Result

The live transport is now modelled without inventing a local workspace or a backend API that the instance does not expose. A future authenticated Bolt API can replace the UI handoff while preserving the existing exact-revision and evidence contracts.
