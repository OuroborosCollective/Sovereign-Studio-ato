## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-21 - [Optimize GitHub Tree Array Processing]
**Learning:** Chaining array methods like `.filter().map().slice()` on potentially huge payloads (like full GitHub API repository trees) forces multiple O(N) traversals and creates intermediate array allocations in memory.
**Action:** Use a single `for` loop with an early break condition (e.g., stopping when reaching the desired slice size) instead of method chains to minimize memory footprint and execution time.

## 2026-05-26 - [CPU Leak in React Animation Loops]
**Learning:** Forgetting to return a cleanup function in `useEffect` hooks that call `requestAnimationFrame` leads to orphaned loops running in the background. Every re-mount of the component spawns a new loop, causing a compounding, severe CPU and memory leak.
**Action:** Always capture the ID returned by `requestAnimationFrame` and call `cancelAnimationFrame(id)` in the `useEffect` cleanup function.
## 2025-05-14 - [Security Fix: Insecure Randomness]
**Learning:** Using `Math.random()` and `Date.now()` for ID generation is insecure and can lead to collisions or predictability in sensitive contexts (like user sessions or trace IDs).
**Action:** Always prefer `crypto.randomUUID()` for generating unique identifiers in both browser and Node.js environments.
