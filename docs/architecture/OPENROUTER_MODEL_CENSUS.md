# OpenRouter model census

Sovereign can execute a bounded, one-request-per-model census over the currently persisted, selectable paid OpenRouter catalog. The census is an execution/availability observation only; it is not a semantic-quality benchmark and does not rank models.

## Safety contract

- The protected OpenRouter API key remains behind the existing owner-managed file boundary and is never returned by the census.
- The catalog snapshot and exact model set are hash-bound before execution.
- Each model is eligible for at most one client request attempt for a given operation identity.
- Client automatic retries are disabled and OpenRouter provider fallback is disabled.
- The request budget is fixed at 64 output tokens with a 15 second timeout and bounded parallelism of four.
- Raw model content, raw tool arguments, and raw provider error bodies are never persisted. Only bounded metadata and SHA-256 digests are written.
- A process interruption after an attempt marker is preserved as `INTERRUPTED_UNKNOWN`; recovery never silently resends that model.
- Results such as `OBSERVED`, `BUDGET_EXHAUSTED`, `REJECTED`, `TIMEOUT`, `NO_VISIBLE_OUTPUT`, and `INTERRUPTED_UNKNOWN` are execution-state observations. `truthVerdict` remains `NOT_ASSERTED` and `leaderboardEnabled` remains false.

## Operation identity

The operation ID binds the running backend source revision, immutable image digest, OpenRouter catalog snapshot SHA-256, model-set SHA-256, and expected model count. A completed receipt is immutable and re-reading the same operation returns the existing receipt without repeating provider requests.

The current owner-request compatible invocation uses the reserved route identifier `openrouter-paid-census-<expected_model_count>` through the existing internal OpenRouter activation boundary. The public MCP still receives no API key and can only request/read bounded census state.

## Evidence output

The final receipt records the exact model identities, per-model classification, HTTP status when observed, latency, OpenRouter request ID when available, resolved model/provider metadata when returned, finish reason, tool-call conformance, usage/reasoning-token counters, observed provider cost when supplied by OpenRouter, and input/output hashes. The receipt itself is canonically SHA-256 bound.

A census proves only what was observed during that exact revision-bound run. It must not be promoted into a model-quality leaderboard or a universal provider reliability claim without further repeated and task-specific evidence.
