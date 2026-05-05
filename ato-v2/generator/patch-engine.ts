import { createPatch } from 'diff';

/**
 * Sovereign Studio V3 - Patch Engine
 * Transformiert LLM-Generierungen in valide Unified Diff Patches für die Repository-Synchronisation.
 * Optimiert für die hybride Architektur (Vite/Capacitor) und Gemini-API-Workflows.
 */

export interface PatchOptions {
  contextLines?: number;
  filename: string;
}

export interface PatchResult {
  success: boolean;
  patch: string;
  error?: string;
}

export class PatchEngine {
  private readonly contextLines: number;

  constructor(options?: Partial<PatchOptions>) {
    this.contextLines = options?.contextLines ?? 3;
  }

  /**
   * Erzeugt einen Git-kompatiblen Patch aus dem Originalzustand und dem LLM-Vorschlag.
   * Nutzt die createPatch-Methode der diff-Library für höchste Format-Konsistenz.
   */
  public generatePatch(filename: string, originalCode: string, modifiedCode: string): PatchResult {
    try {
      if (originalCode === modifiedCode) {
        return { success: true, patch: '' };
      }

      // Erzeugung des Unified Diffs mit standardisierten Header-Präfixen
      const patch = createPatch(
        filename,
        originalCode,
        modifiedCode,
        `a/${filename}`,
        `b/${filename}`,
        { context: this.contextLines }
      );

      // Prüfung ob tatsächliche Änderungen (Hunks) im Patch enthalten sind
      // Verhindert das Senden leerer Patches mit nur Metadaten
      const lines = patch.split('\n');
      const hasHunks = lines.some(line => line.startsWith('@@'));

      return {
        success: true,
        patch: hasHunks ? patch : ''
      };
    } catch (error) {
      return {
        success: false,
        patch: '',
        error: error instanceof Error ? error.message : 'Unknown patch generation error'
      };
    }
  }

  /**
   * Extrahiert Code-Blöcke aus LLM-Antworten (Markdown-Sicher).
   * Implementiert ohne globale Regex-Ersetzungen zur Einhaltung der Sicherheitsvorgaben.
   */
  public extractCodeFromResponse(response: string): string {
    const delimiter = '';
    if (!response.includes(delimiter)) {
      return response.trim();
    }

    const segments = response.split(delimiter);
    
    // Durchsuche Segmente nach Code-Blöcken (jeder zweite Eintrag nach dem Split-Pattern)
    for (let i = 1; i < segments.length; i += 2) {
      const segment = segments[i];
      const lines = segment.split('\n');
      
      if (lines.length === 0) continue;

      const firstLine = lines[0].toLowerCase().trim();
      // Validierung gängiger Dateitypen im Sovereign Studio V3 Stack
      const languages = [
        'typescript', 'ts', 'tsx', 
        'javascript', 'js', 'json', 
        'css', 'scss', 'html', 
        'xml', 'markdown', 'bash'
      ];
      
      if (languages.some(lang => firstLine === lang || firstLine.startsWith(lang))) {
        // Entferne Sprach-Identifier-Zeile und gebe den Code-Rumpf zurück
        const codeLines = lines.slice(1);
        return codeLines.join('\n').trim();
      }
    }

    // Fallback: Extraktion des ersten verfügbaren Inhalts-Segments
    return segments[1] ? segments[1].trim() : response.trim();
  }
}