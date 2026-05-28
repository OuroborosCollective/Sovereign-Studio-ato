## 2025-05-14 - [Fixed CanvasEngine ReferenceError and Added useGemini Tests]
**Learning:** Found a `ReferenceError: fabricObjectsMapRef is not defined` in `CanvasEngine.tsx` that was causing existing tests to fail. The ref was named `existingFabricObjectsMapRef` but used as `fabricObjectsMapRef`. Also implemented comprehensive hook testing using `@testing-library/react`.
**Action:** Always verify existing test suite health before and after changes. Use `sed` for safe bulk renaming of mismatched identifiers discovered during testing.
