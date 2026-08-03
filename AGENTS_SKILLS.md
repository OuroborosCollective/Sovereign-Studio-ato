# Agent Skills — Sovereign Studio ATO

**Reconciled:** 2026-08-03  
**Repository baseline:** `63ddbdf4ed8cd6fa895147e6b09dc39bb2330483`

These are reusable workflows for this repository. A skill never creates permission, evidence or target-system truth by itself.

## Skill 1 — Revision-bound preflight

Use before every mutation.

1. Resolve current `main` and record the exact 40-character SHA.
2. Read related open Issues and PRs.
3. Check for an existing workspace, branch or uncommitted changes.
4. Create an isolated branch/workspace from the exact resolved revision.
5. Read `AGENTS.md`, Current State, Product Truth, Continuity Context, policy and ledger head.
6. Identify canonical and mirrored paths.
7. Define required tests, CI gates and external readbacks.

Fail closed on missing revision, unclear ownership or conflicting work.

## Skill 2 — Repository architecture inventory

Use before introducing a new subsystem or importing an external idea.

- Search current code for existing routes, tools, schemas, tables, UI projections and tests.
- Distinguish canonical code from deployment mirrors.
- Compare the proposal with existing agent, queue, memory, MCP, approval and evidence surfaces.
- Classify every proposed feature as `extend`, `compose`, `replace`, `reject` or `planned`.
- Record legal and supply-chain boundaries for external archives.
- Do not execute unknown binaries or installers during analysis.

Preferred evidence:

- exact paths and symbols;
- Git blob/content hashes;
- schema and migration ownership;
- current tests;
- runtime registry/readback where applicable.

## Skill 3 — Bounded repository edit

Use for documentation and code changes.

1. Read the current file and blob SHA.
2. Prefer exact search/replace for large or high-risk files.
3. Require each search block to match exactly once.
4. Block stale blob/repository SHAs.
5. Keep the patch within the approved path and effect scope.
6. Inspect the diff before commit.
7. Run targeted checks.

Full-file replacement is acceptable only for small, fully reviewed text files when the current blob SHA is bound.

## Skill 4 — Canonical/mirror change

Use when a backend module or migration has a deployment mirror.

1. Identify the canonical owner.
2. Apply the same semantic change to canonical and mirror paths.
3. Verify byte equivalence where the contract requires it.
4. Run canonical tests and mirror-parity tests.
5. Include both paths in continuity and PR evidence.

Never patch only the running/deployment copy.

## Skill 5 — Real-path test design

Use for frontend, backend, MCP and security changes.

- Import the real implementation.
- Use shared provider/test harnesses when the component needs Redux, router or runtime context.
- Mock only external boundaries.
- Cover success, expected failure, invalid input, stale revision/hash, replay and cross-scope denial.
- Assert structured failure codes rather than parsing prose.
- Verify that tool/model success remains unverified until target readback.
- For secret handling, assert absence/redaction without embedding usable secret-shaped values.

Do not copy production functions into tests.

## Skill 6 — Draft PR publication

1. Verify the branch is based on the intended revision.
2. Inspect changed paths and diff.
3. Append the required continuity handoff entry.
4. Run available targeted checks.
5. Create a Draft PR with:
   - source/base revision;
   - exact changed paths;
   - implemented behavior;
   - checks actually run;
   - unavailable checks and blockers;
   - evidence/readback still required.
6. Read the exact PR head after publication.

Do not mark ready or merge merely because a commit exists.

## Skill 7 — CI failure classification

Use when a workflow fails.

1. Read the exact run, job and failed step.
2. Confirm the run belongs to the current PR head.
3. Classify the failure family: code, test, contract, continuity, secret scan, workflow, dependency, environment, artifact or unrelated infrastructure.
4. Reproduce with the smallest relevant check where possible.
5. Fix the causal source, not the latest visible symptom.
6. Re-run only eligible failed/cancelled/timed-out workflows.
7. Re-read all required checks at the unchanged new head.

Pending is not failed. Empty status is not green.

## Skill 8 — Provider route change

- Preserve direct OpenRouter paid routing and direct FreeLLM/Revolver free routing unless a separately approved architecture issue changes it.
- Do not reintroduce LiteLLM.
- Normalize price snapshots into canonical numeric-or-null values.
- Bind provider/model metadata to a refresh/readback timestamp and source identity.
- Fail closed with structured recoverable errors rather than unhandled HTTP 500s.
- Never log keys or provider payloads containing secrets.

## Skill 9 — Repository Intelligence use

- Build/search the revision-bound local index only inside the isolated workspace/Git-private area.
- Treat search ranking and token projections as discovery aids.
- Before editing, read the exact tracked file and Git blob.
- Use capability scopes and hash-bound replace/restore for mutations.
- Verify repository SHA, blob SHA, allowed path and effect.
- Do not claim deployment or runtime success from repository intelligence output.

## Skill 10 — Immutable deployment and MCP self-update

Required order:

1. exact reviewed PR head;
2. required CI terminal green;
3. merge exact head with explicit owner approval;
4. resolve merge/main revision;
5. build immutable image bound to that revision;
6. read registry digest;
7. deploy/self-update through the controlled operator path;
8. read revision, digest, registry, protocol and container identity;
9. read PatchMon/fleet evidence;
10. confirm rollback reference is bound to a real prior revision or digest.

Any missing or contradictory identity blocks completion.

## Skill 11 — Documentation reconciliation

Use when architecture or operational contracts change.

- Update README, Current State, Reader, Product Truth and relevant agent docs together.
- Remove superseded instructions instead of appending contradictory notes.
- Preserve historical records in history/ledger surfaces.
- Mark planned features as `PLANNED`.
- Mark repository-only functionality as `IMPLEMENTED_IN_REPOSITORY`.
- Do not place mutable IPs, ports, credentials, OAuth IDs or hotpatch commands in contributor docs.
- Verify every linked path exists at the branch head.

## Skill 12 — External archive evaluation

- Hash the archive.
- Check path traversal, duplicates, symlinks and encryption.
- Inventory manifests, licenses, signatures, scripts, native binaries and remote endpoints.
- Search for credential-like literals without disclosing values.
- Identify installer, deletion, upload and telemetry behavior.
- Compare capabilities with existing repository surfaces.
- Prefer clean-room principles over code reuse when licensing, trust or duplication is unclear.
- Never run unknown code merely to understand it.

## Common commands

```bash
pnpm run type-check
pnpm run test:unit
pnpm run test:integration
pnpm run test:release-gate
pnpm run build:web
pnpm run audit:sovereign
pnpm run audit:all
pnpm run verify
```

Use focused Python `pytest` commands for affected backend/MCP contracts. Run complete dependency-heavy gates in GitHub Actions when the local environment is not prepared.

## Explicitly obsolete skills

Do not use or restore:

- direct `docker cp` production patching;
- `pip install` or system mutation inside running containers;
- password/host literals in deployment snippets;
- automatic acceptance of unknown SSH host keys;
- GitHub API calls through raw token-bearing `curl` examples;
- universal `draft=false` guidance;
- copied standalone implementations in tests;
- broad `sed -i` batch edits without exact-match and stale-SHA guards.
