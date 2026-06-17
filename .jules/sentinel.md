## 2026-06-10 - Fix Remote Code Execution (RCE) in APK Sandbox Service
**Vulnerability:** The `verifyCodeInAPK` function used `eval()` to execute a string that interpolated user-provided code into a wrapper function. This allowed an attacker to use closing braces and other tokens to "break out" of the wrapper and execute arbitrary code in the host environment during what was supposed to be a simple syntax check.
**Learning:** Even when intended for "sandboxed" syntax checks, `eval()` executes code immediately. Constructing a `new Function(code)` is a much safer alternative for syntax validation because it compiles the code (triggering syntax errors if invalid) but does NOT execute it until the function is invoked.
**Prevention:** Avoid `eval()` entirely. For syntax validation, use `new Function()` without invoking it, or use a dedicated parser like Acorn or Esprima.

## 2026-06-17 - Prevent Internal Leakage in Error Boundaries
**Vulnerability:** The UI `ErrorBoundary` was logging the full `error.stack` and `componentStack` to the browser console. While helpful for debugging, this exposes the application's internal directory structure, module names, and code logic to anyone inspecting the console in production.
**Learning:** Standard security practice for production web apps is to log only sanitized/masked error messages to the client console. Detailed traces should be sent to a secure, private logging service or only logged in development environments.
**Prevention:** Ensure `ErrorBoundary` and global error handlers do not log raw stacks or component trees. Always pass error strings through masking utilities before logging or displaying them.
