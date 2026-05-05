import { diffLines, Change } from 'diff';

/**
 * Sovereign Studio V3 - Patch Engine
 * Transformiert LLM-Generierungen in valide Unified Diff Patches für die Repository-Synchronisation.
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
   */
  public generatePatch(filename: string, originalCode: string, modifiedCode: string): PatchResult {
    try {
      const changes = diffLines(originalCode, modifiedCode);
      
      if (!this.hasChanges(changes)) {
        return { success: true, patch: '' };
      }

      const patch = this.buildUnifiedDiff(filename, changes);
      
      return {
        success: true,
        patch
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
   * Prüft ob tatsächliche Änderungen vorliegen.
   */
  private hasChanges(changes: Change[]): boolean {
    return changes.some(change => change.added || change.removed);
  }

  /**
   * Konstruiert das Unified Diff Format gemäß Git Standards.
   */
  private buildUnifiedDiff(filename: string, changes: Change[]): string {
    const timestamp = new Date().toISOString();
    const header = [
      `--- a/${filename}\t${timestamp}`,
      `+++ b/${filename}\t${timestamp}`
    ];

    let oldLineCounter = 1;
    let newLineCounter = 1;
    const hunks: string[] = [];

    // Zusammenfassung der Changes in Hunks für effiziente Datei-Operationen in Capacitor/Vite
    let currentHunkLines: string[] = [];
    let hunkOldStart = 0;
    let hunkNewStart = 0;
    let hunkOldCount = 0;
    let hunkNewCount = 0;

    changes.forEach((change) => {
      const lines = this.splitIntoLines(change.value);

      if (change.added || change.removed) {
        if (hunkOldStart === 0) {
          hunkOldStart = oldLineCounter;
          hunkNewStart = newLineCounter;
        }

        lines.forEach(line => {
          if (change.added) {
            currentHunkLines.push(`+${line}`);
            hunkNewCount++;
            newLineCounter++;
          } else {
            currentHunkLines.push(`-${line}`);
            hunkOldCount++;
            oldLineCounter++;
          }
        });
      } else {
        // Kontext-Zeilen oder Hunk-Abschluss
        if (hunkOldStart !== 0) {
          // Hinzufügen von Kontext nach einer Änderung (limitieren auf contextLines)
          const postContext = lines.slice(0, this.contextLines);
          postContext.forEach(line => {
            currentHunkLines.push(` ${line}`);
            hunkOldCount++;
            hunkNewCount++;
          });

          const hunkHeader = `@@ -${hunkOldStart},${hunkOldCount} +${hunkNewStart},${hunkNewCount} @@`;
          hunks.push(hunkHeader, ...currentHunkLines);

          // Reset für nächsten Hunk
          currentHunkLines = [];
          hunkOldStart = 0;
          hunkNewStart = 0;
          hunkOldCount = 0;
          hunkNewCount = 0;
        }
        
        oldLineCounter += lines.length;
        newLineCounter += lines.length;
      }
    });

    // Falls noch ein offener Hunk existiert
    if (currentHunkLines.length > 0) {
      const hunkHeader = `@@ -${hunkOldStart},${hunkOldCount} +${hunkNewStart},${hunkNewCount} @@`;
      hunks.push(hunkHeader, ...currentHunkLines);
    }

    return [...header, ...hunks].join('\n') + '\n';
  }

  /**
   * Hilfsmethode zum Zeilen-Splitting ohne Regex-Globale (Safe-Pattern).
   */
  private splitIntoLines(text: string): string[] {
    const lines = text.split('\n');
    // Entferne leere Endzeile durch split
    if (lines.length > 0 && lines[lines.length - 1] === '') {
      lines.pop();
    }
    return lines;
  }

  /**
   * Extrahiert Code-Blöcke aus LLM-Antworten (Markdown-Sicher).
   */
  public extractCodeFromResponse(response: string): string {
    const codeBlockStart = '';
    if (!response.includes(codeBlockStart)) return response.trim();

    const parts = response.split(codeBlockStart);
    for (const part of parts) {
      // Prüft auf gängige Sprachen im Sovereign Studio Stack
      if (part.startsWith('typescript') || part.startsWith('ts') || part.startsWith('tsx') || part.startsWith('javascript') || part.startsWith('js')) {
        const lines = part.split('\n');
        lines.shift(); // Sprach-Identifier entfernen
        return lines.join('\n').trim();
      }
    }
    
    // Fallback auf den ersten Block wenn kein Identifier gefunden wurde
    if (parts.length >= 2) {
      return parts[1].trim();
    }

    return response.trim();
  }
}