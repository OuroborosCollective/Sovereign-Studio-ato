import { fetchFileFromGitHub } from '../services/githubService';
import { askRefactorLLM } from '../services/llmService';
import { verifyCodeInAPK } from '../services/sandboxService';

export interface LogItem {
  id: string;
  time: string;
  type: 'info' | 'success' | 'warn' | 'error';
  text: string;
}

type LogFn = (text: string, type?: LogItem['type']) => void;

export interface RefactorParams {
  owner: string;
  repo: string;
  branch: string;
  path: string;
  instruction: string;
}

export interface RefactorReview {
  originalCode: string;
  updatedCode: string;
  sourceSha: string;
}

/**
 * Erstellt ausschließlich einen revisionsgebundenen Änderungskandidaten.
 * Diese Funktion schreibt weder in GitHub noch beweist sie Build-, CI- oder
 * Runtime-Erfolg. Die nachgelagerte UI darf nur einen Draft-PR anfordern.
 */
export async function runRefactorPipeline(
  params: RefactorParams,
  onLog: LogFn,
  maxFixAttempts = 3,
): Promise<RefactorReview | null> {
  try {
    onLog('📥 Lade die Datei über den sessiongeschützten Sovereign-Gateway.', 'info');
    const { content: originalCode, sha: sourceSha } = await fetchFileFromGitHub(params);
    onLog(`✅ Ausgangsfassung revisionsgebunden geladen (${sourceSha.slice(0, 12)}…).`, 'success');

    onLog('🤖 Erzeuge einen Refactoring-Kandidaten über die konfigurierte LLM-Route.', 'info');
    const systemPrompt = [
      'Du bist ein präziser TypeScript-Refactoring-Agent.',
      'Ändere bestehenden Code exakt nach Anweisung.',
      'Entferne keine bestehende Kernlogik, außer dies wird ausdrücklich verlangt.',
      'Behaupte niemals Build-, Test-, CI-, Deployment- oder Runtime-Erfolg.',
    ].join(' ');
    let updatedCode = await askRefactorLLM(originalCode, params.instruction, systemPrompt);

    let attempts = 0;
    let candidatePassedBoundedCheck = false;
    while (attempts < maxFixAttempts && !candidatePassedBoundedCheck) {
      onLog(
        `🧪 [Prüfung ${attempts + 1}/${maxFixAttempts}] Führe den begrenzten lokalen Syntax-Kandidatencheck aus.`,
        'info',
      );
      const validation = verifyCodeInAPK(updatedCode);

      if (validation.success) {
        candidatePassedBoundedCheck = true;
        onLog(
          '✅ Der Kandidat bestand den begrenzten lokalen Check; vollständige Build- und CI-Evidence steht noch aus.',
          'success',
        );
      } else {
        attempts += 1;
        onLog(`⚠️ Begrenzter Check meldet: "${validation.errorLog}"`, 'warn');
        if (attempts < maxFixAttempts) {
          onLog('🔄 Erzeuge anhand dieses Befunds einen neuen Kandidaten.', 'warn');
          updatedCode = await askRefactorLLM(
            updatedCode,
            `Der begrenzte lokale Check meldet: ${validation.errorLog}. Korrigiere ausschließlich diesen Befund.`,
            systemPrompt,
          );
        }
      }
    }

    return candidatePassedBoundedCheck
      ? Object.freeze({ originalCode, updatedCode, sourceSha })
      : null;
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Unbekannter Pipeline-Fehler';
    onLog(`🚨 Pipeline abgebrochen: ${message}`, 'error');
    return null;
  }
}