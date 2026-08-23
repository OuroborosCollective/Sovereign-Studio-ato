# Live Workspace isolated desktop worker v1

Issue: #1617  
Status: repository implementation and revision-bound CI contract; no production deployment claim

## Decision

The implementation uses a minimal native desktop worker, not Bytebot.

The upstream repository [bytebot-ai/bytebot](https://github.com/bytebot-ai/bytebot) was evaluated at archived commit [3d37894ce07ef8d8b40adc7fd309ad96c2a71313](https://github.com/bytebot-ai/bytebot/tree/3d37894ce07ef8d8b40adc7fd309ad96c2a71313). It is not retained as a dependency, fork, or bundled image because its broader multi-service, agent/LLM and privileged-desktop shape is incompatible with this narrow worker boundary.

The worker is admitted only from a fresh independent PatchMon/Docker/OTBA readback. That readback is bound to one live session, exact Attempt, self-contained worktree revision, immutable image digest, OCI source-revision label, and an integrity-checked sensor receipt. The repository contract does not itself assert that a host has supplied such a production readback.

## Runtime topology

The worker and view gateway are separate non-root services:

| Service | Network | Authority |
|---|---|---|
| desktop-worker | worker backplane only | GUI processes, one writable Attempt checkout, local bounded input controller |
| desktop-view-gateway | worker backplane plus private view-client network | authenticated view-only stream relay; no workspace or controller socket |
| private view client | view-client network only | cookie-authenticated viewing; cannot resolve the worker service |

Both networks are internal-only and neither service publishes a host port. The gateway's per-Attempt signing key is mounted only into the gateway and is never written to the repository, worker filesystem, telemetry, or browser output.

## Hard security boundary

The worker or gateway is rejected unless all applicable properties hold:

| Property | Required state |
|---|---|
| Image | exact repository manifest digest read back through RepoDigests, separate local OCI config identity, plus exact OCI source revision |
| Privilege | non-privileged; no host namespaces; no engine socket |
| Process authority | no-new-privileges and all capabilities dropped |
| Filesystem | readonly root; only bounded tmpfs paths writable |
| Worker workspace | exactly one writable /workspace mount bound to current Attempt worktree |
| Gateway mounts | no workspace or input-controller mount |
| Network | internal networks, default-deny egress, no published port |
| Secrets and models | no production credential or LLM routing surface |
| Lifecycle | restart count zero; no restart policy; bounded wall and idle lifetime |
| Session | runtime, image, Attempt, worktree, head, scopes, and admission match |
| View stream | one-use signed short-lived capability bound to gateway runtime/container/image, opaque cookie, authenticated gateway mode |
| Input stream | dedicated controller UID, current USER_CONTROLLED lease, revoked-lease replay denial, one-use request hash retained through expiry |

The controller has no shell, host-control, arbitrary process, or arbitrary network operation. It accepts a short allow-list of normalized viewport/window/screenshot observations and pointer/keyboard operations. It emits only SENT, OBSERVED, BLOCKED, or UNKNOWN semantics; those outputs never prove an external effect.

## Staged admission

An admission ID depends on an observed running container, so there is no unsafe precomputed admission:

1. Start the worker with exact static session/Attempt/image bindings but no admission ID. The controller remains effect-blocked.
2. Collect a fresh, independent worker readback and mint DesktopWorkerAdmissionV1.
3. The dedicated controller UID binds that exact admission. A different or second admission is refused.
4. Start the optional gateway with that final admission ID and collect DesktopViewGatewayReadbackV1.
5. Only then issue DesktopViewGrantV1 and a private signed gateway capability.

Input delivery has a second effect-time check. The host controller presents a current reconciliation and user-control lease, then updates the local lease state. GIVE BACK records the active lease/reconciliation identity as revoked and clears that state before any new GUI effect can be accepted; replaying an old USER_CONTROLLED update is rejected. A pre-existing request is limited by expiry and each consumed request hash is retained until expiry, with fail-closed cache capacity.

TAKE OVER / GIVE BACK interaction remains owned by #1620. This worker consumes its lease contract and does not introduce a second owner-control system.

## Operation and evidence

The image provides Xvfb, Openbox, xterm, Mousepad, Firefox ESR, Git, a view-only VNC/noVNC upstream, and a local Unix-socket controller. The GitHub Actions canary builds a local image with the checked-out source-revision label and a self-contained detached Attempt checkout at that exact revision. It verifies local config-identity/label/Attempt equality; production validation additionally requires that the configured repository manifest reference appears in Docker RepoDigests. It verifies:

- container-side Git head, owner-accessible workspace, and no extra workspace mount;
- hardened flags, internal-network isolation, no public ports, and explicit removal;
- desktop-user controller refusal, dedicated controller-UID admission bind, bounded view, one allowed input, retained request-replay denial, and GIVE BACK plus lease-update-replay denial;
- anonymous view denial, one-use gateway-runtime-bound signed-capability cookie exchange, and two authenticated WebSocket reconnects.

CI is implementation evidence only. It is not a deployment receipt, an external success receipt, or a target-effect verdict.

## Controlled runtime status

A production deployment/readback requires an explicitly registered, revision-and-digest-bound managed desktop-worker template and canary path. The currently available managed Compose and VPS inspection interfaces do not expose such a template; therefore this document makes no claim that the worker is deployed or independently running on a VPS.

## Continuity policy

Continuity data may be observed or logged separately for investigation. It is not read by the desktop-worker workflow, does not decide CI, does not trigger deployment, does not mutate a workspace, and cannot block a GitHub workflow, merge, release, or runtime action.

## Non-goals

- No second agent, planner, model router, or secret store.
- No public VNC/noVNC endpoint.
- No reuse of the global multi-workspace code-server instance.
- No claim that an observed desktop action changed an external target.
- No expansion of TAKE OVER / GIVE BACK beyond #1620.
