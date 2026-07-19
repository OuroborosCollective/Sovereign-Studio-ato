# Sovereign Enterprise Backend Platform

Status: production-path implementation  
Architecture: hardened modular monolith  
Canonical runtime: `scripts/sovereign-backend/app.py`  
Deployment mirror: `backend/app.py`

## Decision

The existing Flask service remains the only production backend. A second NestJS or Django runtime would duplicate authentication, migrations, observability, and operational ownership without replacing the deployed path. The platform slice is therefore extracted behind a stable package boundary:

- `enterprise_platform/contracts.py`: versioned statuses, validation, canonical evidence hashes, safe errors.
- `enterprise_platform/service.py`: bounded database and provider probes, statistics, canary policy, evidence readback.
- `enterprise_platform/routes.py`: authenticated HTTP transport, request IDs, security headers, rate-limit responses, OpenAPI.
- migration 025: append-only runtime evidence receipts.
- `EnterpriseBackendPanel.tsx`: Android/WebView-friendly operator surface.

The canonical deployment copy and the backend test mirror must remain byte-identical. CI contract tests enforce that invariant.

## Trust boundaries

| System | Backend relationship | Truth source | Platform state |
|---|---|---|---|
| PostgreSQL / Supabase | Direct private SQL through the existing bounded query helper | Transactional source of truth | Required live probe |
| pgvector | PostgreSQL extension and canonical vector columns | Canonical semantic persistence | Required live probe |
| Private LiteLLM | Existing private readiness and completion helpers | Only model-provider routing path | Required live probe |
| OpenAI Agents SDK | Persisted `agent_runs` state | Run lifecycle evidence | Optional live query |
| Knowledge Library | PostgreSQL metadata and pgvector blocks | Source/chunk/vector state | Optional live query |
| Cloudflare R2 | Configuration presence plus PostgreSQL object metadata | Object bytes only; DB owns metadata | Explicitly unverified until a bounded HEAD canary exists |
| Milvus | Outbox projection only | pgvector remains canonical | Explicitly unverified until the private consumer is probed |
| PatchMon | Separate MCP/host-broker control plane | PatchMon operator tools | Intentionally isolated from backend DB and Docker socket |
| Redis | No direct production dependency in this slice | Never a source of truth | Intentionally isolated |

An integration is never reported as verified from configuration alone. `defined_not_run`, `blocked`, and `isolated` are stable, visible states. Required failures block the platform; optional blocked or unprobed integrations degrade it.

## Auth and API

Every route reuses the existing `require_admin` bearer-key decorator. No new credential is introduced, and the Android/Web admin client keeps the key only in module memory.

Base path: `/api/admin/platform/v1`

| Method | Path | Purpose | Side effects |
|---|---|---|---|
| GET | `/identity` | Exact runtime/build identity | None |
| GET | `/overview` | Statistics and all integration states | Bounded probes |
| GET | `/statistics` | Database-backed operational counters | None |
| GET | `/integrations` | Per-boundary evidence | Bounded probes |
| GET | `/evidence?limit=30` | Persisted evidence receipts | None |
| POST | `/canaries` | Readiness or confirmed completion canary | Evidence insert; completion may incur provider cost |
| GET | `/openapi.json` | OpenAPI 3.1 contract | None |

Completion canaries accept only aliases currently enabled in `llm_routes`, require literal `confirmed: true`, and have a database-backed 30-second actor cooldown. Provider credentials and raw secret material are never returned.

## Runtime evidence

Every persisted receipt contains:

- request and actor UUIDs;
- scope and exact outcome;
- exact source revision or the literal `unverified`;
- process runtime UUID;
- canonical SHA-256 of the evidence payload;
- JSON evidence and server timestamp.

Success is returned only after the inserted UUID is read back from PostgreSQL. If persistence or readback fails, the endpoint fails closed.

Container builds inject `github.sha` as `SOVEREIGN_SOURCE_REVISION`. An image digest can be injected as `SOVEREIGN_IMAGE_DIGEST` by the deployment controller. Missing or malformed identities are shown as unverified and degrade the platform.

## Runtime hardening

The production service uses:

- bounded request bodies (1 MiB minimum, 128 MiB maximum, 64 MiB default);
- generated or validated UUID request IDs;
- no-store API responses, MIME sniffing protection, frame denial, strict referrer and permissions policy;
- server timing without secret or SQL disclosure;
- non-root container user;
- `no-new-privileges`, all Linux capabilities dropped, bounded PIDs, a no-exec tmpfs, init and graceful stop;
- private database and provider routes already owned by the deployed backend;
- no generic shell, Docker socket, arbitrary SQL endpoint, or direct PatchMon database access.

## Samsung Galaxy Tab A9 / Android contract

The platform tab is the first admin view after the existing key check. It is optimized for Android WebView and tablet portrait/landscape:

- 48 px minimum interactive targets and 52 px tab targets;
- safe-area padding, contained overscroll, no hover-only actions;
- one-column phone layout, two-column Tab A9 portrait layout, wider landscape grids;
- responsive cards with bounded text and no horizontal page overflow;
- reduced-motion support;
- explicit status text and icons, not color alone;
- a second user confirmation before a real provider completion request.

The frontend calls the existing production base URL and includes the same in-memory bearer key through `adminApiClient`.

## Deployment and rollback

1. Run Python contract/service tests and frontend type/build checks.
2. Run Android fast and standard validation plus the UI contract audit.
3. Apply migration 025 before serving the new evidence routes.
4. Build the image with the exact commit SHA.
5. Deploy to the private backend network.
6. Verify `/identity`, `/overview`, and a readiness canary.
7. Confirm the evidence row SHA and runtime/source identity.
8. Run the completion canary only when provider cost and current provider health are accepted.

Rollback is reversible: deploy the prior image. Migration 025 is additive and can remain in place; deleting evidence during rollback is neither required nor permitted. The old health endpoints remain compatible and delegate to the new service.

## Operational blockers

The control center must preserve—not conceal—external blockers. At implementation time:

- PatchMon runtime health is degraded because its server is missing the required edge-network membership.
- Private LiteLLM readiness is observable, but real OpenAI completion canaries are blocked by the provider path.
- Milvus projection and R2 byte-level checks remain `defined_not_run` until their private bounded canaries are implemented.

These states prevent an unsupported all-green claim and are prerequisites for full runtime verification, not reasons to weaken the contract.
