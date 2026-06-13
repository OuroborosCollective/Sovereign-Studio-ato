export interface SandboxResult {
  success: boolean;
  errorLog?: string;
}

/**
 * Validiert, ob der modifizierte Code syntaktisch korrekt ist.
 * Verwendet 'new Function()', um die JavaScript-Syntax zu prüfen, ohne den Code auszuführen.
 * Dies schützt vor Remote Code Execution (RCE) Risiken, die mit eval() verbunden sind.
 */
export function verifyCodeInAPK(modifiedCode: string): SandboxResult {
  try {
    // Nutzt den Function-Konstruktor zur Syntax-Validierung
    // Der Code wird geparst, aber nicht aufgerufen.
    new Function(modifiedCode);
    return { success: true };
  } catch (error: any) {
    // Syntaxfehler werden hier abgefangen
    return { success: false, errorLog: error.message };
  }
}
