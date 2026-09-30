# Palette Journal - UX & Accessibility Learnings

## 2025-05-18 - Decorative Icons in Structured Interactive Cards
**Learning:** Decorative icons inside interactive UI containers (like `?` badges in question cards or warning icons in alert cards) need explicit `aria-hidden="true"` attributes to prevent screen readers from reading raw punctuation symbols aloud.
**Action:** Always verify that decorative icons, emojis, and status symbols in components have `aria-hidden="true"` and interactive controls have explicit focus ring classes (`focus-visible:ring-2`).
