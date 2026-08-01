# AREKappa Integration Lane

This lane contains non-executing contracts and adapter research only.

## Boundary

`Source -> Language AST -> Semantic Graph -> Topology Graph -> kappa IR -> Validator -> Receipt -> Target Adapter`

No file in this directory may be imported by production runtime, exposed as an endpoint, registered as an MCP tool, or used to authorize an effect until a separate reviewed integration explicitly changes that boundary.

## First artifacts

- `kappa-ir.schema.json`: bounded structural contract for the first IR draft.
- Future parser prototypes must target explicit Python and TypeScript subsets.
- Generated code is never trusted merely because it validates structurally.

## Promotion gate

Promotion requires, at minimum:

1. exact base and head revisions;
2. canonical serialization test vectors;
3. cross-language replay equality;
4. nondeterminism and dynamic-execution audits;
5. explicit effect containment;
6. evidence receipts bound to input, program, runtime and result hashes;
7. no production mutation without separate owner-approved integration.
