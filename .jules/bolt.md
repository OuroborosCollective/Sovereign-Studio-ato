## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2025-05-28 - [Memoization of expensive computations in MainContent and ChatSidebar]
**Learning:** React components that re-render frequently (e.g., on every keystroke or progress update) can suffer from lag if they contain expensive O(N) string processing or data normalization in their render body.
**Action:** Always memoize computations like code line numbering (split/map/join) and data normalization from props (like  from ) using `useMemo` to ensure smooth UI interaction.

## 2025-05-28 - [Memoization of expensive computations in MainContent and ChatSidebar]
**Learning:** React components that re-render frequently (e.g., on every keystroke or progress update) can suffer from lag if they contain expensive O(N) string processing or data normalization in their render body.
**Action:** Always memoize computations like code line numbering (split/map/join) and data normalization from props (like `safeMessages` from `chatMessages`) using `useMemo` to ensure smooth UI interaction.
