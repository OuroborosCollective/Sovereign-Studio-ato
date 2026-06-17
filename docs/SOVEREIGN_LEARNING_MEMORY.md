# Sovereign Learning Memory

Sovereign Learning Memory is a validated pattern store. It is not magic AI learning and it is not session restore.

It exists to remember useful, evidence-backed patterns such as:

```txt
A failed lint workflow should create a focused repair mission.
A generated file review with a forbidden path must block publishing.
A docs request usually needs README + Update History + Runtime docs.
```

## Difference from Session Memory

Session Memory remembers visible UI state:

```txt
repo URL
branch
repo file snapshot
mission
summary
preview
```

Learning Memory remembers validated patterns:

```txt
source node
output nodes
kind
summary
evidence
tags
confidence
hits
```

The two should stay separate.

## Nodes

Learning Memory uses explicit intake/output nodes.

```txt
repo-snapshot
readiness-report
file-integrity
generated-file-review
diff-preview
workflow-watch
workflow-repair-plan
health-report
telemetry
user-mission
action-builder
draft-pr-publisher
```

A pattern must declare where information came from and where it may be used.

Example:

```txt
sourceNode: workflow-watch
outputNodes: workflow-repair-plan, action-builder
```

This means Workflow Watch produced the evidence and the result may be used by Repair Planner and Action Builder.

## Runtime validation

The runtime validates:

- source node is known
- every output node is known
- summary exists
- evidence exists
- content length is bounded
- tags are normalized
- secret-like content is redacted or rejected
- hits are positive
- createdAt is not newer than updatedAt
- store version is supported
- pattern ids are unique
- store size is bounded

## Secret handling

Learning Memory must not store raw secrets.

It redacts patterns such as:

```txt
ghp_...
github_pat_...
sk-...
Bearer ...
password=...
token=...
```

If a forged pattern still contains unredacted secret-like content, validation fails.

## Confidence

A pattern must state confidence:

```txt
observed
inferred
manual
```

Use `observed` when the app saw a concrete runtime event.

Use `inferred` when the app derived a likely pattern from weak evidence.

Use `manual` when the user deliberately supplies the rule.

## Safety rules

Learning Memory may suggest context.

Learning Memory may not bypass:

- Sequential Runtime Guard
- GitHub Auth Session
- Functional Guards
- Generated File Review
- Diff Preview
- Draft PR Publisher validation
- Workflow Watch

## Related files

```txt
src/features/product/runtime/sovereignLearningMemory.ts
src/features/product/runtime/sovereignLearningMemory.test.ts
src/features/product/runtime/runtimeValidationCoverage.ts
src/features/product/runtime/sovereignStructure.test.ts
```
