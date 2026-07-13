# Sovereign MCP control-plane truth

## Direction of authority

The public MCP transport accepts protocol traffic and validated intent. It must not directly execute privileged host mutations.

- Read-only host evidence may use the local Unix broker socket.
- Host, Docker, GitHub-admin, production database, deploy and self-update mutations are written as bounded jobs to `/opt/sovereign-chatgpt-tools/command-queue`.
- `sovereign-chatgpt-command-worker.service` runs independently on the VPS, claims jobs from the queue and executes only actions listed in `command_contract.MUTATING_ACTIONS`.
- `BrokerRuntime.dispatch` rejects every mutating action received through the Unix socket with `INBOUND_MUTATION_FORBIDDEN`.
- There is no generic shell action.

## Job truth

A queued job has one of these states:

- `QUEUED`: not claimed by the host worker.
- `IN_PROGRESS`: atomically moved to the processing directory.
- completed result in the outbox.
- `CANCELLED`: timeout happened before the worker claim; execution did not start.
- `HOST_COMMAND_OUTCOME_UNCERTAIN_AFTER_WORKER_RESTART`: the worker restarted after claiming the job. The job is never automatically executed again. Inspect the target state before any manual retry.

Use `mcp_host_command_status` for an existing request ID. Never resubmit an `IN_PROGRESS` or uncertain mutation blindly.

## Required deployment evidence

An MCP installation is successful only when all of the following are true:

1. `sovereign-chatgpt-command-worker.service` is active.
2. A direct mutating Unix-socket canary returns `INBOUND_MUTATION_FORBIDDEN`.
3. The same canary submitted through the queue returns `HOST_WORKER_READY` with `execution_origin=host_worker`.
4. The broker socket exists on the host and inside the MCP container.
5. Broker health returns `BROKER_READY`.
6. The real JSON-RPC initialize handshake returns `MCP_PROTOCOL_READY`.
7. The tunnel service is active.

## Build and dependency boundary

The running MCP container and the VPS are orchestration surfaces, not Node build workers.

- `pnpm install`, TypeScript checks, Vitest, audits and web builds run only on GitHub Actions runners.
- The local Android `fast` profile contains only diff and static readiness evidence. `standard` and `release` use the allowlisted Android workflow.
- Frontend changes may be pushed as a Draft PR without local Node execution; the PR remains unverified until the required remote checks complete successfully.
- The MCP container image is built and published by GitHub Actions with `org.opencontainers.image.revision` set to the exact commit SHA.
- The VPS pulls that exact tag, verifies the revision label, resolves an immutable repository digest and persists the digest before replacing the running container.
- `docker compose build` is forbidden in the VPS installer. A failed image pull or verification leaves the current container untouched.

## Streamable HTTP evidence

A `400 Bad Request` line alone does not prove that the MCP or tunnel failed. Some client cycles may also contain valid `200 OK` and `202 Accepted` traffic.

The bootstrap blocks the tunnel only when repeated 400 responses occur in the observation window and there is no successful 200/202 MCP traffic in the same window. Node.js, dependencies, the broker or Docker must not be repaired from a 400 line without causal evidence.
