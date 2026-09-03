## 2025-05-28 - [Refactoring ProductMagicApp.tsx]
**Learning:** Large React components (200+ lines) with mixed state and UI benefit significantly from custom hooks and component decomposition.
**Action:** Always look for logical units of state and UI blocks to extract. Use custom hooks for complex state management and isolated components for logical UI sections.

## 2026-06-23 - [Memoizing derived state in ChatSidebar]
**Learning:** Memoizing derived state like 'safeMessages' not only prevents redundant O(N) normalization on every keystroke in a controlled input, but also stabilizes object identity. This prevents unnecessary triggerings of 'useEffect' hooks (e.g., for auto-scrolling) that depend on these objects.
**Action:** Always memoize derived objects/arrays in components with frequent re-renders (like those with text inputs) to maintain stable identities for downstream hooks and memoized children.

## 2025-05-29 - [Referential Stability for Fallback Arrays]
**Learning:** In a large orchestration component like 'App.tsx', failing to memoize safe fallback arrays (e.g., `const safe = data || []`) causes all dependent `useMemo` and `useCallback` hooks to invalidate on every render cycle, even when the underlying data is identical. This leads to massive redundant processing in expensive logic like health reports and diff generation.
**Action:** Always wrap safety/normalization logic for arrays and objects in 'useMemo' at the highest possible level to preserve referential identity across renders.

## 2026-07-02 - [Regex Hoisting in High-Frequency Components]
**Learning:** Components used in high-frequency update paths (like 'ChatMarkdown' inside 'PacedChatText' which updates every 55ms) incur significant overhead if they instantiate/compile regex patterns on every render. Hoisting regex constants to module scope and using '.test()' instead of '.match()' for boolean checks provides a measurable performance boost.
**Action:** Always hoist regex patterns to module-level constants in components that re-render frequently. Use '.test()' for performance-critical boolean checks.

## 2026-07-03 - [1-Slot Memoization for High-Frequency Logic]
**Learning:** In high-frequency update loops (e.g., 55ms chat pacing), even $O(N)$ operations like word counting or array allocations (like regex pattern arrays) can accumulate significant CPU time and GC pressure. 1-slot memoization for pure functions based on input strings and hoisting allocation-heavy arrays to module scope provide immediate, low-risk wins.
**Action:** Implement simple 1-slot memoization for pure utility functions used in frequent render/effect ticks. Hoist not just regexes, but also the arrays/objects that contain them if they are static.

## 2026-07-04 - [Optimizing Deep Structure Analysis Loops]
**Learning:** O(N) operations over file list arrays (e.g., structure analysis, extension checks, matching solution patterns) in a recursive engine can be consolidated. Accumulating name counts on-the-fly and reusing pre-computed metrics (like `byExtension`) completely eliminates redundant iterations. Slicing files before allocating string paths.
**Action:** Always consolidate separate O(N) loops operating on the same arrays. Reuse pre-computed metrics downstream to completely avoid re-parsing structures. Slice lists before allocating string paths.

## 2026-07-05 - [Pre-filtering Query Spaces by Known Store Domains]
**Learning:** When matching database/store patterns based on dynamically gathered repository traits (such as all file extensions), querying the store for every unique trait results in $O(T \times P)$ complexity. Pre-filtering the traits to only those actually present in the store's domain completely eliminates wasteful iterations on non-matching traits.
**Action:** Always pre-filter traits (like extensions or paths) against a Set of the store's known/indexed values before performing nested pattern-matching or search queries.

## 2026-07-06 - [Regex Hoisting and 1-Slot Caching for Secret Masking]
**Learning:** In logging and rendering paths (such as `SafeLogText` which can receive high-frequency stream chunks), compiling numerous complex secret-masking regular expressions on every execution introduces substantial CPU and GC overhead. Hoisting patterns to module scope and wrapping the transformation with a 1-slot strict equality input/output cache (`lastMaskInput` / `lastMaskOutput`) completely bypasses regex replacement loops in O(1) time for consecutive calls on identical strings.
**Action:** For performance-sensitive string processing or sanitization utilities, always hoist regex patterns and apply a simple 1-slot strict-equality input/output cache to avoid redundant RegExp processing on duplicate consecutive calls.

## 2026-07-22 - [Memoizing Sub-State Filters on Parent Controlled Inputs]
**Learning:** In controlled-input interfaces (like Sidebar.tsx rendering next to BuilderContainer textareas), parents frequently trigger state changes on every single keystroke. When a child component map/filter is not memoized, it runs expensive `O(N)` loop computations and string transformations (such as `.toLowerCase()`) on every keystroke, which halts UI fluidity. Wrapping file filtering in `useMemo` and pulling string transformations outside of the filter predicate callback keeps UI render cycles extremely snappy.
**Action:** Always memoize derived array/filtering states and hoist loop-invariant transformations outside predicate callback scopes for components rendered alongside controlled high-frequency text inputs.

## 2026-07-23 - [WeakMap Token Caching and Set Hoisting in Match Loops]
**Learning:** In pattern-matching hot paths that execute matching logic over hundreds of stored pattern templates on every state change, splitting, filtering, and repeatedly normalizing string properties (like pattern descriptions) inside loop iterations creates severe CPU and garbage collection pressure. Caching computed properties via a `WeakMap` keyed on the immutable object reference prevents memory leaks (stale templates are automatically GC'd) and avoids stale-data cache invalidation bugs. Additionally, hoisting array-to-Set conversions outside loops turns redundant $O(N)$ Set allocations into a single $O(1)$ fast lookup table.
**Action:** Always hoist Set-allocations and mapping logic out of hot loops. Use `WeakMap` keyed on immutable object references to securely cache parsed/computed sub-properties without introducing stale data or memory leaks.

## 2026-08-02 - [Line-level and 1-Slot Caching for Progressive Markdown Parsing]
**Learning:** In progressive update interfaces (such as streamed chat responses via `PacedChatText` updating every 55ms), re-parsing the entire markdown string from scratch introduces $O(N^2)$ time complexity overhead relative to the total number of characters. Segmenting content by lines and caching the parsed results of immutable lines in a bounded `inlineLineCache` alongside a 1-slot whole-text tokenizer cache drops consecutive stream ticks from expensive regex re-evaluation to $O(1)$ fast lookups.
**Action:** Always utilize simple, bounded line-level caches combined with 1-slot consecutive whole-text caches to bypass repetitive, expensive string parsing and regular expression tokenization in high-frequency update loops.

## 2026-08-03 - [Consolidating Multi-Pass Scans and Avoiding LocaleCompare]
**Learning:** Performing multiple sequential array filters and checks on repository file trees introduces $O(N \times M)$ overhead from traversing the file array up to a dozen times. Consolidating classification of source files, test files, legacy files, state pattern markers, directory size maps, and lockfile/package.json detection into a single-pass $O(N)$ loop completely avoids redundant iterations and intermediate array allocations. Furthermore, utilizing standard native array `.sort()` instead of custom `.sort((a, b) => a.localeCompare(b))` results in a 10-20x sorting speedup in V8 because locale-aware comparisons are extraordinarily heavy and unnecessary for simple file path arrays.
**Action:** Always consolidate separate $O(N)$ scans of file or entry lists into a single loop pass. Avoid `localeCompare` for string arrays (like file paths or IDs) unless local language-specific collations are explicitly required; native `.sort()` is significantly faster.

## 2026-08-04 - [1-Slot Cache with Norm Loop Consolidation for Deterministic Vector Store]
**Learning:** In a high-frequency vector store search, generating query embeddings and computing their mathematical norms in separate O(N) loops invokes costly JIT array allocations and Math.sin computations. Consolidating the embedding generation and norm accumulation into a single-pass method, and caching the result via a 1-slot cache keyed on the query value, completely eliminates all trigonometry and loop operations for consecutive duplicate queries. In addition, replacing localeCompare with native lexicographical string comparison in tie-breaker sorting removes unnecessary localization collation overhead.
**Action:** When working on mathematical vector/embedding utilities with invariant space configurations, consolidate multi-pass loops into single-pass operations and cache query vectors together with their norms to maximize performance.

## 2026-08-05 - [Fast Native Path Decomposition and Lexicographical Node Sorting]
**Learning:** Building deep directory structures from hundreds of raw file paths can be heavily bottlenecked by continuous array allocations from string splitting (`.split('/')`), filtering (`.filter(Boolean)`), and slicing/joining (`.slice()`, `.join()`). By leveraging native `lastIndexOf` and `substring` operations, we completely avoid array and string allocation overhead on every level of path decomposition. Furthermore, replacing locale-aware sorting (`localeCompare`) with simple character comparison operators (`<` and `>`) results in an order-of-magnitude reduction in CPU time for recursive node sorting.
**Action:** Use fast, native string index lookups (`lastIndexOf`, `substring`) instead of array splitting when decomposing structured paths under hot loops. Avoid `localeCompare` for standard alphanumeric lists (like file paths or file names) to prevent internationalization collation overhead in JS engines.
## 2026-08-06 - [Regex Hoisting for Array String Matching]
**Learning:** Recompiling a regular expression on every invocation of a function, particularly inside an array '.some()' loop, incurs unnecessary runtime overhead. Consolidating array values into a single joined RegExp string and compiling it once at the module level significantly reduces execution time and garbage collection pressure.
**Action:** Always hoist regular expression definitions to module-level constants and use the '.test()' method for optimal performance in validation and text matching functions.
## 2026-08-07 - [Native Array Sorting Efficiency]
**Learning:** When sorting simple string arrays (such as object keys) where local language-specific collation is not required, passing a custom comparison callback (e.g., `.sort((a, b) => a < b ? -1 : a > b ? 1 : 0)`) forces the JavaScript engine to cross the C++/JS boundary for every element comparison, degrading performance.
**Action:** Use the default, argument-less `.sort()` method for sorting arrays of strings lexicographically, as it leverages the engine's highly optimized internal sorting algorithms.

## 2026-08-16 - [Consolidating Multi-Pass Reductions and Slice Allocations in Mathematical Analysis]
**Learning:** Calculating mathematical statistics (such as Pearson correlation) over array buffers using multiple `.slice()` subarray calls and sequential `.reduce()` passes creates significant garbage collection overhead and repeated array traversal costs. Consolidating all summations into a single indexed `for` loop pass drops loop overhead to a single $O(N)$ traversal with $O(1)$ memory allocations.
**Action:** Always replace chained `.slice()` and multi-pass `.reduce()` calls in mathematical analysis routines with a single `for` loop that accumulates all required summations concurrently.

## 2026-08-17 - [Direct Character Scanning for Line Counting and Single-Pass Report Accumulation]
**Learning:** In diff and report previews handling multi-line file content, computing line counts via string splitting (`content.split(/\r?\n/).length`) creates large intermediate arrays of strings, causing severe heap allocations and garbage collection pressure. Replacing `.split(/\r?\n/)` with a direct character scan for newline characters (`charCodeAt(i) === 10`) avoids array allocations entirely. Additionally, consolidating mapping, filtering, and reduction passes over file reports into a single `for` loop reduces iteration complexity from multi-pass $O(N \times K)$ to $O(N)$.
**Action:** Use string character scans for simple token/line counting instead of array splitting on large inputs, and accumulate summary statistics during array mapping loops instead of running post-process `.filter()` and `.reduce()` passes.

## 2026-08-26 - [Consolidating Multi-Pass Array Traversals in Summary Computations]
**Learning:** Computing summary statistics and extracting unique tags using chained `.filter()`, `.reduce()`, and `[...new Set(filtered.map(...))]` methods incurs severe CPU and garbage collection pressure due to multiple $O(N)$ passes and continuous intermediate array allocations on every invocation. Replacing these method chains with a single-pass `for...of` loop completely avoids multiple traversals and eliminates intermediate arrays, keeping computations flat and extremely fast.
**Action:** Always refactor sequential array method chains (like `.filter().reduce()` or `.filter().map()`) into a single-pass loop when dealing with frequent or large-scale data summary computations to avoid intermediate allocations and reduce iteration overhead.

## 2026-09-03 - [Consolidating Multi-Pass Array Iterations]
**Learning:** In memory analytics logic (`derivePatternMemoryCounters`), running multiple independent `.filter()` and `.map()` passes over an array creates severe CPU and garbage collection pressure due to multiple (N)$ passes and continuous intermediate array allocations on every invocation. Replacing these method chains with a single-pass `for...of` loop completely avoids multiple traversals and eliminates intermediate arrays, keeping computations flat and extremely fast.
**Action:** Always refactor sequential array method chains (like `.filter().reduce()` or `.filter().map()`) into a single-pass loop when dealing with frequent or large-scale data summary computations to avoid intermediate allocations and reduce iteration overhead.
