# Integration Task Plan

- plan_id: `example-llm-boundary-binding`
- schema_version: `sovereign.integration-plan-lane.v1`
- plan_schema_version: `1`
- owner: `thomas`
- repo: `OuroborosCollective/Sovereign-Studio-ato`
- workspace_id: `ws-llm-boundary-2026-08-04`
- base_revision: `061919f3a34846eadeebcdee50358b15252e580f`
- issue_reference: `1112`
- pr_reference: `1190`
- attestation_sha256: `populate_after_first_append`
- predecessor_attestation_sha256: ``
- amendment_reason: `initial creation; this is a worked example, not a live plan`
- recorded_at_iso: `2026-08-04T01:00:00+00:00`

> This file is a **worked example** for Issue #1112. It documents the
> canonical task_plan.md layout that an integration agent must produce
> via `integration_plan_helpers.render_task_plan`. Replace the placeholder
> attestation and base_revision with real values when starting an actual
> plan.

## Acceptance Criteria

- Direct OpenRouter paid and direct FreeLLM/Revolver free LLMs remain on
  their own paths; LiteLLM is not introduced.
- `llm_execution_resolver` enforces no-key / user-key / paid-key
  boundaries for every direct route.
- `_load_provider_credential` and the SOVEREIGN_API_KEY env variable are
  the only legitimate fallback chains.

## Allowed Mutation Surfaces

- `backend/agent_runtime/llm_execution_resolver.py`
- `backend/agent_runtime/llm_cost_policy.py`
- `backend/tests/test_llm_execution_resolver.py`

## Phases

### 01-introspect — Trust boundary inventory
- status: `verified`
- description: Snapshot every credential-loading call path and verify
  no key is requested through LiteLLM-style reflection.
- acceptance_criteria:
  - Every credential loader is documented and unit-tested.
  - No LiteLLM usage in production code.
- required_evidence_kinds:
  - `repo_revision`
  - `pr_head`
  - `ci_workflow`
  - `runtime_readback`

### 02-prepaid-paid-route — Direct OpenRouter paid flow
- status: `verified`
- description: Wire SOVEREIGN_API_KEY → OpenRouter direct, no
  reflective call, refusal-on-missing-key semantics.
- acceptance_criteria:
  - `llm_execution_resolver.execute_openrouter_paid` only ever uses
    a stored credential or an explicit user key.
  - No `os.environ["OPENAI_API_KEY"]`-like reflection.
- required_evidence_kinds:
  - `repo_revision`
  - `ci_workflow`
  - `runtime_readback`

### 03-free-route — Direct FreeLLM/Revolver free flow
- status: `in_progress`
- description: Free LLM is on its own resolver path; not a paid-route
  fallback.
- acceptance_criteria:
  - FreeLLM path is exercised via direct worker URL, not via OpenRouter.
- required_evidence_kinds:
  - `repo_revision`
  - `ci_workflow`
  - `runtime_readback`

### 04-boundary-test — Negative tests for each boundary
- status: `pending`
- description: Direct tests that paid and free routes cannot accidentally
  share a credential path. LiteLLM is forbidden.
- acceptance_criteria:
  - Test asserts no LiteLLM import in shipped runtime.
- required_evidence_kinds:
  - `ci_workflow`
  - `runtime_readback`

## Next Step

Complete the negative tests for phases `03-free-route` and
`04-boundary-test`. Validate the entire resolver against
`runtime_readback` evidence from the staging VPS host.

## Truth Notice

Plan status is a projection. Repository, CI, artifact, image,
deployment, database and runtime truth remain canonical. Marking
`Status: complete` in this file alone does not close the integration.
