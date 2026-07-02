---
name: BuilderContainer TopBar layout constraints
description: TopBar in BuilderContainer is extremely space-constrained on mobile (393px container). Rules for safe rendering.
---

## Rules

1. **Ampel in TopBar must use `compact` prop** — `<Ampel status={status} compact />`. Without it, the text label ("bereit", "thinking"…) overflows the flex row and wraps other items.

2. **Sovereign title needs `whiteSpace: "nowrap"`** — the brand name "Sovereign" breaks mid-word without it. Parent title container also needs `overflow: "hidden"`.

3. **CreditDisplay only when `userLoggedIn && credits !== undefined`** — at startup credits = 0 and user is anonymous; without the gate the badge shows false "0 CR" amber warning. `isLow` threshold must be `credits > 0 && credits < 50`.

4. **TopBar flex items order** (left → right): ☰ menu | title (flex:1) | CreditDisplay (gated) | avatar button | Ampel (compact) | RT source button | panel toggle ▴/▾.

**Why:** Task agent (Issues #459, #460, #461) added CreditDisplay, user avatar, and SkillScanPanel to BuilderContainer without adjusting the TopBar layout. Combined with a JSX root-element bug (auth modals outside `<section>`), resulted in parse error + crowded TopBar.

**How to apply:** Before adding any new element to TopBar, check whether the compact flex row can accommodate it. Use `flexShrink: 0` only on essential fixed-width items; let the title div shrink.
