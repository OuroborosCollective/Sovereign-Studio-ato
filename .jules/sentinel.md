## 2026-06-10 - Fix Remote Code Execution (RCE) in APK Sandbox Service
**Vulnerability:** The `verifyCodeInAPK` function used `eval()` to execute a string that interpolated user-provided code into a wrapper function. This allowed an attacker to use closing braces and other tokens to "break out" of the wrapper and execute arbitrary code in the host environment during what was supposed to be a simple syntax check.
**Learning:** Even when intended for "sandboxed" syntax checks, `eval()` executes code immediately. Constructing a `new Function(code)` is a much safer alternative for syntax validation because it compiles the code (triggering syntax errors if invalid) but does NOT execute it until the function is invoked.
**Prevention:** Avoid `eval()` entirely. For syntax validation, use `new Function()` without invoking it, or use a dedicated parser like Acorn or Esprima.

## 2026-06-19 - Prevent Credential Leakage in AI Provider Errors
**Vulnerability:** AI provider responses often echo back invalid or unauthorized API keys in error messages, which could be logged or displayed to the user, leading to credential leakage.
**Learning:** Error messages from external APIs are untrusted and must be sanitized. Standardizing on a `maskSecrets` utility that covers multiple key formats (ghp, gsk, sk-, etc.) ensures consistent protection across different providers.
**Prevention:** Always wrap external error messages in `maskSecrets()` before passing them to UI state or logging services.
