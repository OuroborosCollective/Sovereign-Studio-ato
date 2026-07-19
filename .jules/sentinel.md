## 2026-06-10 - Fix Remote Code Execution (RCE) in APK Sandbox Service
**Vulnerability:** The `verifyCodeInAPK` function used `eval()` to execute a string that interpolated user-provided code into a wrapper function. This allowed an attacker to use closing braces and other tokens to "break out" of the wrapper and execute arbitrary code in the host environment during what was supposed to be a simple syntax check.
**Learning:** Even when intended for "sandboxed" syntax checks, `eval()` executes code immediately. Constructing a `new Function(code)` is a much safer alternative for syntax validation because it compiles the code (triggering syntax errors if invalid) but does NOT execute it until the function is invoked.
**Prevention:** Avoid `eval()` entirely. For syntax validation, use `new Function()` without invoking it, or use a dedicated parser like Acorn or Esprima.

## 2026-06-24 - Mask Secrets in AI Provider Error Messages
**Vulnerability:** AI provider API calls often include the original API key in error messages (e.g., "Invalid API key sk-..."). These messages were being passed directly to the UI state and logs, potentially leaking sensitive credentials to users or telemetry systems.
**Learning:** Error messages from external services should always be treated as untrusted and potentially sensitive input. Masking must happen at the edge of the service integration (e.g., in the provider manager or catch blocks) before the error propagates to the rest of the application.
**Prevention:** Always wrap external error messages with `maskSecrets` (or similar utility) in catch blocks. When re-throwing, construct a `new Error(maskedMsg)` to prevent the original error object (which might store the secret in internal properties) from leaking further up the stack.

## 2026-07-08 - Secured Cloudflare Worker AI Proxy (Open Relay Fix)
**Vulnerability:** The `cloudflare-worker-ai-proxy` was an open relay, allowing anyone with the URL to consume the configured Cloudflare Workers AI resources without authentication.
**Learning:** Edge functions and proxies that bridge to paid or resource-limited APIs must implement their own authentication layer, even if they are "internal" to a larger system, to prevent unauthorized usage and potential cost spikes.
**Prevention:** Always implement a simple API key or token-based authentication (e.g., via `PROXY_API_KEY` environment variable) for AI proxies before deployment.

## 2025-05-22 - Multi-Layered Secret Redaction in Log/Telemetry Utilities
**Vulnerability:** Log utilities like `stripTokenFromText` originally only redacted the specific GitHub token provided. If an error message contained both a GitHub token and an AI provider key (e.g., in a failed cross-provider operation), the AI key would still be leaked.
**Learning:** Redaction utilities should not be limited to redacting a single known value. Integrating a central, pattern-based `maskSecrets` utility into all log-stripping paths provides a critical second layer of defense (defense in depth).
**Prevention:** Always pipe log strings through a generalized `maskSecrets` utility even when a specific token is already being stripped. Ensure the utility covers all provider prefixes used in the app (e.g., `sk-or-v1-`, `hf_`, `together_`, `pollinations_`).

## 2025-05-23 - Proactive Secret Masking at the Normalization Layer
**Vulnerability:** Chat messages and suggestions were normalized and stored in application state before any redaction occurred. While outgoing AI calls were protected, the raw secrets remained in the local runtime state and UI-bound objects.
**Learning:** Security controls like secret masking should be applied as early as possible (at the entry/normalization layer) to minimize the "blast radius" of sensitive data within the application's memory and state management.
**Prevention:** Integrate `maskSecrets` directly into normalization utilities (like `trimText` or `validateChatEntry`) that process user-provided or external content before it is committed to state.

## 2026-07-24 - Dual-Layer Redaction for Runtime Monitors
**Vulnerability:** Runtime monitors and "Coach" components captured DOM text and unmasked runtime signals, potentially displaying API keys or tokens in persistent UI logs or session storage.
**Learning:** Masking at the source (publishers) is necessary but insufficient if components also scrape the DOM. A dual-layer strategy—masking at the publishing layer (e.g., `useCoachRuntimeBridge`) AND the UI rendering layer (e.g., `AgentMonitor`)—provides robust protection against secrets entering the UI from multiple paths.
**Prevention:** Always apply `maskSecrets` at the point of data publishing (CustomEvents/Window state) and as a final filter during UI rendering of captured or log-based text.

## 2026-06-25 - Defense-in-Depth for Secure Logging Components
**Vulnerability:** The `SafeLogText` component only applied masking when explicitly flagged as sensitive. Additionally, internal transmission errors and the bridge payload itself could leak raw secrets if the `isSensitive` prop was omitted or set incorrectly by the developer.
**Learning:** Security utilities designed for "safe" logging should not rely solely on developer-provided flags for protection. Automatic pattern-based redaction provides a critical safety net (defense-in-depth) for cases where sensitive data is passed to a generic log field.
**Prevention:** Always integrate a central `maskSecrets` utility as a mandatory filter in safe-rendering components. Ensure that even "unlabeled" data passes through pattern recognition before it reaches the UI, logs, or external bridges.

## 2025-05-24 - Defensive Secret Masking for Error Messages and Health Checks
**Vulnerability:** Technical error messages from external AI providers (e.g., "Invalid key sk-...") and system health logs were leaking raw secrets into UI responses and backend logs because the sanitization was inconsistent or limited to specific fields.
**Learning:** Hardcoded string-slicing for secret masking is fragile and fails to catch secrets nested in unexpected error strings or dynamic configuration objects. A central, pattern-based utility that covers a broad range of provider-specific key formats is essential for defense-in-depth.
**Prevention:** Wrap all technical error messages in a central `sanitize_agent_text` utility before returning them in API responses. Use recursion for dictionary-based configuration masking to ensure nested secrets are redacted regardless of their depth. Ensure contract files are mirrored between backend and script directories to maintain policy consistency.

## 2026-07-17 - Prevent SSRF in External Worker Dispatchers
**Vulnerability:** The `/api/toolchain/apply-patch-worker` endpoint allowed the client to supply an arbitrary `worker_url` which was then fetched server-side via `requests.post`. An attacker could exploit this to perform Server-Side Request Forgery (SSRF) to scan internal services, pivot within private infrastructure, or access cloud metadata endpoints.
**Learning:** Accepting user-provided URLs in server-side HTTP dispatchers is highly dangerous. Unless strictly required, avoid allowing custom target URLs. If customization is required, validate that the scheme is strictly secure (HTTPS) and that the hostname/netloc exactly matches the trusted default or an explicit domain allowlist.
**Prevention:** Always parse and validate user-supplied URLs using a robust parser like `urllib.parse.urlparse`. Restrict the protocol to `https` and enforce that the hostname matches a trusted default domain or designated whitelist before initiating server-side requests.

## 2026-07-28 - Memory Leakage and Memory Exhaustion (DoS) in In-Memory Rate Limiters
**Vulnerability:** The OAuth rate-limiter stored list records of request timestamps per identifier in an in-memory dictionary. While old timestamps were filtered out per-key on subsequent requests, empty lists (`[]`) were never deleted, and keys for clients that ceased to request remained in the store forever. This enabled attackers to execute a slow-rate distributed scan or spoofed identifier attack to infinitely grow the store's dictionary and trigger an out-of-memory crash (DoS).
**Learning:** In-memory tracking systems without strict eviction and bounded size controls are highly susceptible to memory leaks and resource exhaustion attacks. When implementing rate limiters or caching stores, we must always proactively delete empty/expired keys and enforce hard watermarks to sweep expired state.
**Prevention:** When filtering list-like entries per key, immediately `del` or pop the key if its filtered list becomes empty. Furthermore, implement proactive sweeps or bounded watermarks on the store's overall dictionary length to drop expired keys during active request processing.
