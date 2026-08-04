---
name: security-supply-chain
description: Gate secrets, dependencies, dynamic execution, permissions, SBOM, provenance, signatures, authentication, tenant isolation, and ownership through verifiable evidence.
triggers:
  - security audit
  - check supply chain
  - inspect secrets
  - verify release provenance
---

# Security and supply chain

Separate secret-shaped test fixtures and placeholders from real rotation candidates without returning raw values. Assess secret references by owner, target, age, rotation interval, and canary freshness.

Rank dependency vulnerabilities by reachable production paths and exploit prerequisites, not severity labels alone. Minimize each tool's declared filesystem, database, network, and host permissions to observed requirements.

Audit dynamic imports, generated code, shell execution, and sandbox boundaries by active path. Require negative authentication and tenant-isolation evidence where applicable.

For release artifacts, bind the exact repository revision to immutable image digest, revision label, dependency pinning, SBOM digest, provenance digest, signature verification, and attestation verification. A workflow name, artifact filename, or green badge without matching identities is insufficient.

Check CODEOWNERS coverage for critical paths and use owner approval policy for protected actions. Never store protected credentials, tokens, private endpoints, or raw production data in this plugin.
