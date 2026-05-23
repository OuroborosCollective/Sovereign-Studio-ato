import { GoogleGenerativeAI } from "@google/generative-ai";
import fs from "fs/promises";
import path from "path";

/**
 * CoderAgent
 * Kern-Komponente der NOCode Studio Engine zur Umsetzung architektonischer Blueprints
 * in produktionsreifen Code für Web (Vite) und Android (Capacitor/Gradle).
 */
export class CoderAgent {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
  }

  /**
   * Generiert Code basierend auf einem Architektur-Plan.
   * @param {Object} plan - Der vom ArchitectAgent erstellte Plan.
   * @returns {Promise<Array>} - Liste der generierten Dateien und deren Inhalt.
   */
  async executePlan(plan) {
    const results = [];
    
    for (const task of plan.tasks) {
      const prompt = this._buildGenerationPrompt(task, plan.context);
      const response = await this.model.generateContent(prompt);
      const code = this._extractCode(response.response.text());
      
      results.push({
        filePath: task.filePath,
        content: code,
        action: task.action // 'create', 'update', 'patch'
      });
    }

    return results;
  }

  /**
   * Spezifischer Mechanismus für Gradle-Patching (Android-Native).
   */
  async patchNativeGradle(gradleContent, changes) {
    const prompt = `
      Patsche die folgende build.gradle Datei für NOCode Studio (Capacitor 6 Stack).
      Änderungen: ${JSON.stringify(changes)}
      
      Original-Inhalt:
      ${gradleContent}
      
      Gib nur den vollständigen, validen Gradle-Code zurück.
    `;
    
    const result = await this.model.generateContent(prompt);
    return this._extractCode(result.response.text());
  }

  _buildGenerationPrompt(task, context) {
    return `
      Du bist der NOCode Studio Design-Coder.
      Architektur-Kontext: ${context}
      
      Aufgabe: ${task.description}
      Zieldatei: ${task.filePath}
      Frameworks: Vite, React, Tailwind CSS, Capacitor 6.
      
      REGELN:
      - Nutze niemals leere JSX-Tags (<></> ohne Inhalt).
      - Vermeide TS1135 (keine unvollständigen Kommentare oder Syntaxfehler).
      - Implementiere robustes Error Handling.
      - Integriere Gemini-Hooks, falls im Plan vorgesehen.
      
      Liefere NUR den reinen Code für diese Datei.
    `;
  }

  /**
   * Extrahiert Code-Blöcke aus der LLM-Antwort ohne verbotene Regex-Muster.
   */
  _extractCode(text) {
    const lines = text.split("\n");
    const codeLines = [];
    let inBlock = false;

    for (const line of lines) {
      if (line.startsWith("")) {
        inBlock = !inBlock;
        continue;
      }
      if (inBlock) {
        codeLines.push(line);
      }
    }

    if (codeLines.length === 0) return text.trim();
    return codeLines.join("\n").trim();
  }

  /**
   * Schreibt die generierten Daten in das Repository-Dateisystem.
   */
  async commitToFilesystem(baseDir, files) {
    for (const file of files) {
      const fullPath = path.join(baseDir, file.filePath);
      const dir = path.dirname(fullPath);
      
      await fs.mkdir(dir, { recursive: true });
      await fs.writeFile(fullPath, file.content, "utf8");
    }
  }
}

export default CoderAgent;