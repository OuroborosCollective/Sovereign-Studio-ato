## 2026-06-10 - Fix Remote Code Execution (RCE) in APK Sandbox Service
**Vulnerability:** The `verifyCodeInAPK` function used `eval()` to execute a string that interpolated user-provided code into a wrapper function. This allowed an attacker to use closing braces and other tokens to "break out" of the wrapper and execute arbitrary code in the host environment during what was supposed to be a simple syntax check.
**Learning:** Even when intended for "sandboxed" syntax checks, `eval()` executes code immediately. Constructing a `new Function(code)` is a much safer alternative for syntax validation because it compiles the code (triggering syntax errors if invalid) but does NOT execute it until the function is invoked.
**Prevention:** Avoid `eval()` entirely. For syntax validation, use `new Function()` without invoking it, or use a dedicated parser like Acorn or Esprima.

## 2025-05-15 - Proactive Secret Masking in AI Provider Interfaces
**Vulnerability:** AI providers often echo back the API key in error messages (e.g., "Invalid API key: sk-xxx..."). If these errors are directly set in state or logged, the secrets leak into the UI and telemetry.
**Learning:** Catching and wrapping error messages with a redaction utility (`maskSecrets`) before they reach any observable sink (state, logs, telemetry) is essential when dealing with external LLM providers.
**Prevention:** Always process `error.message` through `maskSecrets` in AI-related catch blocks and re-throw as a new Error object to strip sensitive data from the original error's properties.
