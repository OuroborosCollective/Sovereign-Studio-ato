## 2024-05-07 - [O(N²) Array Lookups in Canvas Render Loop]
**Learning:** The previous implementation synchronized an array of Redux state objects with the active Fabric.js canvas objects inside an effect hook using nested array `.find()` calls. This resulted in O(N²) time complexity which acts as a heavy performance bottleneck and can drop frames for large canvas object counts.
**Action:** When reconciling external state with internal canvas state, always build O(1) Hash Maps (`Map` for existing elements, `Set` for IDs to remove) before looping, bringing the reconciliation complexity down to O(N).

## 2024-05-18 - [Optimized Distance Calculation in Render Loops]
**Learning:** In high-frequency render loops or particle systems (like the background effect in HomePage), calculating squared distances (`distSq < threshold * threshold`) rather than invoking `Math.sqrt()` to evaluate ranges bypasses expensive square root operations and improves frame rates significantly. We should only calculate the exact square root inside the condition if it's strictly needed (e.g. for calculating dynamic opacity).
**Action:** Always check distance comparisons in `requestAnimationFrame` loops and replace `Math.sqrt` with squared distance comparisons where possible.
