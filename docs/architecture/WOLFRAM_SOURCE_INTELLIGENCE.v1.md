# Wolfram Source Intelligence v1

## Purpose

Sovereign Studio ATO uses Wolfram CodeTools as a bounded supplemental source-analysis lane for Wolfram Language source. The lane is not a general Wolfram evaluator and is not a repository, deployment, runtime, ARE or Kappa truth source.

Supported operations:

- `parse` — CodeParser AST projection with normalized structural hash and bounded AST preview.
- `inspect` — CodeInspector findings with tag, severity, source range and confidence.
- `format_preview` — CodeFormatter output plus CodeParser structural-equivalence proof. This operation never writes a file.

The public private-MCP surface is one read-only tool: `wolfram_source_intelligence`.

## Reviewed upstream references

These revisions are review anchors only. Runtime identity is reported separately by the Wolfram runtime and must not be inferred from these Git commits.

| Component | Reviewed upstream revision | Role |
| --- | --- | --- |
| CodeParser | `8c6f94947181884b3d6f14a69857d6a01404d1fc` | AST/CST/token source structure |
| CodeInspector | `3f1d5935b9b81c61bf92b78cd0dc68044abe13d7` | static findings |
| CodeFormatter | `023922634ebf3ac93d35baacad54208b4fbaaa0d` | source formatting |

All three reviewed repositories are MIT licensed.

CodeMirror 5, `mathematica-tmbundle` and `wolfram-mode` are not runtime dependencies of this lane. Sovereign already carries a Monaco editor dependency; introducing a second editor/runtime would create duplicate ownership without adding source-truth evidence.

## Execution boundary

The caller supplies Wolfram Language source as text. Before any provider call:

1. the operation is allowlisted,
2. UTF-8 size is limited to 32768 bytes,
3. NUL bytes are rejected,
4. source egress must be explicitly approved for that call.

The backend base64-encodes the source before constructing a fixed Wolfram expression. The decoded string is bound to `s` and is passed only to CodeTools APIs:

```text
source text
  -> UTF-8 bytes
  -> Base64
  -> fixed Wolfram expression
  -> BaseDecode -> string s
  -> CodeParse / CodeInspect / CodeFormat
```

The source is never inserted as executable Wolfram syntax and is never passed to `ToExpression`, `Get`, `RunProcess`, shell, filesystem write or network primitives.

The provider transport is the already-owned `wolfram.cag.compute` component. No second credential store, CAG registry or Wolfram transport is introduced.

## Consent boundary

`source_egress_approved` defaults to `false`.

When false, the MCP client returns:

```text
WOLFRAM_SOURCE_INTELLIGENCE_BLOCKED
source_egress_approval_required
```

without making a provider request. Approval is therefore per call ("just this once"), not an implicit standing grant. The user should be told that supplied source is transmitted to the configured Wolfram provider. Secrets must never be included in source submitted to this tool.

This follows the existing Owner/agent authority rule: tool availability does not grant data-egress authority.

## Evidence contract

Every successful result binds:

- operation,
- exact source SHA-256 and byte count,
- CAG request hash,
- CAG response hash,
- hashed provider request/correlation identifiers,
- reported Wolfram version,
- reported CodeTools paclet versions,
- reviewed upstream reference revisions,
- `sourceExecuted=false`,
- `sourceEgressOccurred=true`,
- `mutationPerformed=false`,
- `runtimeVerified=false`,
- `secretValuesReturned=false`.

Provider success is reported as `WOLFRAM_SOURCE_INTELLIGENCE_SUCCEEDED_UNVERIFIED`.

## Parse contract

`parse` uses `CodeParse`. Source-location Associations are removed only for the normalized structural hash; the bounded AST preview retains normal parser source metadata.

The result includes:

- normalized AST SHA-256,
- structural leaf count,
- bounded AST preview.

A successful parse is static evidence only. CodeParser error recovery means a returned tree does not by itself mean the program is semantically correct.

## Inspector contract

`inspect` uses `CodeInspect` and projects at most 100 findings.

Each projected finding contains:

- tag,
- description,
- severity,
- source range,
- confidence.

The result reports whether findings were truncated.

Static findings never become runtime truth and never authorize an effect.

## Formatter contract

`format_preview` performs:

```text
original source
  -> CodeParse
  -> remove parser metadata
  -> normalized AST A

original source
  -> CodeFormat
  -> formatted source
  -> CodeParse
  -> remove parser metadata
  -> normalized AST B

A == B ?
```

Only when the normalized structures are equal does the response set `safeToApply=true`.

A mismatch returns `WOLFRAM_SOURCE_FORMAT_DRIFT_DETECTED` and `ok=false`. The formatted source may still be inspected, but the lane does not apply it.

Actual file mutation remains owned by Sovereign workspace tools. A later formatter-apply workflow must bind the preview source hash and formatted-source hash to the exact workspace blob, show the diff, use workspace-write authority, rerun relevant tests and produce ordinary repository evidence.

## Runtime truth

This lane deliberately reports `runtimeVerified=false`.

Runtime/deployment truth still requires the normal causal chain:

- exact repository revision,
- GitHub CI on the exact head,
- immutable backend/MCP image digest where relevant,
- target deployment readback,
- Docker/container health,
- PatchMon/fleet evidence.

CodeTools output cannot replace any of those gates.
