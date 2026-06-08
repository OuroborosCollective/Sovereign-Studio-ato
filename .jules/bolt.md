## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-21 - [Optimize GitHub Tree Array Processing]
**Learning:** Chaining array methods like `.filter().map().slice()` on potentially huge payloads (like full GitHub API repository trees) forces multiple O(N) traversals and creates intermediate array allocations in memory.
**Action:** Use a single `for` loop with an early break condition (e.g., stopping when reaching the desired slice size) instead of method chains to minimize memory footprint and execution time.

## 2026-05-23 - [Canvas Component Stateful vs Stateless Map Bottleneck]
**Learning:** When attempting to replace an O(N) internal Map generation inside a canvas reconciliation hook with a cached `useRef` Map (`fabricObjectsMapRef`), it led to a desynchronization state. The canvas instance acts as a source of truth, and if objects are manipulated natively via Fabric.js (outside the hook), the ref Map drops out of sync and leads to UI duplication logic errors.
**Action:** For reconciliation loops tied to an external state engine (like Fabric.js canvas), avoid keeping persistent references unless strictly synchronized via event listeners. Instead, prefer high-performance stateless rebuilds (e.g., using `for` loops instead of `.forEach` closures) to get performance wins without risking state rot.
