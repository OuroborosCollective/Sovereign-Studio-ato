## 2024-03-24 - Array Iteration Optimization
**Learning:** Chained `.filter().length` calls on the same array cause multiple unnecessary array allocations and repeated iterations over the entire dataset. This is a common React component performance anti-pattern.
**Action:** Replace multiple `.filter(x => x.prop === val).length` calls with a single `for` loop that accumulates counts in a single pass. This dramatically reduces garbage collection overhead and execution time, especially inside `useMemo` hooks running on render.

## 2024-03-24 - Array Iteration Optimization
**Learning:** Chained `.filter().length` calls on the same array cause multiple unnecessary array allocations and repeated iterations over the entire dataset. This is a common React component performance anti-pattern.
**Action:** Replace multiple `.filter(x => x.prop === val).length` calls with a single `for` loop that accumulates counts in a single pass. This dramatically reduces garbage collection overhead and execution time, especially inside `useMemo` hooks running on render.
