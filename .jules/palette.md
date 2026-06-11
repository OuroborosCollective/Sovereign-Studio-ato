## 2024-05-20 - [Accessibility and Tactile Feedback]
**Learning:** Icon-only buttons in the main shell and modals were missing ARIA labels, and primary actions lacked tactile feedback. Additionally, Vitest tests needed to be updated to match the German localization of the UI.
**Action:** Always add 'aria-label' to icon-only buttons. Use 'active:scale-95 transition-all' for a snappy, tactile feel on main action buttons. Ensure tests use localized strings like 'Auftrag starten' instead of 'Laden' or 'Start Order'.
