## 2025-05-15 - [Title Attributes for Icon-Only Buttons]
**Learning:** Providing 'aria-label' is essential for screen readers, but sighted users also benefit from native hover tooltips provided by the 'title' attribute on icon-only buttons, especially in complex settings modals.
**Action:** Always pair 'aria-label' with an identical 'title' attribute for icon-only buttons to ensure universal accessibility and discoverability.

## 2025-07-17 - [Accessible Keyboard Dropdown Navigation]
**Learning:** In complex workspaces, utility/shortcut menus like tool launchers benefit significantly from keyboard-only navigation options (`ArrowUp`, `ArrowDown`, `Escape`, `Enter`). To make them fully accessible and friendly to non-mouse users, focus should be explicitly moved/managed via DOM refs or stateful focused identifiers, and focus must be restored to the launcher trigger button upon menu closure.
**Action:** Always capture keyboard events (`Escape` to close and restore focus; `ArrowUp`/`ArrowDown` to navigate) on custom dropdown overlays, and include clear, compact visual cues like `[↑↓ Navigieren]` for sighted users.

## 2025-07-18 - [Stateful Dynamic Toggle Accessible Names]
**Learning:** For overlay triggers (such as menus, collapsible panels, and launchers) where the action of the toggle button is status-dependent, the trigger button's accessible name and visual tooltip must update dynamically based on the current toggle state. It is insufficient to state 'open' when already open.
**Action:** Toggle buttons should dynamically switch both 'aria-label' and 'title' from action-oriented labels (e.g., 'Tool Launcher öffnen' when closed) to close-oriented labels (e.g., 'Tool Launcher schließen' when open).
