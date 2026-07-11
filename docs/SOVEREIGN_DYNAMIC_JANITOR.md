# Sovereign Dynamic Janitor

The Dynamic Janitor is an explicit, job-scoped repository tool. It does not run
as a background agent and it does not create runtime truth from UI state.

## Runtime contract

1. The user starts a normal Sovereign Agent job for a GitHub repository.
2. The backend creates an isolated workspace and clones the requested branch.
3. `POST /api/user/agent/jobs/<job_id>/tools/janitor` runs inside that owned repo.
4. `mode: "scan"` is read-only and returns deterministic findings.
5. `mode: "apply"` writes exactly one reviewed SEARCH/REPLACE operation.
6. Diff and test evidence remain separate required runtime steps before Draft PR.
7. The tool never commits, pushes, merges, creates a PR, or runs tests.

## Scan mode

```json
{
  "mode": "scan",
  "family": "runtime truth and state contradictions",
  "paths": ["src", "backend"],
  "maxFindings": 10,
  "maxFiles": 200,
  "includeDocs": false,
  "explainWithLocalModel": false
}
```

Python files are parsed with the standard Python AST. JavaScript, TypeScript,
workflow, shell, JSON, TOML, and optional Markdown files use conservative text
rules. Every finding includes a stable ID, file, line, masked evidence, and the
SHA-256 hash of the reviewed file.

## Confirmed apply mode

```json
{
  "mode": "apply",
  "path": "src/example.ts",
  "searchText": "exact reviewed text",
  "replacementText": "exact reviewed replacement",
  "expectedSha256": "64-character digest returned by the scan",
  "confirm": true
}
```

Apply is blocked when the file changed after review, SEARCH matches zero or more
than one location, the path escapes the repo, the target resembles a secret, or
the replacement introduces forbidden security/workflow patterns.

A successful apply returns `changedFiles` and a unified `diffSummary`, but no test
claim. The caller must run the existing test tool next. Only fresh test evidence
may unlock Draft-PR preparation.

## Model explanations

Direct Ollama or arbitrary model network calls are intentionally disabled inside
the Janitor. `explainWithLocalModel: true` returns a truthful blocker message and
does not affect the deterministic scan.

A later explanation layer may use the existing controlled Sovereign LLM runtime.
It may receive only sanitized finding metadata and must remain explanation-only.
Model output must never create a patch, test result, success state, commit, push,
or pull request.
