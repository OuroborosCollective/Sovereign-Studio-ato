# Palette's Journal - Sovereign Studio UX & Accessibility

## 2025-05-14 - Selector Ambiguity and Localized UI
**Learning:** Common localized UI labels like "Vorschläge" or priority badges like "WICHTIG" often appear in both header areas and content sections, leading to `MultipleMatchesError` in Vitest/Testing Library.
**Action:** Prefer `getByLabelText` for interactive elements and use specific containers or `getAllByText` with length checks for descriptive labels to improve test robustness.

## 2025-05-14 - Asynchronous State Machine Testing
**Learning:** Sequential "sleep" calls in complex state machines (e.g., in `useProductMagic.ts`) can exceed default Vitest timeouts and make certain transient states (like "failed" before "fixing") difficult to capture in tests.
**Action:** Increase test timeouts to 15s-20s for workflow tests and consider adding small artificial delays in the code or using `vi.useFakeTimers()` to ensure state stability during assertions.

## 2025-05-14 - Localized Chat Empty State
**Learning:** Starting a chat interface with a null or empty state feels "cold". Initializing the state with a localized welcome message improves the immediate UX and provides a clear starting point for the user.
**Action:** Always initialize chat message arrays with a system or assistant welcome message matching the app's primary locale.
