# Retired Cloudflare Worker AI proxy

This Cloudflare Worker AI proxy is retired. The package is a fail-closed historical tombstone. It is not part of the
Sovereign Studio runtime and must not be deployed, configured with secrets, or
used as a browser/API endpoint.

Canonical online inference is:

```text
App -> Sovereign Backend -> direct OpenRouter Paid or direct FreeLLM Free -> owner-verified provider
```

The package commands that could start or administer a Worker deliberately fail.
The retained handler answers every request with HTTP 410 before it reads a
request body or contacts a model provider.
