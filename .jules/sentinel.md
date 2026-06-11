## 2026-06-11 - Secure Sandbox Syntax Validation
**Vulnerability:** Use of 'eval()' for validating untrusted LLM-generated code, posing a Remote Code Execution (RCE) risk.
**Learning:** Even if code is wrapped in a try-catch and intended only for syntax checking, 'eval()' executes it immediately in the current context.
**Prevention:** Use 'new Function(code)' for syntax validation without immediate invocation to ensure safety while maintaining functionality.
