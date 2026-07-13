---
name: sovereign-cognitive-architecture
description: Enforce Sovereign's eight-role, evidence-first, Draft-PR-only development workflow.
---

Use this skill only for Sovereign Studio repository work.

## Fixed topology

Operate with exactly eight roles in this order:

1. Dispatcher
2. Data & Storage
3. Business & Core Logic
4. Endpoint & Bridge
5. Functional Chat & Cognitive Action
6. UI, CSS & Accessibility
7. Predictive Build Nervous System & QA
8. Judge

The Dispatcher plans. The six workers inspect or propose bounded changes in their assigned domains. The Judge reviews evidence and never edits files.

## Truth requirements

- Never claim a file change, test result, browser result, deployment, database mutation or Draft PR without runtime evidence.
- Never use mocks, stubs or invented snapshots in a production truth path.
- Keep UI state downstream from runtime state.
- Keep secrets outside prompts, traces, tool arguments, logs and repository content.
- Use isolated workspaces and exact search/replace patches for existing files.
- End code work at a Draft PR unless a separate explicit, evidence-backed approval authorizes a later action.
- Never auto-merge.

## Double loop

Run the fixed sequence:

1. Dispatcher plan.
2. Six-worker pass one.
3. Judge checkpoint one.
4. Six-worker refinement pass two, even when pass one appears clean.
5. Judge final verdict.

A final verdict may say `draft_pr_ready` only when supplied evidence proves all required checks passed and no blocker remains. Missing evidence is a blocker, not success.

## Approval boundary

Any write, deployment, migration, merge, secret access or other high-impact action must be performed by a bounded tool with explicit policy checks. Human approval must pause and resume the same workflow state; approval must never be inferred from silence.

## Offline and storage boundary

Treat `/mnt/sdcard/sovereign_data` as a native-device path. Web code must not access it directly. Use a validated native bridge and fail closed when the bridge is unavailable. External asset origins and object-storage buckets must come from real configuration, not hardcoded placeholder domains.

## UI and Apps SDK

Widgets display structured runtime evidence. They do not manufacture completion states. Use a strict CSP, no external scripts by default, accessible controls, and a follow-up approval message rather than an unreviewed destructive tool call.
