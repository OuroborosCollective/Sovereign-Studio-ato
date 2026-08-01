# AREKappa Wolfram Research Lane

This lane is isolated research material. It is not imported by production code, packaged into runtime images, registered as an endpoint, or authorized to mutate repository, database, container, MCP, or application state.

## Inputs

- `docs/architecture/AREKAPPA_SPECIFICATION_V0.md`
- exact integer/rational parameters
- versioned reference fixtures

## Outputs

- symbolic checks
- counterexamples
- exact reference vectors
- proof candidates
- explicit uncertainty or unresolved findings

Every output must record:

- specification version
- Wolfram expression
- exact inputs
- exact output
- output hash
- whether the result is proof, example, counterexample, or advisory analysis

Promotion into the integration lane requires an explicit, reviewed artifact and deterministic reproduction outside Wolfram.
