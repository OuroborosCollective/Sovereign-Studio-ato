export interface SandboxResult {
  success: boolean;
  errorLog?: string;
}

/**
 * Validiert, ob der modifizierte Code syntaktisch korrekt ist.
 * 🛡️ Sentinel: Nutzt 'new Function()' statt 'eval()', um RCE zu verhindern.
 */
export function verifyCodeInAPK(modifiedCode: string): SandboxResult {
  try {
    // Erzeugt eine neue Funktion nur zur Syntaxprüfung.
    // Die Funktion wird NICHT ausgeführt, was die Sicherheit erhöht.
    new Function(modifiedCode);
    return { success: true };
  } catch (error: any) {
    return { success: false, errorLog: error.message };
  }
}
