## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).

## 2024-05-11 - [Expensive Math.sqrt in High-Frequency Render Loops]
**Learning:** High-frequency particle system render loops (e.g., in `CanvasEngine`) iterate over hundreds of elements every frame. Calculating Euclidean distances via `Math.sqrt()` inside these nested loops (O(N²) operations) creates a heavy CPU bottleneck and drops frame rates, especially when determining if a connection threshold is met for the vast majority of non-connecting particles.
**Action:** Instead of `Math.sqrt(dx*dx + dy*dy) < threshold`, use squared distances for evaluation `(dx*dx + dy*dy) < threshold * threshold`. Only invoke `Math.sqrt()` if the check passes and the actual linear distance is required for precise calculations like opacity scaling.

## 2024-05-13 - [Avoid Intermediate Arrays when building Sets]
**Learning:** In `canvasSlice.ts`, when constructing a `Set` from an array of objects to get unique IDs, the code previously did `new Set(state.objects.map(obj => obj.id))`. This created a large temporary intermediate array just to build the set, introducing memory overhead and unnecessary GC pauses during heavy state reconciliation.
**Action:** Replace `Array.map` passed directly into `Set` constructor with a simple `for` loop that iterates the array and explicitly calls `.add` on the `Set`, skipping the intermediate array allocation altogether.
