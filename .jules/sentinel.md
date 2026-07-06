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
