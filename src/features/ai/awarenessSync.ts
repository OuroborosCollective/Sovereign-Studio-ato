import { geminiService } from "./geminiService";

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

export async function runAwarenessSync(
  geminiApiKey: string,
  repoFiles: RepoFile[],
  repoUrl: string,
  model: string = "gemini-1.5-flash"
): Promise<AwarenessSyncResult> {
  if (!geminiApiKey || !geminiApiKey.trim()) {
    throw new Error(
      "Kein Gemini API-Key angegeben. Bitte einen gültigen Key eintragen und erneut versuchen."
    );
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

  const rawText = await geminiService.generateText(geminiApiKey, prompt, {
    model,
    temperature: 0.3,
    maxOutputTokens: 1024,
  });

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

  return { summary, technologies, structure, suggestions, rawText };
}

function extractSection(text: string, heading: string): string {
  const regex = new RegExp(`${heading}:\\s*([\\s\\S]*?)(?=\\n[A-ZÄÖÜ]+:|$)`, "i");
  const match = text.match(regex);
  return match ? match[1].trim() : "";
}
