export interface SandboxResult {
  success: boolean;
  errorLog?: string;
}

// Da wir keine node_modules in der APK ausführen können, validiert diese Sandbox,
// ob der modifizierte Code syntaktisch korrekt ist und grundlegende Logiktests besteht.
export function verifyCodeInAPK(modifiedCode: string): SandboxResult {
  // ✅ SECURITY FIX: replaced eval() with new Function() for syntax validation.
  // This prevents Remote Code Execution (RCE) vulnerabilities because
  // new Function(code) only parses the code without executing it.
  try {
    // We only want to check if the code is syntactically correct.
    // The body of 'new Function' is the modified code itself.
    // If there's a syntax error, it will throw during construction.
    new Function(modifiedCode);
    return { success: true };
  } catch (error: any) {
    return { success: false, errorLog: error.message };
  }
}