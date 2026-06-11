## 2026-06-11 - Secure Sandbox Syntax Validation
**Vulnerability:** Use of 'eval()' for validating untrusted LLM-generated code, posing a Remote Code Execution (RCE) risk.
**Learning:** Even if code is wrapped in a try-catch and intended only for syntax checking, 'eval()' executes it immediately in the current context.
**Prevention:** Use 'new Function(code)' for syntax validation without immediate invocation to ensure safety while maintaining functionality.

## 2026-06-11 - CI Shell Incompatibility (Sentinel Learning)
**Vulnerability:** Shell scripts in GitHub Actions failing due to '-o pipefail' in Dash (default /usr/bin/sh).
**Learning:** Ubuntu runners often use Dash for /bin/sh which is POSIX compliant but lacks bashisms like 'pipefail'.
**Prevention:** Explicitly use 'shell: bash' in GitHub Actions steps or stick to POSIX 'set -e' if using default shell.
