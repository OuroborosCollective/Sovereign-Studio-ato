---
name: BuilderContainer test quirk
description: A known pre-existing failing test in BuilderContainer.test.tsx, confirmed unrelated to workbench/UI changes — don't waste time re-diagnosing it as a regression.
---

The test `"retries the original Worker request after a diagnostic follow-up"`
in `src/features/product/containers/BuilderContainer.test.tsx` fails on an
unmodified checkout of the repo (verified by diffing against `HEAD` and
re-running in isolation). It fails at the `waitFor(() =>
expect(screen.getByText("Retry beantwortet.")).toBeDefined())` assertion after
clicking the first "Retry" button — likely because multiple components
("Retry" in `WorkerBlockerCard`, `ChatRuntimePanel`, etc.) render matching text
and `getAllByText("Retry")[0]` doesn't hit the one wired to the mocked fetch
sequence, or there's a genuine timing/flakiness issue in the retry flow.

**Why:** worth recording so future work doesn't mistake this for a regression
introduced by unrelated UI changes (e.g. the Workbench status redesign) and
spend time bisecting it.

**How to apply:** if this specific test fails after other changes, first
confirm it also fails against `HEAD` before treating it as a regression. If
someone eventually wants to fix it for real, look at disambiguating which
"Retry" button is targeted (e.g. scope the query to the actual worker
blocker card container) rather than assuming the underlying retry logic is
broken.
