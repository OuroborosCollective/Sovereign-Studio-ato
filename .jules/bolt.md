## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-21 - [Optimize GitHub Tree Array Processing]
**Learning:** Chaining array methods like `.filter().map().slice()` on potentially huge payloads (like full GitHub API repository trees) forces multiple O(N) traversals and creates intermediate array allocations in memory.
**Action:** Use a single `for` loop with an early break condition (e.g., stopping when reaching the desired slice size) instead of method chains to minimize memory footprint and execution time.
## 2026-05-23 - [Canvas Optimization: drawImage vs strokeRect]
**Learning:** Drawing hundreds of primitives (`strokeRect`) inside a `requestAnimationFrame` loop causes severe CPU overhead, even for simple static grids. A single `ctx.drawImage()` call referencing a pre-rendered offscreen canvas is massively more performant.
**Action:** Pre-render static background elements to an offscreen canvas (`document.createElement('canvas')`) once on mount, and use `drawImage` in the render loop for high-frequency updates.
