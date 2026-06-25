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
