## 2025-05-15 - [Title Attributes for Icon-Only Buttons]
**Learning:** Providing 'aria-label' is essential for screen readers, but sighted users also benefit from native hover tooltips provided by the 'title' attribute on icon-only buttons, especially in complex settings modals.
**Action:** Always pair 'aria-label' with an identical 'title' attribute for icon-only buttons to ensure universal accessibility and discoverability.

## 2026-06-22 - [Tooltips for Truncated Meta-Information]
**Learning:** Dense headers often truncate essential meta-information (like repository paths or model names). Sighted users need an easy way to reveal the full string without leaving the current view or resizing the window.
**Action:** Apply the `title` attribute to any `div` or `span` that uses `text-overflow: ellipsis` to provide a non-intrusive way to view the full value on hover.
