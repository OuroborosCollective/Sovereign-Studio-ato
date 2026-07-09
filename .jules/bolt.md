## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2026-06-23 - [Memoizing derived state in ChatSidebar]
**Learning:** Memoizing derived state like 'safeMessages' not only prevents redundant O(N) normalization on every keystroke in a controlled input, but also stabilizes object identity. This prevents unnecessary triggerings of 'useEffect' hooks (e.g., for auto-scrolling) that depend on these objects.
**Action:** Always memoize derived objects/arrays in components with frequent re-renders (like those with text inputs) to maintain stable identities for downstream hooks and memoized children.

## 2025-05-29 - [Referential Stability for Fallback Arrays]
**Learning:** In a large orchestration component like 'App.tsx', failing to memoize safe fallback arrays (e.g., `const safe = data || []`) causes all dependent `useMemo` and `useCallback` hooks to invalidate on every render cycle, even when the underlying data is identical. This leads to massive redundant processing in expensive logic like health reports and diff generation.
**Action:** Always wrap safety/normalization logic for arrays and objects in 'useMemo' at the highest possible level to preserve referential identity across renders.

## 2026-07-09 - [Hoisting Regex and Memoizing Markdown Sub-components]
**Learning:** Hoisting regular expressions to the module scope in a frequently called tokenizer (like `ChatMarkdown`) prevents thousands of redundant object re-instantiations during streaming or paced text updates. Combining this with memoization of small, static sub-components (`CodeBlockView`, `TextSegmentView`) eliminates O(M*N) re-render overhead when new messages are added or parent timers (thinking status) tick.
**Action:** Always hoist regex patterns used in loops or frequently called functions to module constants. Use `React.memo` for all sub-components in the chat message tree to isolate them from high-frequency parent state updates.
