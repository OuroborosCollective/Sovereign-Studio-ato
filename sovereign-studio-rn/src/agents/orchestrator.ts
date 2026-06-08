import { fetchFileFromGitHub } from "../services/githubService";
import { askRefactorLLM } from "../services/llmService";
import { verifyCodeInAPK } from "../services/sandboxService";

export interface LogItem {
  id: string;
  time: string;
  type: "info" | "success" | "warn" | "error";
  text: string;
}

type LogFn = (text: string, type?: LogItem["type"]) => void;

export interface RefactorParams {
  patToken: string;
  owner: string;
  repo: string;
  branch: string;
  path: string;
  instruction: string;
}

// Verbindet alle Schritte zu einer vollautomatischen Pipeline mit Live-Logging für das User-Interface.
export async function runRefactorPipeline(
  params: RefactorParams,
  onLog: LogFn,
  maxFixAttempts = 3
): Promise<string | null> {
  try {
    // Schritt 1: Code downloaden
    onLog("📥 Verbinde mit GitHub-API... Lade Datei herunter.", "info");
    const { content: originalCode } = await fetchFileFromGitHub(params);
    onLog("✅ Originaler Quellcode erfolgreich geladen.", "success");

    // Schritt 2: LLM Inferenz starten
    onLog("🤖 Übermittle Code an Free-LLM für das Refactoring...", "info");
    const systemPrompt =
      "Du bist ein präziser TypeScript-Refactoring-Agent. Ändere bestehenden Code exakt nach Anweisung ab. Entferne keine bestehende Kernlogik, es sei denn, es wird verlangt.";
    let updatedCode = await askRefactorLLM(
      originalCode,
      params.instruction,
      systemPrompt
    );

    let attempts = 0;
    let codeIsValid = false;

    // Schritt 3: Lokaler Validierungs- und Fix-Loop innerhalb der APK
    while (attempts < maxFixAttempts && !codeIsValid) {
      onLog(
        `🧪 [Testlauf ${attempts + 1}/${maxFixAttempts}] Überprüfe Code-Syntax in der APK-Sandbox...`,
        "info"
      );
      const validation = verifyCodeInAPK(updatedCode);

      if (validation.success) {
        codeIsValid = true;
        onLog(
          "🎉 Code-Überarbeitung erfolgreich validiert! Keine Syntaxfehler.",
          "success"
        );
      } else {
        attempts++;
        onLog(
          `⚠️ Sandbox-Fehler erkannt: "${validation.errorLog}"`,
          "warn"
        );

        if (attempts < maxFixAttempts) {
          onLog(
            "🔄 Starte autonomen Auto-Fix-Loop mit dem Fehlerprotokoll...",
            "warn"
          );
          updatedCode = await askRefactorLLM(
            updatedCode,
            `Der Code hat folgenden Syntaxfehler erzeugt: ${validation.errorLog}. Bitte korrigiere diesen Fehler im Code.`,
            systemPrompt
          );
        }
      }
    }

    return codeIsValid ? updatedCode : null;
  } catch (err: any) {
    onLog(`🚨 Kritischer Pipeline-Fehler: ${err.message}`, "error");
    return null;
  }
}