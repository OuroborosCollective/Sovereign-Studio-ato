# Sovereign OpenShell — isolated policy and executor admission pilot

**Truth class: IMPLEMENTED_IN_REPOSITORY only after this PR's exact SHA is checked.**
**No deployment, active sandbox, live executor switchover, CI PASS or production effect is implied.**

Source baseline: Sovereign `cfa40443d89a4aa1f38e3b974303cfe09ffac8cc`.
Reviewed upstream: NVIDIA/OpenShell `c4688aa8715ea75d6c39fe468361dbbc16c691fa`, Apache-2.0.
Repository-wide authority remains `AGENTS.md` and `docs/SOVEREIGN_PRODUCT_TRUTH.md`.

## Why this exists

The read-only `ShellTool` in `backend/agent_runtime/tools/shell_tool.py` intentionally
accepts only `ls` and `pwd`; this is **not** Sovereign's entire repository executor.
The durable repository lane is `backend/agent_runtime/repository_execution.py`,
which admits scoped jobs, uses compare-and-swap claims and heartbeat observations,
selects free/paid routes, and binds `BoundRepositoryToolset`. That toolset exposes
file read/write, exact patch, repository test and diff tools, with explicit authority.
The legacy `sovereign_local_runner.py` is quarantined and must **not** be unquarantined
or confused with the newer repository lane. The newer reconciler is registered
by `scripts/sovereign-backend/production_app.py`. Source wiring alone proves
neither the running image nor a successful end-to-end job.

**Acceptance goal (not yet demonstrated):** one real, authorized, revision-bound
Sovereign agent job in a sandbox reads a checkout, applies a permitted test patch,
runs its real regression command, persists a receipt and job transition, and
survives an independent target readback of Git diff, test exit, DB job, sandbox
policy and image/revision identity. A deny/revocation case must also pass.

## Repository-only opt-in preflight

- `backend/agent_runtime/openshell_preflight.py`: stdlib-only proof/canary.
- `scripts/sovereign-backend/agent_runtime/openshell_preflight.py`: exact-byte mirror.
- `config/openshell/agent-readonly-policy.yaml`: candidate with **zero** egress and
  `landlock.compatibility: hard_requirement`.
- `config/openshell/agent-readonly-boundary.yaml`: upper policy boundary; *not* the
  candidate executed by the canary.
- `scripts/sovereign-backend/tests/test_openshell_preflight.py`: 11 local contract
  tests, mocking only the external executable boundary. The tests do **not**
  substitute for a real OpenShell verifier or sandbox.

No upstream installer or `curl | sh` is invoked. No credentials, tokens or
production filesystems are mounted. No paid inference route or app-side runtime
is changed. The canary must never be silently enabled by a CI or deployment.

On an approved isolated Linux host with a *reviewed and pinned* matching CLI,
standalone prover and compatible gateway, the operator may run:

```sh
python3 -m backend.agent_runtime.openshell_preflight \
  --policy config/openshell/agent-readonly-policy.yaml \
  --boundary config/openshell/agent-readonly-boundary.yaml \
  --expected-version 0.1.5
```

The version is a documentation example, not an installed version claim.
Missing tools, version drift, policy digest drift, `unsupported`,
`inconclusive` and absent coverage **block**. Only with separate host scope,
append `--apply-canary` for a fixed, disposable, negative-egress test.
Even a successful canary is not proof of production execution or cleanup:
read back gateway policy, sandbox identity, logs, sandbox deletion, provider
attachments, kernel qualification and host isolation independently.

## Promotion gates, in this order

1. Exact-HEAD Sovereign CI, focused/neighbor regressions and mirror-parity.
2. Reviewed immutable OpenShell binaries and images, kernel Landlock/seccomp,
   Docker/Podman isolation, host resource accounting and policy-prover result.
3. Real sandbox deny/allow/cleanup probes with receipts from the gateway.
4. Implement **one** governed adapter inside Sovereign's existing tool/permission
   boundary (no parallel orchestrator), preserving job CAS/lease, revocation,
   owner/repository/revision identity, provider routes and persistence.
5. Run the end-to-end **write → actual test → persist → independent readback**
   executor test and negative cases. No silent host fallback.
6. Only after Sovereign has runtime evidence, trial an isolated agent shell for
   ARE-SOFTWAREGPU-ENGINE; preserve byte-identical color/depth regressions and
   CPU-only benchmark receipts. Aurion stays unchanged until *both* systems
   are verified.

**OpenShell limitations:** the formal prover covers only modeled policy
domains (not every protocol or filesystem edge case); `within_boundary`
is **not** a statement that a running sandbox is isolated. The OpenShell
pre-1.0 API must be rechecked against a pinned released toolchain.

**Current evidence:** local proof-adapter unit tests were run in isolation;
host `openshell` and `openshell-prover` were unavailable in the local
environment, and no Sovereign production job/readback was run. OpenShell
integration remains `BLOCKED` at runtime until host and executor gates pass.
