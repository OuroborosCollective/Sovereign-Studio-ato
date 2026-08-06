# Predictive Inference and Wolfram Validation

**Issue:** #1172  
**Parent:** #1167  
**Status:** IMPLEMENTED_IN_REPOSITORY  
**Revision:** See git log

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│           Adaptive Predictive Side-Channel                       │
│  • Existing neural nodes and synapses                           │
│  • Hebbian Weight Updates                                       │
│  • Anomaly and time series models                               │
│  • ScaNN Incident Candidates (#1171)                            │
│  • Probabilistic Graph Signals                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Risk Evidence Bundle                                │
│  • Channel receipts with revision binding                       │
│  • Aggregate score and conflict detection                        │
│  • Pre-action evidence window                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           Deterministic Validation Lane                          │
│  • Hard Invariant Checks (deterministic)                        │
│  • Revision-bound Model Receipts                                │
│  • Causal Verdict via post-action readback                      │
│  • Wolfram read-only validation (via #1165)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Key Implementation

### Inference Channels

Located in `src/predictive/inference/`:

| File | Purpose |
|------|---------|
| `types.ts` | Core type definitions for receipts, bundles, channels |
| `hardInvariantChannel.ts` | Deterministic bounds checking (CPU, memory, latency, etc.) |
| `riskEvidenceBundle.ts` | Combines channel outputs into unified bundle |
| `modelReceipt.ts` | Creates validated receipts with full revision binding |

### Channel Types (Planned)

1. **hard_invariant** ✅ IMPLEMENTED - Deterministic bounds checking
2. **time_series** - Resource/latency forecasting (planned)
3. **anomaly_detection** - Baseline deviation detection (planned)
4. **predictive_coding** - Top-down prediction + error (existing)
5. **scann_matching** - Similarity-based incident matching (#1171)
6. **dependency_graph** - Graph propagation over runtime edges (planned)

## Model Receipt Contract

Every inference run produces a Model Receipt binding:

```typescript
interface ModelReceipt {
  schemaVersion: 'model-receipt.v1';
  receiptId: string;
  channelType: InferenceChannelType;
  modelClass: string;
  implementationVersion: string;
  
  // Revision binding
  revisionBinding: {
    runtimeRevision: string;
    configRevision: string;
    schemaVersion: string;
    boundAt: number;
  };
  
  // Input binding
  featureSchemaHash: string;
  inputWindowHash: InputWindowHash;
  
  // Model state (versioned)
  modelStateHash: ModelStateHash;
  
  // Score and calibration
  score: number;
  calibrationMetadata?: {
    method: string;
    score: number;
    sampleSize: number;
  };
  
  // Known constraints
  knownLimitations: string[];
  abortReason?: string;
  
  // Optional external validation
  wolframVersion?: string;
  scannManifestHash?: string;
  
  // Integrity
  createdAt: number;
  receiptHash: string;
}
```

## Risk Evidence Bundle

Combines multiple channel receipts:

```typescript
interface RiskEvidenceBundle {
  schemaVersion: 'risk-evidence-bundle.v1';
  bundleId: string;
  traceId: string;
  
  channelReceipts: ModelReceipt[];
  
  preActionEvidenceWindow: {
    startTimestamp: number;
    endTimestamp: number;
    signalCount: number;
  };
  
  aggregateScore: number;
  worstSeverity: InferenceSeverity;
  channelPassRate: number;
  hasConflicts: boolean;
  
  postActionWindow?: {
    startTimestamp: number;
    endTimestamp: number;
    verdict: CausalVerdict;
    verdictReason: string;
  };
  
  createdAt: number;
  bundleHash: string;
}
```

## Causal Verdict

After action execution, post-action readback determines:

| Verdict | Meaning |
|---------|---------|
| EFFECT_VERIFIED | Expected effect confirmed |
| EFFECT_NOT_OBSERVED | Effect not seen |
| EFFECT_CONTRADICTED | Contradictory evidence |
| TARGET_CHANGED_EXTERNALLY | External change detected |
| INSUFFICIENT_POST_WINDOW | Not enough time for verification |
| ROLLBACK_REQUIRED | Compensation needed |

## Safety Rules

1. **No channel alone grants permission or VERIFIED state**
2. **Wolfram UNAVAILABLE blocks only Wolfram, not hard lane**
3. **Missing hashes block that channel (fail-closed)**
4. **Conflicting channels are visible in bundle**
5. **Unknown/unkalibrated scores trigger no action**
6. **Changed revision/config/weights invalidate old predictions**

## Files Changed

```
src/predictive/inference/
├── types.ts                         # Core types
├── types.test.ts                    # Type validation tests
├── hardInvariantChannel.ts          # Deterministic channel
├── hardInvariantChannel.test.ts     # Channel tests
├── riskEvidenceBundle.ts            # Bundle composition
├── modelReceipt.ts                   # Receipt creation
└── index.ts                         # Public exports

src/predictive/index.ts               # Updated exports
```

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Existing predictive surfaces inventory | ✅ IN_REPOSITORY |
| Adaptive/Deterministic separation | ✅ IN_REPOSITORY |
| 3+ independent channels | 🔄 PARTIAL (1 implemented) |
| Risk Bundle with provenance | ✅ IN_REPOSITORY |
| Mutable weights versioned | ✅ IN_REPOSITORY |
| Reproducible outputs | ✅ IN_REPOSITORY |
| Wolfram via #1165 adapter | ⏳ WAITING (adapter not implemented) |
| Shadow Mode measurement | ⏳ PLANNED |
| No prediction alone grants VERIFIED | ✅ IN_REPOSITORY |
| Cross-revision/negative tests | 🔄 PARTIAL (unit tests) |

## Next Steps

1. **Issue #1165** - Implement Wolfram adapter
2. **Issue #1171** - Implement ScaNN integration
3. Time series channel implementation
4. Anomaly detection channel
5. Shadow mode measurement framework
6. Integration with RuntimeIntelligence guards

## Dependencies

- #1168 Contract Foundation
- #1169 Config Provenance  
- #1170 Deterministic Signal Pipeline
- #1171 ScaNN Incident Memory
- #1165 Wolfram Adapter
- #1116 RunEnvelope
- #1118 Context Trust
