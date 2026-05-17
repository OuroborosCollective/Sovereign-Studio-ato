## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).
## 2024-05-10 - [Math.sqrt Performance in Render Loops]
**Learning:** In high-frequency render loops like canvas particle systems (`HomePage.tsx`), calculating `Math.sqrt` on every frame for distance checks acts as a significant performance bottleneck.
**Action:** When calculating distances just for comparison (e.g. `dist < threshold`), always compute and compare the squared distance (`distSq < threshold * threshold`). Only invoke `Math.sqrt` conditionally if the exact distance value is strictly required inside the threshold block.
>>>>>> main
## 2024-05-24 - [Avoid intermediate array allocation for Set creation]
**Learning:** Using `new Set(array.map(...))` creates an intermediate array that needs to be garbage collected, adding overhead, especially for large arrays in Redux state or high-frequency updates.
**Action:** When constructing a `Set` from an array of objects to get unique IDs, use a `for` loop and explicitly call `.add()` on the `Set`.
