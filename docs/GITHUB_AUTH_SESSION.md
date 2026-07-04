# GitHub Auth Session

The GitHub Auth Session layer centralizes how the app handles user-provided GitHub access values.

It exists to keep private repo access, write-access validation and Draft PR publishing useful without spreading sensitive credential handling across random UI and runtime code.

## Rules

```txt
Access values may live in React state during the visible session.
Access values must not be written into session memory.
Access values must not be written into generated files.
Access values must not be written into telemetry.
Access values must not be written into docs.
Access values must not be written into chat history or action events.
Access values must be redacted from error text before display.
Only masked representations may be stored in runtime state.
```

## Core utilities

```txt
src/features/github/githubAuthSession.ts
src/features/product/runtime/githubAccessRuntime.ts
src/features/product/components/GitHubAccessCard.tsx
```

`githubAuthSession.ts` provides shared header and redaction helpers:

- `normalizeGitHubToken`
- `hasGitHubToken`
- `redactGitHubToken`
- `createGitHubAuthSession`
- `buildGitHubHeaders`
- `requireGitHubToken`
- `stripTokenFromText`

`githubAccessRuntime.ts` owns product-level write access state:

- token format validation;
- token masking;
- real GitHub API validation for the loaded repo;
- `validating`, `ready` and failure states;
- capability checks such as `canPerformGitHubWrite(...)`.

## Integrated paths

The auth/access layer is used by:

```txt
src/features/github/hooks/useGithubRepo.ts
src/features/github/githubPackagePublisher.ts
src/features/product/runtime/workflowWatch.ts
src/features/product/runtime/githubAccessRuntime.ts
src/features/product/components/GitHubAccessCard.tsx
src/features/product/containers/BuilderContainer.tsx
```

## Behavior

Repo loading may work with or without a token. Private repos usually require a token.

Workflow Watch may work with or without a token depending on repo visibility and GitHub API rate limits.

Write operations require validated GitHub write access for the loaded repository. A format-valid token is not enough.

Draft PR publishing always requires validated GitHub access and reviewable changes.

Diff source loading uses the same session access when available, but treats missing or inaccessible source files honestly as not found/source-missing.

## Write access state model

The product should display access state honestly:

```txt
missing/requested → user action needed
validating → GitHub API check is running
ready → GitHub write access is confirmed
invalid/failed → operation is blocked with reason
```

Important split:

```txt
GitHub ready ≠ OpenHands ready
GitHub ready ≠ workspace ready
GitHub ready ≠ Draft PR already created
```

If GitHub access is ready but OpenHands is not configured, the next action is not to reopen GitHub access. The next action is to use Direct GitHub Patch if available, configure a workspace/OpenHands executor, or block honestly.

## Android clipboard guidance

When a user pastes an access value on Android, the app must warn clearly:

```txt
GitHub-Zugang wurde übernommen. Prüfung läuft.
Bitte Android-Zwischenablage leeren, falls der Zugangswert kopiert wurde.
```

After successful validation:

```txt
GitHub-Zugang ist bereit. Der Zugangswert wird nicht im Chat gespeichert.
Wenn er in einem Screen Recording oder Clipboard-Verlauf sichtbar war, bitte rotieren.
```

Optional clipboard clearing may be offered only if the environment supports it. If it cannot be done, the app must say so honestly and ask the user to clear the clipboard manually.

## Safety model

The access value is still a user-provided secret. The app does not make it magically safe. The goal is to keep handling deliberate, auditable and easy to test.

Use this rule for future code:

```txt
Never build GitHub Authorization headers manually.
Use buildGitHubHeaders instead.
```

Use this rule for write operations:

```txt
Never treat token format as write access.
Use the GitHub API validation result / githubAccessRuntime state.
```

Use this rule for user-visible errors:

```txt
Before displaying an error that may include request text, run stripTokenFromText.
```

Use this rule for UI/state:

```txt
Never put raw access values in chat lines, action events, telemetry, issue bodies, PR bodies, session memory or docs.
```

## Related tests

```txt
src/features/github/githubAuthSession.test.ts
src/features/product/runtime/githubAccessRuntime.test.ts
src/features/product/runtime/builderChatHelpers.test.ts
src/features/product/runtime/sovereignStructure.test.ts
src/features/product/runtime/runtimeValidationCoverage.ts
```

## Related issues

```txt
#505 Security/UX: harden GitHub credential handling and Android clipboard guidance
#500 Runtime: route write intents after GitHub ready without OpenHands lock-in
```
