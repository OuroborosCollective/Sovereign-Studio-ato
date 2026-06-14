## 2026-06-14 - Selective Accessibility Testing
**Learning:** Icon-only buttons without labels often lead to fragile tests that rely on 'title' or internal text, which can be inconsistent.
**Action:** Use 'aria-label' consistently for icon-only buttons and query them via 'screen.getByLabelText' in tests to ensure both accessibility and test stability.

## 2026-06-14 - Input Clear Pattern
**Learning:** Users in complex repository editors appreciate quick ways to reset inputs, especially for long URLs.
**Action:** Implement a relative container with an absolute-positioned 'CircleX' icon as a standard 'clear input' pattern for all high-value text fields.
