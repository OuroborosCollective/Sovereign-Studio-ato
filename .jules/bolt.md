## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2025-05-28 - [Memoizing O(N) render-time processing]
**Learning:** O(N) operations like string formatting (line numbering) or array normalization in frequently re-rendering components (Chat inputs) should be wrapped in `useMemo` to avoid main-thread lag during rapid user input.
**Action:** Identify and memoize data transformations that don't need to run on every keystroke if their source data hasn't changed.
