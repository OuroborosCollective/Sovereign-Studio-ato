# Sovereign Contract Scan Scripts

These scripts back the `Sovereign Runtime Contract Scan` workflow.

- `sovereign-contract-scan.mjs` checks app/runtime handoff contracts.
- `sovereign-ux-contract-scan.mjs` checks user-visible flow and design contracts.
- `sovereign-live-path-scan.mjs` checks the real `src/` live path for unsafe implementation patterns.

The live-path scanner intentionally treats test fixtures and security-pattern definitions differently from production runtime code. Real secrets, old DOM installer paths, test doubles in live code, and placeholder implementation markers remain blocking findings.
