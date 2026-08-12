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

## 2025-07-20 - [Hover Tooltips for Truncated Paths]
**Learning:** In sidebar navigators where workspace files or repository structures are listed, long paths and deeply-nested file names are often visually truncated (`text-overflow: ellipsis`) to fit narrow column views. This leaves users guessing or clicking through to find the correct file.
**Action:** Always assign a native `title` attribute matching the full, untruncated path (e.g., `title={file.path}`) on file list items to ensure they are fully discoverable on hover for sighted and keyboard-navigated users.

## 2025-07-21 - [Avoiding Label Ambiguity between Inputs and Trigger Buttons]
**Learning:** Assigning identical aria-labels to adjacent components (e.g., "Datei suchen" on both a text input field and its executing submit button) creates ambiguity for screen readers and breaks testing frameworks' element queries (e.g., `getByLabelText`).
**Action:** Ensure that input fields retain object-oriented labels (e.g., `aria-label="Datei suchen"`) while their corresponding trigger buttons utilize action-oriented names (e.g., `aria-label="Datei im Repository suchen"`).

## 2025-07-22 - [Stateful Disclosure Button Accessibility]
**Learning:** Disclosure widgets (like findings panels, accordions, and error drawers) need explicit ARIA state triggers like `aria-expanded` and clear native tooltips (via `title`) to inform users about toggle states before and after expansion.
**Action:** Toggle/disclosure buttons should pair a reactive `aria-expanded` state with descriptive, stateful hover tooltips (`title`) describing the consequences of toggling the element.

## 2025-07-23 - [Interactive vs. Informative Inline Badges]
**Learning:** Conversational event logs and stream cards often display inline file paths. When these are interactive (i.e. click-to-open), they benefit from both descriptive visual 'title' hover tooltips and clear 'aria-label' attributes that convey the action (e.g., 'Repo Datei öffnen: path'). If they are merely static/informative, hover 'title' should default to the full path and any interactive actions should be removed to prevent confusing screen reader announcement states.
**Action:** Always condition 'aria-label' and 'title' attributes in inline custom badge components on the presence of click handler callbacks to cleanly distinguish between active elements and static information tags.

## 2025-07-24 - [Accessible Hover and State-Dependent Discovery for Inline Sub-Cards]
**Learning:** Complex sub-cards (such as changelog previews, repair sheets, and workbench status cards) often render context-sensitive action items (such as copying content, applying a mission, or opening deep-links). Sighted and keyboard-navigated users require clear visual cues on action boundaries, and screen readers benefit from descriptive action-oriented `aria-label` and `title` attributes that update based on active/blocked/pressed states.
**Action:** For interactive buttons within secondary workspace sheets and cards, always pair clear, detailed `title` tooltips with stateful, dynamic descriptive accessible names (e.g., using ternary expressions matching active/disabled states) to prevent confusion.

## 2025-07-25 - [Consistent Language in Accessible Attributes]
**Learning:** When adding accessibility attributes like `aria-label` and `title` hover tooltips, they must precisely match the primary language used in the surrounding visual components and text. Mixing languages (e.g., German ARIA/tooltips in an English layout or vice-versa) degrades the experience for screen readers and creates confusion for internationalized users.
**Action:** Always verify the surrounding context language and use matching, consistent localization in all added accessible labels, tooltips, and status descriptions.

## 2025-08-01 - [Accessible Roadmap Step Lists and Summaries]
**Learning:** For interactive or descriptive workflow step/roadmap lists, screen readers struggle to parse visual symbols (like checkmarks, warning icons, triangles) or truncated names without appropriate list roles and state-dependent text fallbacks.
**Action:** Always wrap lists of workflow steps in elements with `role="list"`, assign `role="listitem"` and proper `aria-current="step"` on active items, and pair them with localized description titles (e.g., `Abgeschlossen: Schritt`, `Aktueller Schritt: Schritt`) as well as native hover `title` tooltips for truncated visuals.

## 2025-08-02 - [Lazy-Loaded File Tree Accessibility]
**Learning:** For dynamic, lazy-loading directory trees (such as remote file lists in a VPS Connector), interactive nodes need clear distinction between files and folders. Folders must expose their state via `aria-expanded` and stateful toggle actions to help screen readers understand current layout status.
**Action:** Always assign dynamic, state-dependent `aria-label` and matching native `title` tooltips for folder trees, and explicitly manage `aria-expanded` attributes on directories.

## 2025-08-03 - [Accessible Metric and Dashboard Panels]
**Learning:** Relying on `aria-hidden` and custom `aria-label` tags on generic wrapper elements (like `div` or `span` with no semantic role) to describe statistics values hides them from screen readers entirely, since assistive technologies ignore `aria-label` attributes on non-semantic tags. Transforming statistical tables/grids into semantically meaningful layouts like unordered lists (`<ul>`/`<li>`) with native visual text keeps the data fully visible, accessible, and structured for linear screen reader flow.
**Action:** Always structure sets of dashboard metrics or cards using semantic lists (`<ul>`/`<li>` with `list-none`), ensure visible text remains accessible to screen readers, and pair them with matching native hover `title` attributes on the parent items for clean, standard-compliant UX and accessibility.

## 2025-08-04 - [WAI-ARIA Radiogroup Keyboard Model]
**Learning:** For choice cards/dialogues containing lists of options acting like a radio group (such as asking for user decisions), mouse-only accessibility is insufficient. Standard-compliant keyboard-only navigation requires capturing Arrow keys (`ArrowUp`/`ArrowDown`/`ArrowLeft`/`ArrowRight`), roving `tabIndex` parameters (`tabIndex={0}` on the active/first option, and `-1` on others), and managing dynamic focus to allow screen reader and keyboard users to naturally cycle between options.
**Action:** Always implement the WAI-ARIA Radio Group pattern for button lists acting as mutual choices, pair with high-visibility dynamic outline styles on focus, and test arrow key wrapping behavior.
