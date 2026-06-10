## 2026-06-10 - [Accessibility in Settings Modal]
**Learning:** Many form components in the app used plain labels without `htmlFor` or `id`, which hinders accessibility for screen readers and reduces clickable areas. Replacing `h4` with `label` for form sections also improves semantic structure.
**Action:** Always ensure that form labels are programmatically linked to their controls and icon-only buttons have descriptive ARIA labels.
