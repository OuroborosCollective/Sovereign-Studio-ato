# Sovereign desktop worker

This directory contains the isolated desktop-worker implementation for Live Workspace issue #1617.

It is intentionally a GUI boundary only. It does not create agents, call an LLM, route model traffic, hold production credentials, decide completion, or become an evidence authority.

## Security shape

The immutable worker image contains Xvfb, Openbox, xterm, Mousepad, Firefox ESR, Git, a view-only VNC/noVNC upstream, and a local Unix-socket controller.

The deployment template creates two separate non-root services on two internal-only networks:

- desktop-worker is the only service with the one writable /workspace Attempt checkout and the bounded input controller. It is on the worker backplane only.
- desktop-view-gateway is an optional, read-only profile. It has neither workspace nor controller-socket mount. It relays only authenticated, view-only noVNC traffic from the private client network to the fixed worker upstream.

Neither service publishes a host port, mounts an engine socket, uses host namespaces, retains capabilities, or has a writable root filesystem. Restart is disabled; the worker also terminates itself at bounded wall-clock or idle limits.

## Required staged operator flow

The final admission ID depends on an independent readback, so the worker is deliberately started in a safe pre-admission state:

1. Create a self-contained Attempt checkout at the exact intended Git revision. Do not bind a host path by identity.
2. Validate the environment with operator-validate.py: exact self-contained Attempt HEAD, immutable repository manifest reference, local OCI config identity, and OCI source-revision label must agree. Start only desktop-worker.
3. Collect a fresh independent PatchMon/Docker/OTBA readback and create DesktopWorkerAdmissionV1.
4. Bind that exact admission through the controller's dedicated host-control UID. Until this succeeds, every GUI request is rejected.
5. Start the optional view-gateway profile with the final admission ID and a private, per-Attempt gateway-key file mounted only into that sidecar.
6. Collect a separate gateway readback before issuing a DesktopViewGrantV1.

The gateway key is never mounted into the worker, returned to the browser, put into telemetry, or written to repository files. The gateway accepts a short-lived signed capability once, bound to its runtime identity, container identity, image, session, admission, Attempt, and head; it exchanges that capability for an opaque HttpOnly; SameSite=Strict cookie, and strips capability/cookie headers before proxying the fixed WebSocket upstream.

## Input and consent

Viewing is the default. The controller accepts a request only from UID 10002, verifies every session/admission/image/Attempt/worktree/head/principal/scope binding before a GUI effect, and retains each consumed input request hash until grant expiry. It fails closed at replay-cache capacity rather than evicting a still-live request.

Input additionally requires a current USER_CONTROLLED lease update at the controller. A GIVE BACK lease update records the active lease as revoked and clears state immediately; a request created before it is rejected at delivery time, and replaying the prior USER_CONTROLLED update cannot restore authority. TAKE OVER / GIVE BACK remains owned by #1620; this worker consumes its lease contract and does not create a second ownership system.

Controller receipts are limited to SENT, OBSERVED, BLOCKED, or UNKNOWN semantics and hashes/bounded metadata. They never verify an external target effect.

## Revision-bound canary

The GitHub Actions canary:

- builds the image with an OCI source-revision label equal to the checked-out revision and validates that the local config identity, source label, and Attempt HEAD agree;
- creates a self-contained detached Attempt checkout at exactly that revision;
- verifies container-side Git head and writable workspace access as UID 10001;
- checks immutable/non-privileged/no-public-port flags, two internal networks, and removal;
- proves the desktop user is refused by the controller while the dedicated host-control UID can bind an admission;
- proves a current input lease permits one bounded input, replay is rejected, and GIVE BACK blocks a fresh post-revocation input;
- proves anonymous view access is denied, a bound private capability creates an opaque cookie, and two authenticated WebSocket upgrades reconnect.

This is repository and CI evidence only. It is not a production deployment or a target-effect verdict. A production runtime claim requires a separately registered managed desktop-worker deployment/readback path.

## Explicit upstream decision

bytebot-ai/bytebot is not used as a runtime dependency or fork. Its archived, multi-service upstream shape carries broader agent/LLM and privileged-desktop surface than this narrow worker boundary permits. The native worker retains only the required desktop capability while preserving the existing controller, Attempt, and evidence boundaries.
