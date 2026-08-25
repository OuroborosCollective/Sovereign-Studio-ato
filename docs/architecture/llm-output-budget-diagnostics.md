# LLM output-budget diagnostics

Sovereign must not treat every blank, partial, or schema-invalid model response as evidence that a provider is unavailable. A routed request can execute successfully and still exhaust its bounded output budget before a useful visible payload is emitted, particularly when the provider reports reasoning-token usage inside the completion budget.

## External motivating evidence

The public Hugging Face Shadow Bench contains two controlled `openai/gpt-oss-120b @ groq` slices that held provider, model, temperature and a 64/96/128 output-budget ladder fixed while changing the fixed seed. They are external diagnostic evidence only; they are not runtime authority for Sovereign and are not a provider/model quality score.

- seed `424242`: slice SHA-256 `a3c315adf47c05209659de28ead52748850d6373f6ef05fc3bfb2a951024d8bb`; observed first conformant tested budget 96.
- seed `424243`: slice SHA-256 `381cf468609e564471657183fcb2024e3af4c763f6e21404a608cc602458213e`; observed first conformant tested budget 128.

Both controlled seeds failed to emit the bounded literal at 64 and both emitted it at 128. The 96 result differed by seed, so Sovereign MUST NOT hardcode 96, 128, Groq, or Hugging Face as a routing threshold or authority from this evidence.

## Runtime rule

When a result is already invalid, empty, partial, or rejected by its output contract, Sovereign may inspect only bounded provider metadata such as:

- `finish_reason` / incomplete reason;
- completion/output token count;
- reasoning-token count when supplied by the provider;
- the request-local configured output limit.

If the bounded metadata shows an explicit length/max-output finish, or a reasoning-bearing response consumed the configured output limit, the failure family is `AGENTS_OUTPUT_BUDGET_EXHAUSTED` with next action `RETRY_WITH_BOUNDED_OUTPUT_BUDGET_INCREASE`.

This classification does not itself authorize a retry, provider switch, increased spend, or model change. It only prevents a budget-exhaustion observation from being mislabeled as provider unavailability or a generic structured-output failure. Existing cost, entitlement, retry, route and owner-policy boundaries remain authoritative.

## Truth and security boundary

The diagnostic persists no raw model output and no raw provider error text. It returns bounded counters and finish metadata only, with `truthVerdict=NOT_ASSERTED`. A successful output that already satisfies its contract must not be rejected merely because reasoning tokens were present.
