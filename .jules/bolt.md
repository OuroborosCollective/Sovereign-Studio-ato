## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-22 - [Bolt: Canvas Offscreen Rendering]
**Learning:** High-frequency `strokeRect` calls (e.g., 380+ per frame) in a `requestAnimationFrame` loop for static elements (like grids) cause severe main thread bottlenecks. Furthermore, missing `cancelAnimationFrame` in `useEffect` cleanups creates silent memory and CPU leaks upon component unmounting.
**Action:** Always pre-render static canvas elements to an offscreen canvas (`document.createElement('canvas')`) and draw them using a single `ctx.drawImage` call per frame. Always store the animation frame ID and call `cancelAnimationFrame` in the hook cleanup.
