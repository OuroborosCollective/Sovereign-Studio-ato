## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).
<<<<<<< bolt-optimize-math-sqrt-4859146072729765810

## 2024-05-11 - [Expensive Math.sqrt in High-Frequency Render Loops]
**Learning:** High-frequency particle system render loops (e.g., in `CanvasEngine`) iterate over hundreds of elements every frame. Calculating Euclidean distances via `Math.sqrt()` inside these nested loops (O(N²) operations) creates a heavy CPU bottleneck and drops frame rates, especially when determining if a connection threshold is met for the vast majority of non-connecting particles.
**Action:** Instead of `Math.sqrt(dx*dx + dy*dy) < threshold`, use squared distances for evaluation `(dx*dx + dy*dy) < threshold * threshold`. Only invoke `Math.sqrt()` if the check passes and the actual linear distance is required for precise calculations like opacity scaling.
=======
## 2024-05-10 - [Math.sqrt Performance in Render Loops]
**Learning:** In high-frequency render loops like canvas particle systems (`HomePage.tsx`), calculating `Math.sqrt` on every frame for distance checks acts as a significant performance bottleneck.
**Action:** When calculating distances just for comparison (e.g. `dist < threshold`), always compute and compare the squared distance (`distSq < threshold * threshold`). Only invoke `Math.sqrt` conditionally if the exact distance value is strictly required inside the threshold block.
>>>>>>> main
## 2024-05-12 - [Array Map in Canvas Redux Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects using a temporary  array inside . This temporary allocation created unnecessary garbage collection overhead when adding batches of objects.
**Action:** When creating a  from an array just for tracking IDs to prevent duplicates, avoid . Instead, initialize an empty  and populate it via a  loop using . This keeps memory allocation strictly to the resulting Set and the iterators, preventing the creation of short-lived arrays and avoiding GC pauses.

## 2024-05-12 - [Array Map in Canvas Redux Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects using a temporary `.map()` array inside `addVectors`. This temporary allocation created unnecessary garbage collection overhead when adding batches of objects.
**Action:** When creating a `Set` from an array just for tracking IDs to prevent duplicates, avoid `.map()`. Instead, initialize an empty `Set` and populate it via a `for...of` loop using `.add(id)`. This keeps memory allocation strictly to the resulting Set and the iterators, preventing the creation of short-lived arrays and avoiding GC pauses.
