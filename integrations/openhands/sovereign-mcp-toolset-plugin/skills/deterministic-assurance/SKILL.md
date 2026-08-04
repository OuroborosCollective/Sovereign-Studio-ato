---
name: deterministic-assurance
description: Audit ARE/Kappa boundaries, nondeterminism, SQL ordering, canonical encoding, replay, transitions, idempotency, and evidence chains.
triggers:
  - audit determinism
  - verify ARE transition
  - check Kappa contract
  - scan nondeterminism
---

# Deterministic assurance

Use deterministic tooling to distinguish canonical truth, effects, projections, tests, and legacy surfaces.

Scan for randomness, wall clocks, floats, hidden state, generated identifiers, implicit SQL ordering, and uncontrolled effects. Audit Kappa scale, integer representation, bigint use, and canonical encoding at boundaries.

Validate pure transitions with explicit current state, action, transition table, expected version, canonical state hash, and engine version. Use replay only on bounded supplied sequences and compare the expected final hash.

For repeated side-effecting operations, verify request hashes, invocation counts, unique side-effect identities, and terminal result hashes. Idempotency is an observed property, not a tool-name annotation.

Do not infer runtime determinism from a static scan. Do not introduce mocks, fake snapshots, or alternate state stores into a truth path. Preserve side channels as projections and bind all conclusions to their exact source revision and evidence identity.
