## 2025-05-18 - Keyboard Navigation for Scrollable Table Containers
**Learning:** Overflow scroll containers (`overflow-auto` / `overflow-y-auto`) holding tabular data are unreachable for keyboard-only users unless explicitly given `tabIndex={0}`, a landmark/region role (`role="region"`), and an accessible name (`aria-label`).
**Action:** Always wrap scrollable tables/lists in a focusable region with `tabIndex={0}`, `role="region"`, and focus ring styles (`focus-visible:ring-2`).
