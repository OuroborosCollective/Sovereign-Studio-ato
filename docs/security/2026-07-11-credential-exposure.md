# Credential exposure containment — 2026-07-11

A production debugging session introduced authentication material into generated
agent documentation and external work logs. The repository copy is sanitized by
this change without recording the exposed values again.

Required operational actions outside this repository:

1. Rotate the VPS administrator credential and prefer a non-root deploy account.
2. Rotate database, admin API, JWT/session, and LLM proxy credentials that appeared
   in the affected work log.
3. Invalidate sessions derived from the previous JWT secret.
4. Review SSH, API, database, and provider access logs for unexpected use.
5. Rewrite affected public Git history after rotations are complete. A normal
   follow-up commit does not remove values from earlier commits.
6. Do not paste replacement credentials into issues, pull requests, chat, logs, or
   repository documentation.

Runtime containment in this change:

- autonomous repository changes may only create Draft PRs;
- direct Dependabot auto-merge is removed;
- the unfinished local runner is disabled and its standalone entrypoint is
  quarantined;
- backend host publishing is limited to localhost;
- deploy images carry their source revision.
