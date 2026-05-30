import { geminiService } from "./geminiService";
import { callGroq, callHuggingFace, callTogether, type ProviderType } from "./providerManager";

export interface RepoFile {
  path: string;
  type: "blob" | "tree";
  size?: number;
}

export interface AwarenessSyncResult {
  summary: string;
  technologies: string[];
  structure: string;
  suggestions: string[];
  rawText: string;
}

/**
 * Runs awareness sync with automatic provider fallback
 * Tries Gemini first, then falls back to free providers if needed
 */
export async function runAwarenessSync(
  geminiApiKey: string,
  repoFiles: RepoFile[],
  repoUrl: string,
  fallbackProviders: {
    groqKey?: string;
    hfKey?: string;
    togetherKey?: string;
    openrouterKey?: string;
  } = {},
  model: string = "gemini-1.5-flash",
  onProviderSwitch?: (from: ProviderType, to: ProviderType, error: string) => void
): Promise<AwarenessSyncResult> {
  if (!geminiApiKey || !geminiApiKey.trim()) {
    if (!fallbackProviders.groqKey && !fallbackProviders.hfKey && !fallbackProviders.togetherKey && !fallbackProviders.openrouterKey) {
      throw new Error("Kein API-Key konfiguriert. Bitte Gemini, Groq, HuggingFace oder Together AI Key eintragen.");
    }
    // Will try fallback providers
  }

  const filePaths = repoFiles
    .filter((f) => f.type === "blob")
    .slice(0, 80)
    .map((f) => f.path)
    .join("\n");

  const prompt = `Du bist ein erfahrener Software-Architekt. Analysiere das folgende GitHub-Repository und gib eine strukturierte Übersicht zurück.

Repository: ${repoUrl}

Dateiliste (Auszug):
${filePaths}

Antworte auf Deutsch in diesem exakten Format:

ZUSAMMENFASSUNG:
[2-3 Sätze was dieses Projekt ist und macht]

TECHNOLOGIEN:
[Komma-getrennte Liste der erkannten Technologien, Frameworks, Tools]

STRUKTUR:
[Kurze Beschreibung der Ordnerstruktur und Architektur in 2-3 Sätzen]

VERBESSERUNGSVORSCHLÄGE:
- [Vorschlag 1]
- [Vorschlag 2]
- [Vorschlag 3]`;

  let rawText: string;
  let usedProvider: ProviderType = 'gemini';

  // Try Gemini first
  if (geminiApiKey?.trim()) {
    try {
      rawText = await geminiService.generateText(geminiApiKey, prompt, {
        model,
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      usedProvider = 'gemini';
    } catch (geminiError: any) {
      const errorMsg = geminiError?.message || String(geminiError);
      const isRetryable = 
        errorMsg.includes('429') || 
        errorMsg.includes('quota') || 
        errorMsg.includes('RESOURCE_EXHAUSTED') ||
        errorMsg.includes('authentication') ||
        errorMsg.includes('api key') ||
        geminiError?.status === 401 || 
        geminiError?.status === 403;

      if (isRetryable) {
        onProviderSwitch?.('gemini', 'groq', errorMsg);
      } else {
        throw geminiError;
      }
    }
  }

  // If Gemini failed or no key, try fallback providers
  if (!rawText) {
    // Try Groq
    if (fallbackProviders.groqKey?.trim()) {
      try {
        const response = await callGroq(fallbackProviders.groqKey, model, prompt, {
          temperature: 0.3,
          maxOutputTokens: 1024,
        });
        rawText = response.text;
        usedProvider = 'groq';
      } catch (err: any) {
        onProviderSwitch?.('groq', 'huggingface', err?.message || String(err));
        // Continue to next provider
      }
    }

    // Try HuggingFace
    if (!rawText && fallbackProviders.hfKey?.trim()) {
      try {
        const response = await callHuggingFace(fallbackProviders.hfKey, model, prompt, {
          temperature: 0.3,
          maxOutputTokens: 1024,
        });
        rawText = response.text;
        usedProvider = 'huggingface';
      } catch (err: any) {
        onProviderSwitch?.('huggingface', 'together', err?.message || String(err));
      }
    }

    // Try Together AI
    if (!rawText && fallbackProviders.togetherKey?.trim()) {
      try {
        const response = await callTogether(fallbackProviders.togetherKey, model, prompt, {
          temperature: 0.3,
          maxOutputTokens: 1024,
        });
        rawText = response.text;
        usedProvider = 'together';
      } catch (err: any) {
        onProviderSwitch?.('together', 'openrouter', err?.message || String(err));
      }
    }
  }

  if (!rawText) {
    throw new Error("Alle AI-Provider sind fehlgeschlagen. Bitte API-Keys für Gemini, Groq, HuggingFace oder Together AI eintragen.");
  }

  const summary = extractSection(rawText, "ZUSAMMENFASSUNG");
  const techLine = extractSection(rawText, "TECHNOLOGIEN");
  const structure = extractSection(rawText, "STRUKTUR");
  const suggestionsText = extractSection(rawText, "VERBESSERUNGSVORSCHLÄGE");

  const technologies = techLine
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);

  const suggestions = suggestionsText
    .split("\n")
    .map((s) => s.replace(/^[-•*]\s*/, "").trim())
    .filter(Boolean);

  return { 
    summary, 
    technologies, 
    structure, 
    suggestions, 
    rawText
  };
}

function extractSection(text: string, heading: string): string {
  const regex = new RegExp(`${heading}:\\s*([\\s\\S]*?)(?=\\n[A-ZÄÖÜ]+:|$)`, "i");
  const match = text.match(regex);
  return match ? match[1].trim() : "";
}
