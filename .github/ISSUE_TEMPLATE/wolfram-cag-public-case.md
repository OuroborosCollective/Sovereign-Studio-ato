---
name: Wolfram CAG public benchmark case proposal
about: Propose a new public, reproducible claim-check case (or a reproducible failure report) for the Wolfram CAG evidence lane
title: "[CAG public case] <short claim summary>"
labels: enhancement
---

## Claim being checked

<!-- Example: "17 * 23 equals 391". Must be a public, non-sensitive fact. -->

## Proposed case id

<!-- e.g. cag-bench-013 -->

## Expected comparison verdict

<!-- SUPPORTED | CONTRADICTED | INCONCLUSIVE -->

## Which component does this target?

<!-- wolfram.cag.hints | wolfram.cag.compute | wolfram.cag.results | wolfram.cag.context -->

## Why this case is publicly reproducible

<!-- Elementary/public facts only. No private repositories, prompts, accounts,
     secrets, or commercially restricted data. -->

## Normalization / tolerance (if numeric)

<!-- e.g. absolute tolerance 0, relative tolerance 1e-9 -->

## For failure reports: reproduce the behavior

- Git revision (`git rev-parse HEAD`):
- Python version:
- Exact command run:
- Full `--json` output:

## Checklist

- [ ] The claim uses only public, non-sensitive values
- [ ] No secrets, tokens, private infrastructure details or personal data included
- [ ] The expected verdict follows the deterministic comparison rules
- [ ] I ran `python scripts/run-wolfram-cag-benchmark.py --json` locally (for a proposal)

/labels not settable by non-collaborators: a maintainer will triage.
