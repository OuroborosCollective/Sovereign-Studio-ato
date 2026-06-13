## 2026-06-13 - Localized UI Testing & ARIA Consistency
**Learning:** In a localized UI (German in this case), tests must strictly match the visible strings or use robust ARIA labels. Icon-only buttons without explicit labels cause test failures when using 'getByRole'.
**Action:** Always provide 'aria-label' to icon-only buttons and update test mocks/assertions to match localized UI strings (e.g., 'Auftrag starten' vs 'Laden').
