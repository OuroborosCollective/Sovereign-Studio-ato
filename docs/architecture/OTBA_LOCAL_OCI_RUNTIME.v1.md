# OTBA LOCAL_OCI Runtime Lane — v1

> Baseline revision: `841745f5c824227cc9b8e0204ee231d00f44864b` (issue #1451, OTBA 2/5)
> Status: `IMPLEMENTED_IN_REPOSITORY` / `TESTED_AT_REVISION`
> Scope: the real LOCAL_OCI canary runtime, the strace trace normalizer, and the bridge that
> converts a real observation set into an `ObservedToolBehaviorReceipt`. Stacked on the OTBA 1/5
> contract/receipt core. No registry promotion, no persistence, no LLM decision.

## Prime directive

Runtime creates truth. This lane runs a real tool inside a real OCI container, traces its real
syscalls with strace, reads the real image digest from the registry, and feeds only those real
observations into the deterministic receipt core from OTBA 1/5. A positive `BEHAVIOR_VERIFIED`
verdict is never produced from a mock, an unavailable runtime, a trace that died, or a digest that
did not match the contract.

## Ownership

| Path | Ownership |
|------|-----------|
| `tools/sovereign-chatgpt-mcp/tool_behavior_trace.py` | pure strace trace normalizer |
| `tools/sovereign-chatgpt-mcp/tool_behavior_runtime.py` | LOCAL_OCI canary runtime + receipt bridge |
| `tools/sovereign-chatgpt-mcp/tests/test_tool_behavior_trace.py` | trace normalizer tests |
| `tools/sovereign-chatgpt-mcp/tests/test_tool_behavior_runtime.py` | runtime + gate tests |
| `tools/sovereign-chatgpt-mcp/tests/fixtures/trace_*.log` | authentic strace captures (real, not synthesized) |

This lane introduces no second registry, queue, memory store, approval system or evidence truth
layer. It consumes the OTBA 1/5 contract and receipt cores and does not modify them.

## tool_behavior_trace.py

A pure, execution-free normalizer that converts raw strace text into a `ToolBehaviorObservationSet`.

`ToolBehaviorObservationSet`:

- `process_exec` — the `execve` target binaries, in observation order
- `filesystem_reads`, `filesystem_writes` — deduplicated, sorted real path operands
- `network_connects`, `network_listens` — `host:port`/`unix:` endpoints from `connect`/`bind`
- `peak_memory_bytes`, `wall_time_ms`, `exit_code` — caller-supplied resource stats
- `trace_artifact_sha256` — derived canonical hash over the observation set (not the raw bytes)

### Baseline noise exclusion

A real OCI container produces runtime loader reads, `nscd`/resolver unix sockets and `/dev/tty`
stdio wiring that are not the tool's behavior. The normalizer excludes these so a tool is not
blamed for runtime overhead:

- `/dev/tty`, `/dev/null`, stdio descriptors are baseline, never a filesystem write.
- Dynamic-loader and library reads under `/usr/lib`, `/lib`, `/etc/ld.so*` are baseline reads.
- `AF_UNIX` connects to `/var/run/nscd`, `/run/nscd` are baseline resolver noise.
- `/etc/passwd`, `/etc/hosts`, `/etc/nsswitch.conf`, `/etc/resolv.conf` are baseline reads.

Exclusion is a path-classification decision over the immutable OCI filesystem baseline; it never
invents an observation and never hides a real workspace write.

## tool_behavior_runtime.py

The real LOCAL_OCI canary. `run_local_oci_canary` runs a tool command inside a real Docker
container, traces it with a strace sidecar, reads the image digest and captures resource stats.

### Image digest binding

`resolve_image_digest` reads `docker image inspect --format {{index .RepoDigests 0}}`. A
`LOCAL_OCI` contract that carries no `image_digest` is rejected at contract construction
(fail-closed, OTBA 1/5). After execution, the executed digest is compared to the contract digest;
a mismatch yields `IMAGE_DIGEST_MISMATCH`, never a positive verdict.

### Observation dimensions

The canary captures all four OTBA observation dimensions from real syscalls:

- Process: `execve` targets.
- Filesystem: `openat`/`open`/`creat`/`unlink` reads and writes.
- Network: `connect`/`bind` endpoints (IP/DNS `host:port`, unix sockets).
- Resource: peak memory from `docker stats`, wall time, exit code.

### Non-positive runtime statuses

Every non-positive path is a real, named blocker, never a hidden success:

- `UNAVAILABLE` — docker or strace not present (real probe).
- `BLOCKED` — contract `execution_kind` is not `LOCAL_OCI`.
- `IMAGE_DIGEST_MISMATCH` — executed digest differs from the contract.
- `TRACE_DIED` — the tracer exited before the tool; observation is incomplete.
- `EXECUTION_FAILED` — the canary command exited non-zero and no clean trace was captured.

### Container hygiene

Each canary runs in a uniquely named container `otba-canary-{pid}-{timestamp}` and is removed
after the run. A failed cleanup cannot turn a non-positive result positive.

## Receipt bridge

`build_receipt_from_canary` bridges a real `LocalOciRunResult` into an `ObservedToolBehaviorReceipt`:

- A `VERIFIED_OBSERVATION` run with in-bounds observations → `BEHAVIOR_VERIFIED`.
- A `VERIFIED_OBSERVATION` run with an undeclared write/exec/network → `BEHAVIOR_VIOLATION`.
- Any non-positive status → `UNVERIFIED`, with the real blocker recorded as a finding.
- The receipt binds the trace artifact hash to the raw trace content hash and the authoritative
  readback to the contract hash. Receipts round-trip through serialization and fail closed on tamper.

`observation_set_to_observed_behavior` maps a `ToolBehaviorObservationSet` into the
`ObservedBehavior` shape the receipt core expects, deterministically sorting merged network targets.

## What this lane does NOT do

- No registry mutation or promotion. A verified canary does not promote a tool.
- No persistence. Receipts are returned to the caller, never stored by this lane.
- No LLM decision. The verdict is deterministic, evaluated from real observations.
- No claim of deployed runtime truth. The canary runs locally; deployed runtime readback belongs
  to a later OTBA lane.

## Testing truth

Tests exercise the real normalizer against authentic strace fixtures captured from real isolated
executions (bash echo, whoami, getent DNS, forbidden write). They assert exact expected
observations and that baseline runtime noise is excluded.

The real Docker canary path cannot run without a Docker daemon. Per the truth rules, those tests
are skipped honestly (`pytest.mark.skipif`) — they are never faked. What is verified
deterministically: availability probes return real booleans; non-positive statuses are honest and
named; the gate bridges real fixtures into verified/violation/unverified receipts; receipts are
tamper-resistant across serialization. No mock ever produces a positive runtime attestation receipt.

## Remaining risks

- A real positive canary requires a Docker daemon + a registry-resolvable image bound to the
  contract digest. In environments without Docker, only the deterministic gate and negative paths
  are exercised; the real positive canary is deferred to CI/environments with Docker.
- Baseline noise exclusion is a path classification over the standard OCI filesystem layout. A
  custom image with a non-standard layout could misclassify a path; the classification is
  intentionally conservative (excludes only well-known runtime paths).
- This lane feeds the receipt core honestly, but cannot detect a caller that supplies a fabricated
  trace as if it were real. Independent readback (later OTBA lane) must re-derive observations.
