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

## 2026-07-03 - [1-Slot Memoization for High-Frequency Logic]
**Learning:** In high-frequency update loops (e.g., 55ms chat pacing), even $O(N)$ operations like word counting or array allocations (like regex pattern arrays) can accumulate significant CPU time and GC pressure. 1-slot memoization for pure functions based on input strings and hoisting allocation-heavy arrays to module scope provide immediate, low-risk wins.
**Action:** Implement simple 1-slot memoization for pure utility functions used in frequent render/effect ticks. Hoist not just regexes, but also the arrays/objects that contain them if they are static.

## 2026-07-04 - [Single-Pass Multi-Attribute Processing and Early Slicing]
**Learning:** Performing multiple independent O(N) array mapping or filtering loops over large repository file structures is highly inefficient and creates substantial memory allocation/GC pressure. Accumulating metadata like duplicate file name counts on-the-fly during a main single pass, reusing pre-computed results like extensions (`byExtension`), and slicing arrays *before* mapping paths (`slice(0, 50).map()`) provides a massive performance and memory efficiency boost.
**Action:** Always process and accumulate multiple structural attributes in a single traversal where possible. When mapping, filtering, or slicing large collections, prefer slicing or filtering *prior* to map projections to avoid allocating large unused intermediate arrays.
