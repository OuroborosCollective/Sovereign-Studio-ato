# Solution Pattern Memory

Solution Pattern Memory learns reusable repair patterns from reported and completed fixes.

It is separate from Session Memory and separate from the generic Learning Memory.

Its job is to build repair intelligence:

```txt
problem before
+ file/context structure
+ proposed or proven fix after
= reusable problem -> solution pattern
```

## Goal

When a later session sees a similar structural problem, the memory can emit an Aha hint:

```txt
Aha: this kind of problem in this kind of file and context was solved by this fix strategy.
```

## Intake and output nodes

Every learned pattern declares where information came from and where it may be used.

Known nodes:

```txt
scan-finding-registry
workflow-watch
workflow-repair-plan
generated-file-diff
generated-file-review
action-builder
draft-pr-publisher
learning-memory
telemetry
```

## Input shape

A learning input contains:

```txt
intakeNode
processingNode
outputNodes
problem snapshot
fix snapshot
confidence
tags
```

The problem snapshot includes:

```txt
finding id
category
severity
file path
line number
problem description
before snippet
context paths
context signals
```

The fix snapshot includes:

```txt
fix summary
after snippet
changed files
steps
completed flag
proof
```

## Confidence

```txt
reported   = proposed fix exists, not proven yet
completed  = fix was proven by clean check or test result
manual     = user supplied the repair rule
inferred   = system inferred a likely repair rule
```

A completed pattern must have `fix.completed=true`.

## Soft rejection

Invalid learning input does not hard-fail the full runtime flow.

Instead:

```txt
accepted: false
pattern not added
rejection logged
store returned
summary explains why
```

This is intentional: learning should never break the main build, publish, watch or repair flow.

## Pattern extension

If the same problem/signature/fix appears again, the existing pattern is extended:

```txt
hits +1
successfulUses +1 when completed
confidence upgrades to completed when proof-backed
updatedAt refreshed
```

This is the part that makes memory stronger across sessions.

## Matching

Later queries can ask for matching repair patterns by:

```txt
category
file path / extension
problem wording
context signals
output node
minimum successful uses
```

Matches include:

```txt
score
reasons
Aha explanation
pattern
```

## Runtime validation

Validation exists for:

```txt
input intake
pattern build result
store state
rejection log
match/output list
```

The runtime checks:

- known intake node
- known processing node
- known output nodes
- required file path
- required problem description
- required fix summary
- required changed files
- required repair steps
- completed confidence requires completed fix
- bounded text and list lengths
- no unsafe raw text
- unique pattern ids
- bounded store size
- bounded rejection log
- non-negative counters
- Aha output has score, reasons and text

## Related files

```txt
src/features/product/runtime/solutionPatternMemory.ts
src/features/product/runtime/solutionPatternMemory.test.ts
src/features/product/runtime/runtimeValidationCoverage.ts
```
