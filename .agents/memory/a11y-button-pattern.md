---
name: Accessibility button pattern for BuilderContainer
description: Icon-only and compact buttons in BuilderContainer must carry both aria-label and title; PaletteEnhancements tests assert both attributes.
---

`PaletteEnhancements.palette.test.tsx` asserts WCAG 2.5.3 Label-in-Name compliance for every icon/compact button in BuilderContainer and its sub-components. The contract requires **both** `aria-label` and `title` to be present and match expected values.

**Why:** Buttons with only visible icon text (☰, ▴/▾, ✕, "RT") are invisible to screen readers without explicit accessible names. `title` provides the browser tooltip; `aria-label` is the programmatic accessible name. `getByRole('button', { name: /pattern/i })` matches against the accessible name, which comes from `aria-label`.

**How to apply:** For every new icon-only or compact-label button added to BuilderContainer or its TopBar/SideDrawer sub-components:
- Add `aria-label="<German action label>"` — use the same phrasing as the test pattern
- Add `title="<German action label>"` — typically identical to aria-label (or shorter)
- For toggle buttons, make both attributes dynamic based on state (e.g. `panelOpen ? "Panel schließen" : "Panel öffnen"`)
- Check `PaletteEnhancements.palette.test.tsx` for the expected string before implementing

The RT button is special: its visible text "RT" must appear inside the accessible name to satisfy Label-in-Name (`aria-label="RT – Runtime Quelle"`).
