---
name: Sovereign Studio Workbench status vocabulary
description: How BuilderContainer surfaces user-facing status (Actions/Files/Logs/Errors/Draft PR) instead of technical module abbreviations, and where the technical view still lives.
---

Sovereign Studio's `BuilderContainer` chat workbench replaced the always-visible
technical module-abbreviation lamps (INT/ROU/PAT/SYN/ORC/LOG/BUD) as *primary*
navigation with five user-facing status chips: Actions, Files (edited files),
Logs, Errors, Draft PR/Workflow status. Chat remains the sole primary
destination; there is no restored sidebar/shell menu.

**Why:** product direction (German-language request) was that engineers/users
should reason about outcomes ("what did the agent do", "what changed", "is
anything broken") rather than internal module names. Technical module lamps
are still valuable for debugging but must not compete with chat as primary UI.

**How to apply:**
- Status slots are derived, never fabricated: see
  `src/features/product/runtime/builderWorkbenchStatus.ts`
  (`deriveWorkbenchStatusSlots` and friends) which computes the 5 slots purely
  from runtime state (`statusLogs`, `workerBlocker`, `chatRepoError`,
  `openhandsJob`, `publishedPrUrl`). Empty states use explicit German labels
  ("Noch keine Actions", "Noch keine bearbeiteten Dateien", "Keine Fehler",
  "Draft PR fehlt") — never mock/sample data.
- The technical module lamps (`ModuleLamps`) still exist and render, but only
  inside an opt-in "Inspector (intern)" view, toggled via a bottom-bar
  INSPECTOR button (`showInspector` state) — never shown by default.
- Product contract validation for this pattern lives in
  `sovereignProductTemplate.ts` (`SovereignWorkbenchStatusSlotId`,
  `workbenchStatusSlots`, `internalOnlyModuleAbbreviations`,
  `SOVEREIGN_BUILDER_WORKBENCH_INVARIANTS`) — keep slot IDs and the
  "no overlap with module abbreviations" invariant in sync if this pattern is
  extended.
- If adding a new status concept, prefer adding a new derived slot function in
  `builderWorkbenchStatus.ts` over reusing/overloading an existing chip.
