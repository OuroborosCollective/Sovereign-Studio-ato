## 2025-05-14 - [Fixed CanvasEngine ReferenceError and Added useGemini Tests]
**Learning:** Found a `ReferenceError: fabricObjectsMapRef is not defined` in `CanvasEngine.tsx` that was causing existing tests to fail. The ref was named `existingFabricObjectsMapRef` but used as `fabricObjectsMapRef`. Also implemented comprehensive hook testing using `@testing-library/react`.
**Action:** Always verify existing test suite health before and after changes. Use `sed` for safe bulk renaming of mismatched identifiers discovered during testing.

## 2026-05-21 - [Redundant Component Definitions in Ouroboros UI]
**Learning:** Duplicate component definitions in the same file (e.g., `GameHUD`) cause immediate TypeScript `TS2451` redeclaration errors and build failures, especially when one version references undefined state (`syncHz`). This often occurs during automated UI generation or merging of partial screens.
**Action:** Always verify component unique naming and scope consistency when adding new Ouroboros screens. Use `pnpm run type-check` to catch these before triggering the full Android build workflow.
## 2026-05-21 - [Optimize GitHub Tree Array Processing]
**Learning:** Chaining array methods like `.filter().map().slice()` on potentially huge payloads (like full GitHub API repository trees) forces multiple O(N) traversals and creates intermediate array allocations in memory.
**Action:** Use a single `for` loop with an early break condition (e.g., stopping when reaching the desired slice size) instead of method chains to minimize memory footprint and execution time.

## 2026-05-23 - [Canvas Component Stateful vs Stateless Map Bottleneck]
**Learning:** When attempting to replace an O(N) internal Map generation inside a canvas reconciliation hook with a cached `useRef` Map (`fabricObjectsMapRef`), it led to a desynchronization state. The canvas instance acts as a source of truth, and if objects are manipulated natively via Fabric.js (outside the hook), the ref Map drops out of sync and leads to UI duplication logic errors.
**Action:** For reconciliation loops tied to an external state engine (like Fabric.js canvas), avoid keeping persistent references unless strictly synchronized via event listeners. Instead, prefer high-performance stateless rebuilds (e.g., using `for` loops instead of `.forEach` closures) to get performance wins without risking state rot.
