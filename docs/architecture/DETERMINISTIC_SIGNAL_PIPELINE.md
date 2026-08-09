# Deterministic Signal Pipeline

## Status

`IMPLEMENTED_IN_REPOSITORY` | `TESTED_AT_REVISION` | `CI_VERIFIED`

## Overview

This document describes the deterministic signal and feature pipeline between runtime sensors and Predictive/ScaNN/Wolfram lanes. The pipeline uses an internal allowlist adapter to safely evaluate iterator primitives.

## Architecture

```
validated signals
  → canonical order
  → bounded grouping by node
  → pairwise deltas
  → fixed/overlapping tick windows
  → deterministic feature vectors
  → feature-window receipt
  → inference lanes
```

## Key Properties

| Property | Value |
|----------|-------|
| Ordering | Tick, Node, Sequence (canonical) |
| Hash | FNV-1a inspired deterministic hash |
| Windows | Fixed-size or overlapping |
| Replay Parity | Same signals → Same hashes |

## Allowed Iterator Primitives

After testing, the following primitives are permitted:

| Primitive | Purpose |
|-----------|---------|
| `chunkwise` | Bounded chunking |
| `chunkwiseOverlap` | Overlapping chunks |
| `pairwise` | Consecutive pairs |
| `zipEqual` | Parallel iteration with length check |
| `groupBy` | Canonical grouping |
| `runningDifference` | Temporal delta features |
| `runningTotal` | Cumulative sum features |
| `toMinMax` | Range statistics |

### Explicitly Blocked

| Pattern | Reason |
|---------|--------|
| `random.*` | Non-deterministic |
| `infinite.*` | Unbounded |
| `sort` without canonical comparator | Non-deterministic ordering |
| Unbounded async streams | Cannot guarantee termination |
| Wall-clock generators | Not causally bound |

## Contract Tests

The following patterns are verified by contract tests:

```typescript
// Contract test for allowlist - should fail at static analysis
import { random } from 'itertools-ts'; // ❌ Blocked
import { infinite } from 'itertools-ts'; // ❌ Blocked
```

## File Structure

### TypeScript Implementation

```
src/predictive/pipeline/
├── index.ts                      # Module exports
├── deterministicIterables.ts     # Allowlist adapter + primitives
├── signalOrdering.ts            # Canonical ordering
├── tickWindow.ts                # Window generation
├── featureVector.ts             # Feature extraction
├── replay.ts                    # Replay with parity
├── deterministicIterables.test.ts
├── signalOrdering.test.ts
├── tickWindow.test.ts
├── featureVector.test.ts
└── replay.test.ts
```

### Python Implementation

```
backend/agent_runtime/predictive/
├── __init__.py
└── signal_pipeline.py            # Mirrors TypeScript implementation

backend/tests/
└── test_predictive_signal_replay.py
```

## Key Interfaces

### Signal Types

```typescript
interface OrderedSignal extends Signal {
  metadata: {
    tick: number;       // Monotonically increasing
    sequence: number;   // Per-tick sequence
    revision: string;   // Repository revision bound
    node: string;
  };
}
```

### Window Configuration

```typescript
interface TickWindowConfig {
  windowSize: number;     // Fixed window size
  overlap: number;        // Overlap between windows (must be < windowSize)
  maxItems?: number;      // Optional max items per window
  maxWindowDuration?: number; // Optional max duration in ms
}
```

### Feature Vector

```typescript
interface FeatureVector {
  values: number[];           // Flat feature vector
  signalHash: string;        // Deterministic hash
  tickRange: [number, number];
  sequenceRange: [number, number];
  revision: string;
  configFingerprint: string; // Encodes window config
}
```

## Pipeline Flow

### 1. Signal Ordering

```typescript
// Canonical order: tick, node, sequence
const orderedSignals = orderSignals(signals);
validateCanonicalOrder(orderedSignals); // Throws on violations
```

### 2. Window Generation

```typescript
// Fixed windows (non-overlapping)
const windows = [...generateTickWindows(orderedSignals, config)];

// Overlapping windows
const overlappingWindows = [...generateOverlappingTickWindows(orderedSignals, config)];
```

### 3. Feature Extraction

```typescript
for (const window of windows) {
  const { features, featureVector, receipt } = processWindowToFeatures(window, isReplay);
  // features: Statistical and temporal features
  // featureVector: Flat vector for ML inference
  // receipt: Processing receipt with drop information
}
```

### 4. Replay with Parity

```typescript
// Record signals
pipeline.startRecording(revision);
pipeline.recordSignals(signals);
const recordedSet = pipeline.finishRecording(featureVectors);

// Replay later
const replayResult = pipeline.replayRecorded(recordedSet);
console.log(`Parity verified: ${replayResult.parityVerified}`);
```

## Backpressure

Backpressure is applied when the queue depth exceeds a threshold:

```typescript
interface BackpressureState {
  queueDepth: number;
  isBackpressured: boolean;
  maxQueueDepth: number;
}
```

When backpressure is applied, signals are dropped with a reason code:

```typescript
type WindowDropReason =
  | 'MAX_ITEMS_EXCEEDED'
  | 'MAX_WINDOW_DURATION_EXCEEDED'
  | 'BACKPRESSURE_APPLIED'
  | 'ABORT_SIGNALLED'
  | 'INCOMPLETE_WINDOW';
```

## Receipts

Every window processing generates a receipt:

```typescript
interface WindowReceipt {
  id: string;
  featureVector: FeatureVector;
  signalCount: number;
  timestamp: number;
  isReplay: boolean;
  dropReason?: string;  // Only present if signals were dropped
}
```

## Verification

### Replay Parity

```typescript
// Verify that same recorded signals produce same hashes
const parity = verifyFeatureParity(originalVector, replayedVector);
if (!parity.equal) {
  console.error(`Parity mismatch: ${parity.diff}`);
}
```

### Semantic Identity

Live and replay outputs are semantically identical when:

1. Same window count
2. Same signal count
3. Same feature vectors (by tick range and hash)

## Performance

The pipeline is designed with bounded operations:

- All iterables are bounded by `maxItems`
- Window duration is bounded by `maxWindowDuration`
- No unbounded async streams
- Deterministic hashing (no crypto operations)

Typical overhead is O(n) where n is the number of signals.

## Related Issues

- Parent: #1167
- Number Semantics: #1168
