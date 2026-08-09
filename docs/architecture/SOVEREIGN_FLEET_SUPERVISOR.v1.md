# Sovereign Fleet Supervisor V1

This vertical slice implements the bounded planning and projection layer requested by
#1305 and its child issues. It is intentionally not a second execution platform.

## Canonical ownership

| Concern | Owner |
| --- | --- |
| Workspaces, repository mutations, Draft PR creation | existing repository runtime and controller |
| GitHub reads / CI evidence | existing authenticated broker and GitHub runtime |
| Fleet plan, conflict detection, worker envelope validation, verdict/projection | `agent_runtime/fleet_supervisor.py` |
| Fleet controller ingress | `/api/internal/controller/fleet/*-preview` |
| ChatGPT operator view | read-only MCP tools in `tools/sovereign-chatgpt-mcp/server.py` |
| Browser Draft-PR consent | `DraftPrActionPreview` before the existing server-side Draft-PR gate |

The backend mirror at `backend/agent_runtime/fleet_supervisor.py` must remain
byte-identical to the production module under `scripts/sovereign-backend/`.

## Issue mapping

- **#1306:** `FleetTask`, `FleetPlan`, deterministic SHA-256 plan binding,
  dependency-cycle rejection, and fail-closed conflict lanes.
- **#1307:** `FleetWorkerAssignment` binds a task to an existing controller run
  and workspace identity. Worker events permit only
  `WORKER_COMPLETED_UNVERIFIED`, never a verified or merged result.
- **#1308:** `evaluate_fleet_verdict` requires exact base/head/workspace equality
  and exact-head successful checks before returning `MERGE_CANDIDATE`. It does
  not call merge APIs. `MERGED` and `RUNTIME_VERIFIED` require supplied
  authenticated readbacks.
- **#1309:** `build_fleet_projection` and
  `fleet_plan_read`, `fleet_status`, `fleet_lane_status`,
  `fleet_blockers`, and `fleet_evidence_gaps` are projection-only.
  Stale main-head evidence marks commands blocked.

## Fail-closed planning

Tasks may share a parallel lane only when every candidate explicitly proves
independence and none of these intersections exists:

- changed path;
- canonical architecture owner;
- invariant scope;
- mutation resource;
- lock scope.

Missing source-path or ownership evidence results in
`UNPROVEN_INDEPENDENCE` and serial lanes. The MCP source reader deliberately
does this when authenticated GitHub status does not provide changed paths.

## Draft PR consent

The sidebar and `/pr` route now open a concrete action preview containing the
repository, branch, expected head, evidence count/source, and mission. Cancel is
focused first. Confirming proceeds to the existing server-side prepare/create
Draft-PR route, which remains authoritative and rechecks its evidence.

No access token, secret, raw log, merge control, deploy control, or direct
worker mutation is exposed through the Fleet projection tools.
