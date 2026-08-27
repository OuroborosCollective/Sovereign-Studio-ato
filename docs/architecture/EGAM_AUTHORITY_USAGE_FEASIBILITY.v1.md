# EGAM Authority Usage Feasibility Study

**Issue:** #1602  
**Status:** GO/NO-GO DECISION  
**Baseline Revision:** `a93102180dbea4051a46fa8eca58a1e7af60bc6`

---

## Executive Summary

**DECISION: NO SAFE RIGHTSIZING INPUT AVAILABLE**

This feasibility study concludes that the Evidence-Grounded Authority Minimizer (EGAM) cannot proceed to Phase 1 (shrink-only rightsizing) because:

1. **#1116 (RunEnvelope + Capability Manifest)** - NOT IMPLEMENTED - no canonical authority baseline exists
2. **#1118 (Context Trust)** - NOT IMPLEMENTED - no trust-based capability reduction receipts exist
3. **#1119 (CAS/Versioned Mutation Control)** - NOT IMPLEMENTED - no atomic mutation control

The current receipt infrastructure tracks tool invocations but lacks:
- Canonical authority atom definitions
- Capability manifest bindings
- Trust-based reduction evidence
- Deterministic baseline resolution

---

## Current Authority Tracking State

### What EXISTS (Agent Run Receipts)

The existing `agent_run_receipts.py` tracks:

```python
# From agent_run_receipts.py - line 294
tool_name: str,
```

**Finding:** Tool names are recorded in receipts, but:
- No canonical authority atom definition exists
- No mapping from tool_name to authority atom class
- No capability manifest hash binding
- No baseline authority contract

### What DOES NOT EXIST

| Requirement | Status | Evidence |
|------------|--------|----------|
| Authority Atom Definition | ❌ MISSING | No `AuthorityAtom` dataclass |
| Capability Manifest | ❌ MISSING | No `#1116` implementation |
| Context Trust Receipt | ❌ MISSING | No `#1118` implementation |
| CAS Mutation Control | ❌ MISSING | No `#1119` implementation |
| Tool→Atom Mapping | ❌ MISSING | No registry of authority atoms |
| Baseline Authority Contract | ❌ MISSING | No deterministic baseline |

---

## Dependency Analysis

### Issue #1116 (RunEnvelope + Capability Manifest) - BLOCKING

```bash
$ gh issue view 1116 --json state,url
{
  "state": "OPEN",
  "title": "Implement revision-bound harness-neutral execution envelopes and capability manifests"
}
```

**Impact:** Without RunEnvelope, there is no canonical way to:
- Define what authority atoms are granted at run start
- Bind capability manifest to specific revision
- Compare observed usage against granted baseline

### Issue #1118 (Context Trust) - BLOCKING

```bash
$ gh issue view 1118 --json state,url
{
  "state": "OPEN", 
  "title": "Implement provenance-bound context trust and deterministic tool-chain guardrails"
}
```

**Impact:** Without Context Trust, there is no:
- Trust-based capability reduction mechanism
- Deterministic trust state receipts
- Dynamic authority adjustment evidence

### Issue #1119 (CAS Mutation Control) - BLOCKING

```bash
$ gh issue view 1119 --json state,url
{
  "state": "OPEN",
  "title": "Implement atomic versioned mutation control with CAS, resource locks, and config receipts"
}
```

**Impact:** Without CAS:
- No atomic mutation control for authority changes
- No versioned policy control
- No config receipt for audit trail

---

## Existing Infrastructure Analysis

### Fleet Attempts (Partially Relevant)

```python
# From fleet_attempts.py - line 48
@dataclass(frozen=True, slots=True)
class FleetWorkerAttempt:
    capability_manifest_hash: str
```

**Finding:** `capability_manifest_hash` field exists but:
- No implementation of `#1116` capability manifest
- Hash is computed but not validated against canonical contract
- No authority atom decomposition

### Cognitive Repository Tools

```python
# From cognitive_repository_tools.py
# Tool calls are tracked but not mapped to authority atoms
tool_call_id = start_agent_tool_call(...)
```

**Finding:**
- Tool invocations create receipts
- No canonical authority atom mapping
- No baseline authority comparison

---

## Go/No-Go Evidence

### GO Criteria (from Issue #1602)

- [ ] Authority Baseline deterministically resolvable without heuristics
- [ ] Usage classes actually observable
- [ ] At least one non-trivial `UNUSED_IN_VERIFIED_CORPUS` case exists
- [ ] No credential/scope interpretation from hashes needed
- [ ] #1116/#1118/#1119 ownership usable without parallel architecture

### Actual State

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Authority Baseline resolvable | ❌ NO | No `#1116` RunEnvelope |
| Usage classes observable | ⚠️ PARTIAL | Tool names exist, no atom mapping |
| Non-trivial UNUSED case | ❌ NO | Cannot decompose without manifest |
| No hash interpretation | ❌ N/A | No baseline to compare |
| Ownership usable | ❌ NO | Implementations missing |

---

## Raw Metrics

```
baseline authority atoms: UNDEFINED
observable atoms: UNDEFINED (no atom registry)
observed used atoms: UNDEFINED (no tool→atom mapping)
unused-in-corpus atoms: UNDEFINED
non-decomposable atoms: UNDEFINED
incomplete atoms: UNDEFINED
verified runs included: 0 (no baseline to bind)
runs excluded + reason: N/A
projection latency: N/A
receipt reads: 0 (no authority tracking)
```

## Test Verification Results

The following tests were executed to verify the current state:

```
$ uvx pytest backend/tests/test_authority_usage_truth_boundary.py -v
========================= 8 passed in 0.14s =========================

Test Results:
- test_no_authority_atom_class_exists: PASSED
- test_no_capability_manifest_exists: PASSED
- test_receipts_track_tool_names_but_not_authority_atoms: PASSED
- test_no_trust_reduction_receipts: PASSED
- test_no_cas_mutation_control: PASSED
- test_fleet_attempt_has_manifest_hash_field: PASSED
- test_prerequisite_issues_not_implemented: PASSED
- test_no_unsafe_inference_from_tool_names: PASSED
```

**Key Findings from Tests:**
1. No AuthorityAtom class exists in agent_runtime
2. No CapabilityManifest class exists
3. No ToolReceipt class - tool tracking doesn't exist in receipts
4. No trust reduction receipts exist
5. No CAS mutation control exists
6. FleetWorkerAttempt has capability_manifest_hash but no full manifest

---

## Conclusion

**NO_SAFE_RIGHTSIZING_INPUT_AVAILABLE**

### Reason

The EGAM feasibility study cannot proceed because:

1. **No Authority Baseline** - Issue #1116 (RunEnvelope + Capability Manifest) is not implemented. Without a canonical definition of granted authority atoms, any "unused" claim would be based on guesswork, not deterministic evidence.

2. **No Tool-to-Atom Mapping** - While tool names are recorded in receipts, there is no canonical mapping from tool invocations to authority atom classes (TOOL, EGRESS_TARGET, EFFECT_CLASS, MUTATION_FAMILY, ENVIRONMENT).

3. **No Trust Reduction Evidence** - Issue #1118 is not implemented. There is no mechanism to track trust-based capability reductions that could inform shrink decisions.

4. **Risk of False Causality** - As stated in the issue: "nicht beobachtet" ≠ "nicht benötigt". Without proper baseline and tracking, we cannot distinguish between:
   - Authority that was granted but not used
   - Authority that was never granted
   - Authority used in a way not captured by receipts

### Recommendation

1. **Close EGAM Phase 0** with NO-GO decision
2. **Re-prioritize #1116, #1118, #1119** as prerequisites
3. **Re-assess EGAM feasibility** after RunEnvelope implementation
4. **Do not attempt** parallel authority tracking - would create duplicate ownership

---

## Required for Future Re-evaluation

After #1116/#1118/#1119 implementation:

1. Authority atom registry with explicit definitions
2. Tool→Atom mapping in capability manifest
3. Baseline authority contract in RunEnvelope
4. Trust state receipts from #1118
5. CAS-bound policy changes from #1119

---

*Generated: 2026-08-27*  
*Revision: a93102180dbea4051a46fa8eca58a1e7af60bc6*  
*Status: FINAL - NO-GO*
