# Agent Instructions

Use this toolchain as a safe implementation workspace.

## Default behavior

1. Read and analyze first.
2. Preview changes with `preview_search_replace` or `github_apply_search_replace_pr` using `confirm=false`.
3. Ask for approval before write actions.
4. Create Draft PRs only. Do not push directly to `main`.
5. Use `expected_sha` when applying a change that was previewed earlier.
6. Never print tokens, Authorization headers, secrets, or full environment dumps.

## Recommended tool sequence

For repo edits:

```text
github_read_file
preview_search_replace
github_apply_search_replace_pr(confirm=false)
github_apply_search_replace_pr(confirm=true)
```

For backend guardrail hardening:

```text
apply_backend_guardrails_patch_pr(confirm=false)
apply_backend_guardrails_patch_pr(confirm=true)
```

For sandbox verification:

```text
toolchain_briefing
plan_sandbox_commands(goal="verify")
```
