# Desktop Worker decision for #1617

Decision date: 2026-08-23  
Decision: `MINIMAL_NATIVE_DESKTOP_WORKER`

## Bytebot admission record

The candidate was examined at `bytebot-ai/bytebot@3d37894ce07ef8d8b40adc7fd309ad96c2a71313`, the then-current archived `main` head. It is Apache-2.0, but it is not reused in this repository.

Reasons:

- The upstream repository was archived by its owner on 2026-03-07.
- Its documented topology includes a desktop, autonomous agent service, task UI, PostgreSQL and direct desktop-control APIs.
- Its documented deployment accepts independent provider keys and uses LiteLLM for multi-provider routing.
- Its default desktop API is documented as unauthenticated for localhost development.

That ownership, routing and topology exceed the #1617 boundary. No Bytebot source, image, provider configuration, task runtime or credential flow is copied.

Primary source records:

- https://github.com/bytebot-ai/bytebot/tree/3d37894ce07ef8d8b40adc7fd309ad96c2a71313
- https://github.com/bytebot-ai/bytebot/blob/3d37894ce07ef8d8b40adc7fd309ad96c2a71313/LICENSE
- https://docs.bytebot.ai/core-concepts/architecture

## Native worker boundary

The native worker contains only a visible Linux desktop, editor, terminal, browser, bounded local desktop bridge and a single exact Attempt workspace mount. It contains no LLM client, provider key, task planner, repository clone, database connection, success evaluator or permanent recording.

Admission is fail-closed on:

- immutable worker image digest and source revision;
- one current attempt/worktree identity and its expected base/head revisions;
- non-root execution, read-only root filesystem, `no-new-privileges`, all capabilities dropped, bounded CPU/RAM/PIDs/wall/idle time;
- one internal-only `sovereign-desktop` network, no published ports, host socket, PID/IPC namespace or global home/repository mount;
- distinct private view and input scope material.

A view frame is an observation only. Controller input accepts only listed mouse, keyboard, scroll and focus operations and returns `SENT`, `OBSERVED`, `BLOCKED` or `UNKNOWN`; it never confirms target effect or creates execution truth. Takeover and recording are deliberately excluded from #1617.

Runtime readback is observational Docker evidence. It records the immutable digest, identity labels, hardening, network, mounts, health and canary result, but cannot decide repository, controller or success state.
