## 2026-06-10 - Fix Remote Code Execution (RCE) in APK Sandbox Service
**Vulnerability:** The `verifyCodeInAPK` function used `eval()` to execute a string that interpolated user-provided code into a wrapper function. This allowed an attacker to use closing braces and other tokens to "break out" of the wrapper and execute arbitrary code in the host environment during what was supposed to be a simple syntax check.
**Learning:** Even when intended for "sandboxed" syntax checks, `eval()` executes code immediately. Constructing a `new Function(code)` is a much safer alternative for syntax validation because it compiles the code (triggering syntax errors if invalid) but does NOT execute it until the function is invoked.
**Prevention:** Avoid `eval()` entirely. For syntax validation, use `new Function()` without invoking it, or use a dedicated parser like Acorn or Esprima.

## 2026-06-18 - Secret Leakage in AI Error Messages
**Vulnerability:** AI provider error messages (from Gemini, Groq, etc.) were found to sometimes echo back sensitive API keys or Bearer tokens in the error string itself, especially when authentication failed or rate limits were hit. These raw error strings were then displayed in the UI or stored in client-side logs.
**Learning:** Never trust error messages from third-party APIs. They may contain the very credentials that failed.
**Prevention:** Always pass error strings through a sanitization utility like `maskSecrets` before displaying them in the UI or persisting them to logs. This provides defense-in-depth even if a provider's error reporting is overly verbose.
