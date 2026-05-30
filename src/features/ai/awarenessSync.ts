import { geminiService } from "./geminiService";
import { callPuter, callGroq, callHuggingFace, callTogether, callOpenRouter, type ProviderType } from "./providerManager";

// Default model - updated to gemini-2.0-flash
const DEFAULT_MODEL = "gemini-2.0-flash";

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
 * 
 * FIXED LOGIC:
 * - No key OR any error → ALWAYS fallback to free providers
 * - Uses gemini-2.0-flash as default model
 * - OpenRouter is primary free fallback (has :free models)
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
  model: string = DEFAULT_MODEL,
  onProviderSwitch?: (from: ProviderType, to: ProviderType, error: string) => void
): Promise<AwarenessSyncResult> {
  // FIXED: If no API keys at all, throw immediately
  if (!geminiApiKey?.trim() && !fallbackProviders.groqKey?.trim() && !fallbackProviders.hfKey?.trim() && !fallbackProviders.togetherKey?.trim() && !fallbackProviders.openrouterKey?.trim()) {
    throw new Error("Kein API-Key konfiguriert. Bitte Gemini, Groq, HuggingFace, Together AI oder OpenRouter Key eintragen.");
  }

  const effectiveModel = model || DEFAULT_MODEL;

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

  let rawText: string = '';
  let usedProvider: ProviderType = 'gemini';

  // Try Gemini first if key provided
  if (geminiApiKey?.trim()) {
    try {
      rawText = await geminiService.generateText(geminiApiKey, prompt, {
        model: effectiveModel,
        temperature: 0.3,
        maxOutputTokens: 1024,
      });
      usedProvider = 'gemini';
    } catch (geminiError: any) {
      // FIXED: ANY error → fallback to free providers (no more retryable check)
      const errorMsg = geminiError?.message || String(geminiError);
      console.log(`🔄 Gemini failed: ${errorMsg} → falling back to free providers`);
      onProviderSwitch?.('gemini', 'groq', errorMsg);
      // Continue to fallback providers - don't throw
    }
  } else {
    // No key → immediate fallback
    console.log('🔄 No Gemini API key → using free providers');
    onProviderSwitch?.('gemini', 'puter', 'No API key provided');
  }

  // FIXED: If Gemini failed or no key, try fallback providers (ALL errors now trigger fallback)
  if (!rawText) {
    // Priority: Puter.js (KEYLESS!) → Groq → OpenRouter → HuggingFace → Together
    const providerOrder: Array<{ key: string; fn: (k: string, m: string, p: string, o: any) => Promise<any>; name: ProviderType; next: ProviderType; requiresKey: boolean }> = [
      { key: '', fn: callPuter, name: 'puter', next: 'groq', requiresKey: false },  // KEYLESS!
      { key: fallbackProviders.groqKey || '', fn: callGroq, name: 'groq', next: 'openrouter', requiresKey: true },
      { key: fallbackProviders.openrouterKey || '', fn: callOpenRouter, name: 'openrouter', next: 'huggingface', requiresKey: true },
      { key: fallbackProviders.hfKey || '', fn: callHuggingFace, name: 'huggingface', next: 'together', requiresKey: true },
      { key: fallbackProviders.togetherKey || '', fn: callTogether, name: 'together', next: 'puter', requiresKey: true },
    ];

    for (const provider of providerOrder) {
      // Skip if API key is required but not provided
      if (provider.requiresKey && !provider.key?.trim()) continue;
      
      try {
        const response = await provider.fn(provider.key || '', effectiveModel, prompt, {
          temperature: 0.3,
          maxOutputTokens: 1024,
        });
        rawText = response.text;
        usedProvider = provider.name;
        console.log(`✅ Success with ${provider.name}`);
        break;
      } catch (err: any) {
        const errMsg = err?.message || String(err);
        console.log(`❌ ${provider.name} failed: ${errMsg}`);
        onProviderSwitch?.(provider.name, provider.next, errMsg);
        // Continue to next provider
      }
    }
  }

  if (!rawText) {
    throw new Error("Alle AI-Provider sind fehlgeschlagen. Bitte API-Keys für Puter.js (kein Key nötig!), Groq, HuggingFace, Together AI oder OpenRouter eintragen.");
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
