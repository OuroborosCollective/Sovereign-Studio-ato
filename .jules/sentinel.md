## 2025-06-13 - [HIGH] Fix RCE in sandboxService.ts
**Vulnerability:** Remote Code Execution (RCE) via unsafe eval() in code validation.
**Learning:** The sandboxService used eval() to check JS syntax of modified code, which allowed arbitrary code execution in the application context.
**Prevention:** Use 'new Function(code)' constructor for syntax validation. It parses the code without executing it immediately, providing a safer way to check for syntax errors.
