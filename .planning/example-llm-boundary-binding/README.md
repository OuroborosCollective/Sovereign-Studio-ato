# Example Plan: `example-llm-boundary-binding`

This directory is a **worked example** for Issue #1112. It demonstrates
the canonical layout of a per-integration plan and is the reference an
Owner's agent is expected to follow when opening a real integration
plan. None of the artifacts here are written to the canonical
continuity ledger; the canonical continuity ledger is append-only at
`docs/sovereign-continuity/LEDGER.jsonl` and independently at
`tools/sovereign-chatgpt-mcp/continuity-data/LEDGER.jsonl`.

| File | Purpose |
| --- | --- |
| `task_plan.md` | Owner-visible plan: scope, phases, acceptance criteria, next step. |
| `findings.md` | Five canonical sections (untrusted_external, repository_observed, runtime_observed, verified, invalidated). |
| `progress.md` | Real event log, no secrets, no LiteLLM-style reflection. |
| `plan.receipt.json` | Schema-versioned plan identity, owner binding, attestation hashes. |
| `evidence-index.json` | Per-phase evidence records with `isVerified` flags. |
| `ledger-actions.jsonl` | Append-only per-plan ledger (not the canonical continuity ledger). |
| `.mode` | Gating mode (`open` / `gated` / `closed`). |
| `.attestation` | SHA-256 of the plan content; must match `plan.receipt.json.attestationSha256`. |
| `.active_revision` | Workspace HEAD SHA the plan is bound to. |

## Status

- `runtimeVerified: false` — this is a worked example, not a live plan.
- `mutationPerformed: false` — no canonical commit has been made.
- `secretValuesReturned: false` — no secrets are stored in the plan.

## How to verify the example

```bash
python -c "
import json, hashlib
plan = json.load(open('.planning/example-llm-boundary-binding/plan.receipt.json'))
on_disk = open('.planning/example-llm-boundary-binding/.attestation').read().strip()
assert plan['attestationSha256'] == on_disk, 'attestation mismatch'
print('attestation OK:', plan['attestationSha256'])
"
```

## Truth notice

Marking `Status: complete` in `task_plan.md` does not close the
integration. Only the evidence-evaluator + real readback can produce a
verified or terminal state. This is by design.
