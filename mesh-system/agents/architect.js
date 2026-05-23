import { GoogleGenerativeAI } from "@google/generative-ai";

/**
 * ArchitectAgent
 * Verantwortlich für die technologische Planung und Dekonstruktion von Anforderungen
 * in ausführbare Implementierungsschritte innerhalb des NOCode Studio Stacks.
 */
export class ArchitectAgent {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
  }

  /**
   * Erstellt einen detaillierten Implementierungsplan basierend auf einem Issue.
   * @param {Object} issue - Das zu planende Feature oder Problem.
   * @param {Object} context - Aktueller Repository-Kontext und Dateistruktur.
   */
  async planFeature(issue, context) {
    const systemPrompt = `
      Du bist der NOCode Studio ArchitectAgent. Deine Aufgabe ist es, präzise technische Blueprints
      für einen hybriden Vite + Capacitor 6 Stack zu erstellen.
      
      ARCHITEKTUR-FOKUS:
      - Frontend: React + Vite + Tailwind CSS.
      - Native: Capacitor 6 (Gradle/Java für Android).
      - AI: Gemini Integration (Google Generative AI SDK).
      - Workflow: Build-to-Deploy, CI/CD Ghost-Pilot.

      AUFGABE:
      Analysiere das Issue und erstelle einen Plan, der folgende Punkte enthält:
      1. Betroffene Dateien (Existing & New).
      2. Erforderliche API-Änderungen oder neue Hooks.
      3. UI/UX Komponenten-Struktur.
      4. Native Capacitor-Plugins (falls erforderlich).
      5. Sicherheits- und Performance-Überlegungen.
    `;

    const userPrompt = `
      ISSUE: ${issue.title}
      BESCHREIBUNG: ${issue.description}
      KONTEXT: ${JSON.stringify(context.fileTree)}
    `;

    try {
      const result = await this.model.generateContent([systemPrompt, userPrompt]);
      const response = await result.response;
      return this.parseBlueprint(response.text());
    } catch (error) {
      console.error("ArchitectAgent Planning Error:", error);
      throw new Error("Fehler bei der Architektur-Planung.");
    }
  }

  /**
   * Formatiert die LLM-Antwort in ein strukturiertes JSON-Format für den DeveloperAgent.
   */
  parseBlueprint(rawText) {
    // Extrahiert Informationen aus dem Markdown des LLMs
    return {
      timestamp: new Date().toISOString(),
      blueprint: rawText,
      strategy: "hybrid-native-evolution",
      recommendedChanges: this.extractFileList(rawText)
    };
  }

  extractFileList(text) {
    const fileRegex = /`([^`]+\.(js|jsx|ts|tsx|gradle|json|xml))`/;
    const matches = text.match(new RegExp(fileRegex.source, 'm'));
    return matches ? Array.from(new Set(matches)) : [];
  }
}

export default ArchitectAgent;