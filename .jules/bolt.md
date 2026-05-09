## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).

## 2024-05-10 - [O(N²) FabricJS canvas.getObjects().indexOf() inside loop]
**Learning:** Using `canvas.getObjects().indexOf(obj)` inside a loop to check an object's current z-index/position creates an O(N²) bottleneck because `getObjects()` might slice/copy the array in some versions, and `indexOf` iterates O(N) over it.
**Action:** Replace `canvas.getObjects().indexOf(existingObj) !== index` with `canvas.item(index) !== existingObj` to perform an O(1) check and significantly reduce the time complexity inside canvas reconciliation loops.
