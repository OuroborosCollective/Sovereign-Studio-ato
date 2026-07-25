# APK Live Device Failure-Family Hunt — 2026-07-25

## Truth boundary

- Repository: `OuroborosCollective/Sovereign-Studio-ato`
- Isolated workspace: `job-d54b2da137a1`
- Workspace branch: `sovereign/chatgpt/1784934534-apk-operator-failure-family-hunt-0821bd`
- Exact starting revision: `ee6197b061d175d5a7b6ef788420623b725a24b0`
- Starting `main`, workspace HEAD, and deployed private MCP revision matched exactly.
- No swarm or delegated coding agent was used.
- No local Node dependency installation was performed.
- No production deploy, merge, container stop, database mutation, or secret read was performed.
- All fixes described below exist only in the isolated workspace until a Draft PR is published, CI is green, and an exact immutable release is deployed.

## Evidence sources

1. Live Android device video, 8:04 minutes, 1080×1810, no audio track.
2. Exact-revision repository reads and searches.
3. Bounded VPS container status and logs.
4. Local Python, installer, syntax, import, and diff checks.
5. Android static release preflight.
6. GitHub Actions is the mandatory truth source for TypeScript, Vitest, web build, Gradle, APK, and AAB execution.

## Outcome summary

| Failure family | Initial state | Workspace outcome | Production outcome |
|---|---|---|---|
| `DIRECT_LLM_SESSION_401` | Confirmed | Fixed and regression-covered | Not deployed |
| `LEGACY_LITELLM_SIDE_ARCHITECTURE` | Confirmed | Retired from active app/backend/operator/installer contracts | Legacy containers still running pending canary-gated retirement |
| `GITHUB_OAUTH_LOCALHOST_REDIRECT` | Confirmed | Fixed | Not deployed |
| `GITHUB_OAUTH_NO_WINDOW_OPENER` | Plausible mobile consequence | Native deep-link return implemented and tested in Vitest source | Not deployed |
| `TOOLCHAIN_APK_RELATIVE_BASE` | Confirmed by code plus device symptoms | Fixed | Not deployed |
| `TOOLCHAIN_HTML_INSTEAD_OF_JSON` | Confirmed | Fixed classification and regression test added | Not deployed |
| `TOOLCHAIN_ENDPOINT_PATH_DRIFT` | Confirmed | Fixed | Not deployed |
| `NETWORK_ERROR_MISCLASSIFICATION` | Confirmed | Fixed | Not deployed |
| `OFFLINE_FALLBACK_UNKNOWN_PRESENTATION` | Confirmed | Fixed presentation; fail-closed behavior preserved | Not deployed |
| `MOBILE_TOUCH_ACCESSIBILITY` | Confirmed on relevant Toolchain controls | Relevant controls hardened | Not deployed |
| `SCHEMA_MIGRATION_LAYOUT_DRIFT` | Historical/runtime compatibility signal | No current defect proven; no patch | Observe only |

---

# Run 01 — DIRECT_LLM_SESSION_401

## Real finding

The video showed `Sovereign LLM Intent HTTP 401`, `worker · blockiert`, and `Offline-Fallback=unknown`.

The reverse repository trace located the exact producer in:

- `src/features/product/runtime/sovereignLiteLlmIntentRuntime.ts`
- request target `/api/llm/chat`
- backend route `scripts/sovereign-backend/app.py::public_llm_chat`
- backend guard `@require_session`

The forward trace showed that `BuilderContainer` could invoke online language interpretation without a confirmed `authUser`. The backend correctly rejected the request. This was therefore not an OpenRouter outage and not a Worker reachability failure; it was a missing client-side session gate before an intentionally protected backend route.

## Fix

- Added a strict `authUser` gate before any route catalog or LLM chat request.
- Guest requests now produce a truthful blocked message, open login, send no LLM request, and deduct no credits.
- HTTP 401 is classified as `authentication`, not `worker_config` or network failure.
- A real 401 refreshes session state and opens login.
- Active imports now use the canonical direct OpenRouter/FreeLLM module name.

## Forward test

`guest input -> BuilderContainer auth gate -> no /api/llm/routes -> no /api/llm/chat -> login surface`

## Reverse test

`HTTP 401 -> DevChatWorkerDiagnostic(authentication) -> session refresh/login -> no provider-secret recommendation`

## Seven logical deployment consequences checked

1. **Repeated unauthorized chat requests** — fixed by pre-request session gate.
2. **Credits charged for rejected requests** — blocked; no protected request is sent as guest.
3. **Provider outage falsely reported** — fixed by authentication-specific diagnostic scope.
4. **Blind retry loop after expired session** — blocked; refresh and login are requested instead.
5. **Provider credentials moved into APK as a workaround** — explicitly prohibited by diagnostics and architecture.
6. **Guest tests falsely passing protected LLM calls** — fixed by separating authenticated test setup from a real guest regression test.
7. **OpenRouter blamed for backend session rejection** — removed from user-facing classification.

## Evidence/tests

- Added HTTP 401 diagnostic regression test.
- Added Builder guest regression test proving no route/chat request.
- Node execution is intentionally deferred to GitHub Actions.

---

# Run 02 — LEGACY_LITELLM_SIDE_ARCHITECTURE

## Real finding

The intended productive architecture is direct OpenRouter paid transport plus direct FreeLLM free transport. Nevertheless, the hunt found all of the following:

- Active legacy compose stack in repository and operator allowlist.
- Active installer packaging and deployment capability.
- Active MCP tools capable of inventory and alias activation.
- Active backend registration of `llm_provider_runtime.py` with LiteLLM proxy/catalog/activation paths.
- Real VPS containers:
  - `sovereign-litellm-litellm-1` — healthy at inspection time.
  - `sovereign-litellm-db-1` — healthy at inspection time.
- Bounded logs showed health checks and two model inventory requests; no completion traffic was observed in the inspected range.

This was not merely a stale filename. It was a live secondary architecture capable of being managed and reactivated.

## Fix

- Removed `sovereign-litellm` from managed compose allowlist.
- Removed plan/deploy handling from `ManagedComposeRuntime`.
- Installer no longer installs the LiteLLM runtime module or compose templates.
- Installer removes stale LiteLLM backend environment variables and container allowlist entries.
- Command worker no longer has write access to `/opt/sovereign-litellm`.
- Active backend no longer imports or registers `register_llm_provider_routes`.
- Added direct internal OpenRouter status/activate endpoints protected by the owner service key.
- Added canonical MCP tools:
  - `openrouter_provider_status`
  - `openrouter_provider_activate`
- Legacy LiteLLM MCP tools remain only as read-only `RETIRED` tombstones with no network or mutation effect.
- Legacy owner target `litellm_provider_key` is no longer allowlisted.
- The historical `litellm_stack.py` constructor is permanently fail-closed and cannot instantiate a deployment runtime.
- MCP CI no longer compiles, packages, compares, or requires LiteLLM templates as release assets.
- Existing VPS containers were deliberately not stopped before merge, CI, deploy, and direct-route canaries.

## Forward test

`installer/update -> no LiteLLM module/templates -> no legacy compose allowlist -> no legacy container write access -> direct OpenRouter/FreeLLM only`

## Reverse test

`legacy MCP tool name -> local RETIRED result -> replacement points to OpenRouter -> no broker call -> no stack mutation`

## Seven logical deployment consequences checked

1. **A later self-update silently reinstalls LiteLLM** — fixed by removing installer packaging/templates.
2. **Operator redeploys the retired stack** — fixed by removing stack from allowlist and deployment branches.
3. **Legacy containers remain privileged through command worker paths** — fixed by removing write path and allowlist entries.
4. **Old backend endpoints create new LiteLLM routes** — fixed by removing runtime registration from active `app.py`.
5. **MCP still offers mutating LiteLLM tools** — fixed; old names are read-only tombstones.
6. **OpenRouter credentials are routed through a LiteLLM owner target** — fixed; target removed, direct OpenRouter bridge added.
7. **Immediate container shutdown causes unknown hidden dependency outage** — intentionally not performed; retirement is canary-gated after deployment.

## Evidence/tests

- `test_managed_compose.py`: 31 passed.
- `test_install_contract.py`: 12 passed.
- `test_installer_contract.py`: 9 passed.
- `test_owner_input_client.py`: 23 passed.
- `test_backend_release_a2a_evidence.py`: 3 passed.
- `test_command_queue.py`: 8 passed.
- `test_openrouter_integration_static.py`: 9 passed.
- `test_owner_input_install_contract.py`: 8 passed.
- `test_bootstrap_deploy_contract.py`: 6 passed.
- `test_operating_profile.py`: 5 passed.
- `test_private_litellm_provider_contract.py`: 8 passed.
- `test_litellm_retirement.py`: 1 passed.
- Historical LiteLLM deployment tests: 12 deliberately skipped after retirement.
- `app.py` Python compilation passed.
- Internal Flask endpoint tests are defined; the lightweight local image skips Flask cases and full backend CI must execute them.

---

# Run 03 — GITHUB_OAUTH_LOCALHOST_REDIRECT

## Real finding

Backend runtime evidence contained:

`GITHUB_OAUTH_REDIRECT_IGNORED`

with client redirect:

`https://localhost/auth/github/callback.html`

The client built the callback URL from `window.location.origin`, which is `https://localhost` in the Capacitor WebView. The backend correctly ignored this and used its canonical registered redirect.

## Fix

- Client no longer sends `redirect_uri` to OAuth init.
- Backend remains the sole authority for the registered HTTPS callback URI.
- State, PKCE, and opener-origin verification remain intact.

## Forward test

`APK -> /api/auth/github/init with opener_origin only -> backend canonical redirect -> GitHub`

## Reverse test

`backend audit -> no client_redirect_uri mismatch -> callback bound to server configuration`

## Seven logical deployment consequences checked

1. **GitHub redirect mismatch rejection** — fixed by removing client redirect input.
2. **Environment-specific callback drift** — fixed by server authority.
3. **APK localhost callback opened in WebView** — removed from init request.
4. **Client expands OAuth redirect allowlist** — impossible through this request contract.
5. **PKCE state detached from canonical redirect** — preserved through backend init state.
6. **Web and APK choose different redirect paths** — unified at backend.
7. **Audit noise masks real OAuth failures** — expected redirect-ignored event is eliminated after deployment.

## Evidence/tests

- Test asserts `redirect_uri` is absent from OAuth init body.

---

# Run 04 — GITHUB_OAUTH_NO_WINDOW_OPENER

## Real finding

The public callback page required `window.opener`. An Android external browser opened through Capacitor may return without a usable opener relation. The video did not prove this exact second-stage failure, but it is a direct mobile consequence of the observed OAuth flow and existing callback implementation.

The Android manifest already registered app schemes, but the OAuth runtime did not use them.

## Fix

- Native flow uses `@capacitor/browser` and `@capacitor/app`.
- Listener is registered before browser open.
- Callback page first verifies the OAuth state context through the backend.
- When no opener exists and the confirmed opener is native, callback redirects to:
  `com.arestudio.nocode.aab://auth/github/callback`
- APK parses the exact protocol/host/path, validates state again, closes browser, and removes listener.
- Web popup behavior remains unchanged.

## Forward test

`APK Browser.open -> GitHub -> canonical HTTPS callback -> backend callback-context -> app deep link -> App.appUrlOpen -> state validation`

## Reverse test

`deep link -> exact protocol/host/path filter -> state match -> code+verifier returned -> browser/listener cleanup`

## Seven logical deployment consequences checked

1. **External browser cannot postMessage to WebView** — fixed by deep-link fallback.
2. **Untrusted site invokes arbitrary app URL** — constrained by exact scheme, host, path, and state.
3. **Deep link races before listener registration** — listener is registered before browser open.
4. **Listener leak handles a later unrelated URL** — listener is removed on completion.
5. **Browser remains open after success** — closed after finish.
6. **Web popup flow regresses** — native branch is conditional; web branch remains.
7. **Error callback loses its reason** — error is carried through the deep link and returned as failure.

## Evidence/tests

- Native Capacitor test covers Browser.open, appUrlOpen, state, cleanup, and no popup use.

---

# Run 05 — TOOLCHAIN_APK_RELATIVE_BASE

## Real finding

The toolchain client used a relative base:

`/api/toolchain/universal`

In the APK WebView this can resolve against `https://localhost`, producing an HTML application fallback or 404 instead of the backend JSON contract. This matches the device symptoms.

## Fix

- Toolchain uses the same canonical absolute backend base as auth and direct LLM.
- `VITE_ADMIN_API_BASE` remains an explicit override.
- Session cookies are included.
- `Headers` are normalized through the Web API rather than spread from a union type.

## Forward test

`APK -> absolute sovereign backend -> /api/toolchain/universal/manifest -> JSON`

## Reverse test

`HTML/404 symptom -> requested origin/path -> relative base -> Capacitor localhost -> absolute-base correction`

## Seven logical deployment consequences checked

1. **Manifest request hits WebView localhost** — fixed.
2. **Invoke request hits a different origin than manifest** — both derive from one base.
3. **Session cookie omitted on protected invoke** — credentials included.
4. **Environment override keeps trailing slash and creates double slash** — base normalized.
5. **Header union spread loses `Headers` values** — fixed by `new Headers()` normalization.
6. **GET incorrectly sends unnecessary content type** — content type is set only with a body.
7. **Tests pass only in browser origin but fail in APK** — absolute URL assertion added.

---

# Run 06 — TOOLCHAIN_HTML_INSTEAD_OF_JSON

## Real finding

Device UI showed:

`Unexpected token '<', "<!DOCTYPE "... is not valid JSON`

The client called `response.json()` directly, so a proxy/frontend HTML response escaped as a generic JavaScript parse error.

## Fix

- Client reads bounded text first.
- Detects HTML by content type or leading `<`.
- Produces typed `invalid_response` with bounded snippet and status.
- Invalid non-HTML JSON is distinguished from HTML.

## Forward test

`HTTP response -> text -> JSON parse -> typed result`

## Reverse test

`parse failure -> content type/body prefix -> invalid_response -> truthful UI title`

## Seven logical deployment consequences checked

1. **Raw SyntaxError leaks to user** — fixed.
2. **HTML login page reported as network outage** — classified as invalid response.
3. **HTML 404 hides status** — status is retained.
4. **Huge HTML body floods logs/UI** — snippet is bounded.
5. **Empty successful response accepted as manifest** — blocked as invalid response.
6. **Malformed JSON accepted through type assertion** — blocked before return.
7. **Retry button repeatedly calls an unknown broken origin** — UI now exposes the actual response family.

## Evidence/tests

- Added HTML 404 regression test.

---

# Run 07 — TOOLCHAIN_ENDPOINT_PATH_DRIFT

## Real finding

The UI advertised:

- `/toolchain/mcp`
- `/toolchain/api/v1/tools/{name}`
- `/toolchain/api/openapi.json`

The exact backend route inventory registered:

- `/api/toolchain/universal/status`
- `/api/toolchain/universal/manifest`
- `/api/toolchain/universal/invoke`

The browser-visible 404 therefore had a direct repository explanation.

## Fix

- UI now displays only registered Status, Manifest, and Invoke contracts.
- Invoke is not exposed as a browser-openable GET link.
- Stale public MCP/REST/OpenAPI documentation removed from the active panel/client.

## Forward test

`UI link -> exact registered GET route -> backend response`

## Reverse test

`browser 404 -> displayed URL -> no matching backend decorator -> replace with route inventory truth`

## Seven logical deployment consequences checked

1. **User copies non-existent endpoint** — fixed.
2. **GET opens a POST-only invoke route** — open action disabled for Invoke.
3. **External client configured against dead MCP URL** — removed from active UI.
4. **Docs and client diverge again** — both use exported canonical endpoint constants.
5. **Proxy adds HTML fallback for unknown path** — unknown path no longer advertised.
6. **Status badge goes offline while backend is healthy** — manifest now targets real backend path.
7. **Operator diagnoses full server outage from one missing route** — typed path-specific errors now shown.

---

# Run 08 — NETWORK_ERROR_MISCLASSIFICATION

## Real finding

The device used “Worker nicht erreichbar” or “Server nicht erreichbar” for responses that proved reachability:

- HTTP 401
- HTTP 404
- HTML response

## Fix

Typed classifications now distinguish:

- authentication
- permission
- not found
- invalid response
- client request
- server
- real network failure

## Forward test

`response status/body -> deterministic failure kind -> specific title/action`

## Reverse test

`displayed title -> failure kind -> preserved status/body evidence`

## Seven logical deployment consequences checked

1. **401 triggers infrastructure restart** — fixed classification.
2. **404 triggers credential reset** — fixed classification.
3. **HTML proxy fallback triggers offline mode** — classified invalid response.
4. **403 prompts user to retry login forever** — distinguished from 401.
5. **5xx blamed on client form** — classified server/upstream.
6. **real fetch rejection loses network identity** — classified network.
7. **support logs cannot correlate user-visible message with HTTP evidence** — status retained in structured error.

---

# Run 09 — OFFLINE_FALLBACK_UNKNOWN_PRESENTATION

## Real finding

The local classifier intentionally returns `unknown` when free language cannot be mapped safely to an action. The UI rendered this as `Offline-Fallback=unknown`, which looked like an uninitialized or broken subsystem.

## Fix

- Fail-closed behavior is preserved.
- User/operator evidence now says `free_language_not_safely_classifiable`.
- No action success is claimed.

## Forward test

`online interpretation failure -> local classifier -> no safe intent -> explicit fail-closed evidence`

## Reverse test

`free_language_not_safely_classifiable -> no allowed action -> no repository/runtime mutation`

## Seven logical deployment consequences checked

1. **Unknown interpreted as successful fallback** — prevented.
2. **Unknown interpreted as uninitialized code** — clarified.
3. **Unsafe keyword action executed from free language** — unchanged fail-closed boundary.
4. **User assumes offline model answered** — wording says classification, not answer.
5. **Runtime success is fabricated** — explicitly prohibited.
6. **Support cannot distinguish no-match from runtime failure** — evidence token is specific.
7. **Future classifier expansion silently changes safety** — regression expectation remains action-gated.

---

# Run 10 — MOBILE_TOUCH_ACCESSIBILITY

## Real finding

The device video and static audit both showed small interaction targets in the Toolchain panel, including copy/open/reload/result controls and a clickable non-button card header.

## Fix

- Relevant controls use 44×44 pixel targets.
- Tool card header is a semantic button with `aria-expanded`.
- Copy/open/reload/result buttons have accessible labels.
- Run button has a 44-pixel minimum height.
- Secondary endpoint text was enlarged.

## Forward test

`touch -> semantic target >=44 -> one deterministic action`

## Reverse test

`mis-tap candidate -> measured inline dimensions/element role -> corrected target`

## Seven logical deployment consequences checked

1. **Copy opens endpoint accidentally** — separate 44-pixel controls.
2. **Reload is hard to hit** — enlarged.
3. **Result copy is inaccessible to screen readers** — labeled.
4. **Clickable div lacks keyboard semantics** — replaced by button.
5. **Expanded state unavailable to accessibility tree** — `aria-expanded` added.
6. **Invoke is opened as URL rather than executed** — open control omitted.
7. **Dense mobile panel causes repeated mis-taps** — key action targets hardened; broader UI audit remains separate.

---

# Run 11 — SCHEMA_MIGRATION_LAYOUT_DRIFT

## Real finding

Runtime logs previously showed a compatibility family resembling:

`schema_migrations_layout_drift / id_name_to_legacy_version / runtime_sql_only`

During this hunt, current exact-revision schema/runtime evidence did not prove a failing migration, missing required schema object, or blocked readiness caused by this family.

## Decision

No schema patch was made. Modifying migration bookkeeping without a current schema inventory conflict would be speculative and could damage historical migration identity.

## Forward test

`migration runner -> current schema layout -> compatibility path -> migration completion`

## Reverse test

`runtime drift marker -> schema/readiness evidence -> no current blocker -> observe only`

## Seven logical deployment consequences checked

1. **Duplicate migration application** — not observed.
2. **Migration version collision** — not observed.
3. **Fresh database differs from upgraded database** — plausible; requires dedicated preview comparison.
4. **Runtime rewrite masks old schema debt** — plausible; retained as follow-up.
5. **Readiness becomes green with missing tables** — current readiness contract checks required schema objects.
6. **Manual repair corrupts migration history** — avoided by no speculative patch.
7. **Future migration assumes one column layout** — should be covered by a dedicated schema-layout test in a separate database-focused change.

---

# Validation ledger

## Local checks completed

| Check | Result |
|---|---|
| `git diff --check` | PASS |
| Managed compose tests | 31 passed |
| Installer contract tests | 12 passed |
| Secondary installer contract tests | 9 passed |
| Owner/OpenRouter client tests | 23 passed |
| OpenRouter integration static tests | 9 passed |
| Backend release/A2A import tests | 3 passed |
| Command queue/server import tests | 8 passed |
| Owner-input/MCP workflow contract tests | 8 passed |
| Bootstrap deploy workflow contract tests | 6 passed |
| Operating profile workflow contract tests | 5 passed |
| Backend LiteLLM-retirement contract tests | 8 passed |
| LiteLLM fail-closed constructor test | 1 passed |
| Historical LiteLLM deploy suite | 12 skipped by explicit retirement marker |
| `scripts/sovereign-backend/app.py` compile | PASS |
| Android static standard preflight | `RELEASE_READY`, 0 critical/high/medium/low/info findings |

## Mandatory remote checks

The operator correctly refused local Node execution with:

- `LOCAL_NODE_EXECUTION_FORBIDDEN`
- `REMOTE_CI_REQUIRED`

Required GitHub Actions evidence after Draft PR publication:

1. TypeScript typecheck.
2. Targeted Vitest suites.
3. Web build.
4. Android Gradle build.
5. APK/AAB artifact inspection.
6. Full backend tests with Flask dependencies.
7. MCP registry/contract checks after adding OpenRouter tool names.

# Deployment sequence after green CI

1. Re-resolve exact PR head and base revision.
2. Require all relevant checks green on that exact head.
3. Merge only through the owner-approved repository policy; no merge is part of this hunt.
4. Build immutable backend/MCP/APK artifacts from the merged revision.
5. Deploy exact digests and verify source revision/image digest readback.
6. Run direct OpenRouter status, catalog, protected completion canary, and `/api/llm/chat` authenticated device flow.
7. Run direct FreeLLM readiness and completion canaries.
8. Repeat the original Android device scenario, collecting WebView console, HTTP status, trace IDs, backend logs, and logcat.
9. Verify zero traffic/dependency on legacy LiteLLM during a bounded observation window.
10. Only then stop the two legacy LiteLLM containers. Retain volumes/config backup for the rollback window; deletion is a separate owner-approved action.

# Final truth statement

The workspace removes the confirmed causes and retires the unintended LiteLLM side architecture from active code and management contracts. It does **not** prove production green yet. Production remains unchanged until Draft PR CI, exact revision readback, immutable deployment, and a repeated real-device test complete successfully.
