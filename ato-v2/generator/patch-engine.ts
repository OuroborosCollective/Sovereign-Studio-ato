import { createPatch } from 'diff';

/**
 * Sovereign Studio V3 - Patch Engine
 * Transformiert LLM-Generierungen in valide Unified Diff Patches für die Repository-Synchronisation.
 * Optimiert für die hybride Architektur (Vite/Capacitor) und Gemini-API-Workflows.
 * 
 * HINWEIS: Erfordert 'diff' und '@types/diff' in den Projekt-Abhängigkeiten zur Behebung von TS2307.
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
      // Normalisierung der Zeilenenden für konsistente Diff-Erzeugung
      const normalizedOriginal = originalCode.replace(/\r\n/g, '\n');
      const normalizedModified = modifiedCode.replace(/\r\n/g, '\n');

      if (normalizedOriginal === normalizedModified) {
        return { success: true, patch: '' };
      }

      // Erzeugung des Unified Diffs mit standardisierten Header-Präfixen (Git-Style)
      const patch = createPatch(
        filename,
        normalizedOriginal,
        normalizedModified,
        `a/${filename}`,
        `b/${filename}`,
        { context: this.contextLines }
      );

      // Prüfung ob tatsächliche Änderungen (Hunks) im Patch enthalten sind
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
   * Implementiert eine robuste Logik zur Identifikation von Code-Fence-Blöcken.
   */
  public extractCodeFromResponse(response: string): string {
    const delimiter = '';
    
    if (!response.includes(delimiter)) {
      return response.trim();
    }

    const segments = response.split(delimiter);
    
    // Durchsuche Segmente nach Code-Blöcken (jeder zweite Eintrag nach dem Split-Pattern ist Inhalt innerhalb der Backticks)
    for (let i = 1; i < segments.length; i += 2) {
      const segment = segments[i];
      if (!segment) continue;

      const lines = segment.split('\n');
      if (lines.length === 0) continue;

      const firstLine = lines[0].toLowerCase().trim();
      
      // Validierung gängiger Dateitypen im Sovereign Studio V3 Stack
      const languages = [
        'typescript', 'ts', 'tsx', 
        'javascript', 'js', 'json', 
        'css', 'scss', 'html', 
        'xml', 'markdown', 'bash', 'yaml', 'yml', 'sql'
      ];
      
      // Prüfe, ob die erste Zeile eine Sprachkennung ist
      const isLanguageHeader = languages.some(lang => firstLine === lang || firstLine.startsWith(lang));
      
      if (isLanguageHeader) {
        // Entferne Sprach-Identifier-Zeile und gebe den Code-Rumpf zurück
        return lines.slice(1).join('\n').trim();
      } else if (lines.length > 1) {
        // Wenn kein expliziter Header gefunden wurde, aber Text vorhanden ist, gib das ganze Segment zurück
        return segment.trim();
      }
    }

    // Fallback: Extraktion des ersten verfügbaren Inhalts-Segments nach dem ersten Delimiter
    return segments[1] ? segments[1].trim() : response.trim();
  }
}