# GitHub Auth Session

The GitHub Auth Session layer centralizes how the app handles user-provided GitHub tokens.

It exists to keep private repo access and Draft PR publishing useful without spreading token handling across random UI and runtime code.

## Rules

```txt
Token may live in React state during the visible session.
Token must not be written into session memory.
Token must not be written into generated files.
Token must not be written into telemetry.
Token must not be written into docs.
Token must be redacted from error text before display.
```

## Core utility

```txt
src/features/github/githubAuthSession.ts
```

It provides:

- `normalizeGitHubToken`
- `hasGitHubToken`
- `redactGitHubToken`
- `createGitHubAuthSession`
- `buildGitHubHeaders`
- `requireGitHubToken`
- `stripTokenFromText`

## Integrated paths

The auth session utility is used by:

```txt
src/features/github/hooks/useGithubRepo.ts
src/features/github/githubPackagePublisher.ts
src/features/product/runtime/workflowWatch.ts
src/App.tsx
```

## Behavior

Repo loading may work with or without a token. Private repos usually require a token.

Workflow Watch may work with or without a token depending on repo visibility and GitHub API rate limits.

Draft PR publishing always requires a token.

Diff source loading uses the same session token when available, but treats missing or inaccessible source files honestly as not found/source-missing.

## Safety model

The token is still a user-provided secret. The app does not make it magically safe. The goal is to keep token handling deliberate and easy to audit.

Use this rule for future code:

```txt
Never build GitHub Authorization headers manually.
Use buildGitHubHeaders instead.
```

Use this rule for write operations:

```txt
Never check token.trim() manually in write paths.
Use requireGitHubToken instead.
```

Use this rule for user-visible errors:

```txt
Before displaying an error that may include request text, run stripTokenFromText.
```

## Related tests

```txt
src/features/github/githubAuthSession.test.ts
src/features/product/runtime/sovereignStructure.test.ts
src/features/product/runtime/runtimeValidationCoverage.ts
```
