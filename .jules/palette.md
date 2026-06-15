## 2026-06-15 - [Clear button for text inputs]
**Learning:** Adding a clear button to text inputs significantly improves UX for long inputs by allowing users to reset state with one click. It must be accessible (ARIA label) and should not overlap with the text.
**Action:** Use a relative container around the input and an absolute positioned button at the end (right-2) with the 'CircleX' icon and 'aria-label="Eingabe loeschen"'.
