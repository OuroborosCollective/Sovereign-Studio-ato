## 2025-05-14 - [Fixed CanvasEngine ReferenceError and Added useGemini Tests]
**Learning:** Found a `ReferenceError: fabricObjectsMapRef is not defined` in `CanvasEngine.tsx` that was causing existing tests to fail. The ref was named `existingFabricObjectsMapRef` but used as `fabricObjectsMapRef`. Also implemented comprehensive hook testing using `@testing-library/react`.
**Action:** Always verify existing test suite health before and after changes. Use `sed` for safe bulk renaming of mismatched identifiers discovered during testing.

## 2025-05-14 - [Fixed CI Java Distribution Error]
**Learning:** The GitHub CI job "Android Build Verification" failed with a 520 error during the `actions/setup-java@v4` step when using the `zulu` distribution. Switching to `temurin`, which was already successfully used in `android-release.yml`, resolved the issue.
**Action:** When a CI step fails inexplicably (like error 520 on a standard action), compare the configuration with other successful workflows in the same repository. Distribution choice can impact availability or reliability in certain GitHub runner regions.
## 2025-05-31 - [Single-Pass useMemo React Optimization]
**Learning:** React components sometimes perform redundant array allocations via chaining multiple methods (e.g. `.filter().slice().map()`) and repeating similar logic inline (e.g. `.filter().length`) inside the render body. This is a common React performance anti-pattern.
**Action:** When finding multiple chained array manipulations or redundant array counts during render, extract them to a `useMemo` block that executes a single O(N) loop to compute derived state variables simultaneously without temporary array allocations.
