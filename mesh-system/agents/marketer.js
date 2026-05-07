import { GoogleGenerativeAI } from "@google/generative-ai";

/**
 * MarketerAgent
 * Spezialisiert auf die Extraktion technischer Errungenschaften aus dem Build-Prozess
 * und deren Transformation in hochgradig konvertierende Marketing-Assets für Sovereign Studio.
 */
export class MarketerAgent {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
    this.brandVoice = "Visionär, technisch präzise, souverän und zukunftsorientiert.";
    this.coreContext = "Sovereign Studio: AI-powered repository editor, Hybrid Vite/Capacitor-6 stack, Autonomous CI/CD (Ghost-Pilot).";
  }

  /**
   * Generiert Release-Ankündigungen basierend auf Commit-Daten und Build-Metriken.
   */
  async generateReleaseNotes(version, diffData, buildMetrics) {
    const prompt = `
      Handle als Lead Marketing Agent für Sovereign Studio.
      Erstelle eine Release-Ankündigung für Version ${version}.
      
      KONTEXT:
      ${this.coreContext}
      
      TECHNISCHE ÄNDERUNGEN:
      ${JSON.stringify(diffData)}
      
      PERFORMANCE-METRIKEN:
      ${JSON.stringify(buildMetrics)}
      
      AUFGABE:
      1. Formuliere eine packende Headline.
      2. Hebe die Evolution des "Build-to-Deploy"-Workflows hervor.
      3. Erkläre den Nutzen der neuen Features für Entwickler (Gemini-Integration, Gradle-Patching).
      4. Erstelle eine Sektion "Technischer Durchbruch" basierend auf den Build-Metriken.
      
      TONALITÄT:
      ${this.brandVoice}
      Format: Markdown.
    `;

    const result = await this.model.generateContent(prompt);
    return result.response.text();
  }

  /**
   * Erstellt plattformspezifischen Content für Web und Mobile (Android Play Store).
   */
  async generatePlatformMarketing(featureSet) {
    const prompt = `
      Erstelle Marketing-Inhalte für zwei Kanäle:
      1. Android Play Store (Kurzbeschreibung & Neuigkeiten) - Fokus auf Capacitor 6 & Native Performance.
      2. X/Twitter Thread für Entwickler - Fokus auf Ghost-Pilot CI/CD Automatisierung.
      
      FEATURES:
      ${JSON.stringify(featureSet)}
      
      REGELN:
      - Nutze keine generischen Phrasen.
      - Betone die Souveränität durch lokale KI-Orchestrierung.
      - Maximiere technische Glaubwürdigkeit.
    `;

    const result = await this.model.generateContent(prompt);
    return this._parseMultiChannelResponse(result.response.text());
  }

  /**
   * Analysiert Repository-Trends, um proaktive Feature-Ankündigungen zu planen.
   */
  async createAutonomousCampaign(repoState) {
    const prompt = `
      Analysiere den aktuellen Status des Repositories:
      ${JSON.stringify(repoState)}
      
      Entwirf eine "Autonomous Evolution" Kampagne, die beschreibt, wie Sovereign Studio 
      sich durch den Ghost-Pilot Zyklus selbst verbessert hat.
    `;

    const result = await this.model.generateContent(prompt);
    return result.response.text();
  }

  /**
   * Hilfsmethode zur Strukturierung von Multi-Channel Content.
   */
  _parseMultiChannelResponse(text) {
    // Vermeidung von komplexen Regex-Patterns gemäß Vorgabe
    const segments = text.split("---");
    return {
      playStore: segments[0] || "",
      socialMedia: segments[1] || "",
      raw: text
    };
  }
}

export default MarketerAgent;
