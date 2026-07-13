## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2026-06-23 - [Memoizing derived state in ChatSidebar]
**Learning:** Memoizing derived state like 'safeMessages' not only prevents redundant O(N) normalization on every keystroke in a controlled input, but also stabilizes object identity. This prevents unnecessary triggerings of 'useEffect' hooks (e.g., for auto-scrolling) that depend on these objects.
**Action:** Always memoize derived objects/arrays in components with frequent re-renders (like those with text inputs) to maintain stable identities for downstream hooks and memoized children.

## 2025-05-29 - [Referential Stability for Fallback Arrays]
**Learning:** In a large orchestration component like 'App.tsx', failing to memoize safe fallback arrays (e.g., `const safe = data || []`) causes all dependent `useMemo` and `useCallback` hooks to invalidate on every render cycle, even when the underlying data is identical. This leads to massive redundant processing in expensive logic like health reports and diff generation.
**Action:** Always wrap safety/normalization logic for arrays and objects in 'useMemo' at the highest possible level to preserve referential identity across renders.

## 2026-07-02 - [Regex Hoisting in High-Frequency Components]
**Learning:** Components used in high-frequency update paths (like 'ChatMarkdown' inside 'PacedChatText' which updates every 55ms) incur significant overhead if they instantiate/compile regex patterns on every render. Hoisting regex constants to module scope and using '.test()' instead of '.match()' for boolean checks provides a measurable performance boost.
**Action:** Always hoist regex patterns to module-level constants in components that re-render frequently. Use '.test()' for performance-critical boolean checks.

## 2026-07-02 - [Leaky Memoization & Callback Stabilization]
**Learning:** Wrapping a component in 'React.memo' is ineffective if even one prop is an inline arrow function or a non-stabilized object. In 'BuilderContainer.tsx', failing to stabilize the 'onWorkbenchSlotClick' callback initially negated the 'React.memo(TopBar)' optimization.
**Action:** Always audit ALL props of a memoized component to ensure they are stabilized via 'useCallback', 'useMemo', or hoisted constants.

## 2026-07-02 - [1-Slot Memoization for High-Frequency State]
**Learning:** In pacing runtimes like 'assistantResponsePacingRuntime.ts' that are called every 55ms, redundant O(N) regex scans for word counts can be avoided by implementing a simple 1-slot memoization (caching the last input string and its result).
**Action:** Use 1-slot memoization for pure computational helpers that are frequently called with identical inputs during UI animation/pacing cycles.
