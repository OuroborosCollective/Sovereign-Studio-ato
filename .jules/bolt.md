## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).
## 2024-05-10 - [Math.sqrt Performance in Render Loops]
**Learning:** In high-frequency render loops like canvas particle systems (`HomePage.tsx`), calculating `Math.sqrt` on every frame for distance checks acts as a significant performance bottleneck.
**Action:** When calculating distances just for comparison (e.g. `dist < threshold`), always compute and compare the squared distance (`distSq < threshold * threshold`). Only invoke `Math.sqrt` conditionally if the exact distance value is strictly required inside the threshold block.
>>>>>> main
## 2024-05-16 - [Set Construction Overhead in Array.map]
**Learning:** Constructing a `Set` directly from `Array.map` (e.g. `new Set(array.map(x => x.id))`) in a hot path or frequently called reducer allocates an intermediate array, which causes unnecessary memory churn and garbage collection overhead.
**Action:** Use a `for` loop to explicitly call `.add()` on the `Set` when extracting unique values from large arrays to reduce GC pressure and avoid intermediate array allocations.
