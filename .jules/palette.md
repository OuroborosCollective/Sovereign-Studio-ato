## 2025-05-15 - [Title Attributes for Icon-Only Buttons]
**Learning:** Providing 'aria-label' is essential for screen readers, but sighted users also benefit from native hover tooltips provided by the 'title' attribute on icon-only buttons, especially in complex settings modals.
**Action:** Always pair 'aria-label' with an identical 'title' attribute for icon-only buttons to ensure universal accessibility and discoverability.

## 2025-07-17 - [Accessible Keyboard Dropdown Navigation]
**Learning:** In complex workspaces, utility/shortcut menus like tool launchers benefit significantly from keyboard-only navigation options (`ArrowUp`, `ArrowDown`, `Escape`, `Enter`). To make them fully accessible and friendly to non-mouse users, focus should be explicitly moved/managed via DOM refs or stateful focused identifiers, and focus must be restored to the launcher trigger button upon menu closure.
**Action:** Always capture keyboard events (`Escape` to close and restore focus; `ArrowUp`/`ArrowDown` to navigate) on custom dropdown overlays, and include clear, compact visual cues like `[↑↓ Navigieren]` for sighted users.

## 2025-07-18 - [Stateful Dynamic Toggle Accessible Names]
**Learning:** For overlay triggers (such as menus, collapsible panels, and launchers) where the action of the toggle button is status-dependent, the trigger button's accessible name and visual tooltip must update dynamically based on the current toggle state. It is insufficient to state 'open' when already open.
**Action:** Toggle buttons should dynamically switch both 'aria-label' and 'title' from action-oriented labels (e.g., 'Tool Launcher öffnen' when closed) to close-oriented labels (e.g., 'Tool Launcher schließen' when open).

## 2025-07-19 - [Accessible Input Association in Provider Card Lists]
**Learning:** In dynamically generated card lists (such as API keys or settings lists) where inputs are wrapped inside custom containers without visible labels next to them, screen readers fail to associate the fields with their parent providers. Relying on visual context alone causes inputs to have blank accessible names.
**Action:** Always provide an explicit, programmatically constructible `aria-label` attribute (e.g. `aria-label={`${provider.name} API-Key`}`) on credentials or technical fields rendered inside custom grid/card rows.

## 2025-07-20 - [Accessibility and Hover Tooltips for Modal Close Buttons]
**Learning:** Icon-only overlay controls (like '×' close buttons in bottom sheet sheets or modal dialogues) must have consistent hover tooltips via the 'title' attribute in addition to 'aria-label' so that non-screen reader users can discover their specific functions effortlessly.
**Action:** Ensure all close/dismiss icon buttons in slide-overs, panels, or custom sheet dialogs consistently specify both 'aria-label' and matching 'title' tooltips.
