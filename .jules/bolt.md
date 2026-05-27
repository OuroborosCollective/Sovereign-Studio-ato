## 2025-05-14 - [Security Fix: Insecure Randomness]
**Learning:** Using `Math.random()` and `Date.now()` for ID generation is insecure and can lead to collisions or predictability in sensitive contexts (like user sessions or trace IDs).
**Action:** Always prefer `crypto.randomUUID()` for generating unique identifiers in both browser and Node.js environments.
