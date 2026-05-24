## 2026-05-19 - [Gemini 404 Fix & Key Setup UX]
**Learning:** Hardcoded model names in the frontend can lead to breaking changes if the provider (Google Gemini) retires or changes preview model strings. Always ensure fallback or stable model identifiers are used. Corrupted HTML at the end of files (stray braces/scripts) can break entire app execution and Capacitor syncs.
**Action:** Use stable model identifiers (e.g., `gemini-1.5-flash`) instead of dated previews. Implement automated UX prompts for missing API keys to reduce "Denkprozess Fehler" reports.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-21 - [Optimize GitHub Tree Array Processing]
**Learning:** Chaining array methods like `.filter().map().slice()` on potentially huge payloads (like full GitHub API repository trees) forces multiple O(N) traversals and creates intermediate array allocations in memory.
**Action:** Use a single `for` loop with an early break condition (e.g., stopping when reaching the desired slice size) instead of method chains to minimize memory footprint and execution time.
## 2026-05-22 - [Optimize High-Frequency Rendering & Fix Canvas Memory Leak]
**Learning:** Initializing high-frequency static rendering (like drawing grids using multiple `strokeRect` commands) inside a `requestAnimationFrame` loop creates hundreds of unnecessary draw calls per frame, leading to CPU bottlenecks. Additionally, omitting a `cancelAnimationFrame` cleanup function in a `useEffect` that initiates such loops causes severe memory leaks and background processing drain when the component unmounts and remounts.
**Action:** Pre-render static elements (e.g. grids) into an offscreen canvas (`document.createElement('canvas')`) once during mount, and use `ctx.drawImage` to render the cached result per frame. Always implement a cleanup function returning `cancelAnimationFrame(animationFrameId)` within `useEffect` hooks that handle render loops.
