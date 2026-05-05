import { GoogleGenerativeAI } from "@google/generative-ai";

export class ReviewerAgent {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ 
      model: "gemini-1.5-pro",
      generationConfig: {
        temperature: 0.1,
        topP: 0.8,
        topK: 40,
      }
    });
  }

  /**
   * Führt eine tiefgreifende Qualitätsprüfung des Codes durch.
   * @param {string} code - Der zu prüfende Code.
   * @param {string} filePath - Pfad der Datei für kontextuelle Analyse.
   * @returns {Promise<Object>} Review-Ergebnis.
   */
  async review(code, filePath) {
    const staticAnalysis = this._performStaticCheck(code);
    
    if (!staticAnalysis.passed) {
      return {
        status: "REJECTED",
        score: 0,
        errors: staticAnalysis.errors,
        suggestions: ["Beheben Sie die kritischen Syntax-Verstöße gegen die Sovereign Studio Guidelines."]
      };
    }

    const prompt = `
      Analysiere den folgenden Code für das Sovereign Studio (Vite/Capacitor-6 Stack).
      
      DATEI: ${filePath}
      CODE:
      ${code}

      KRITERIEN:
      1. Architektur: Entspricht es dem Build-to-Deploy Workflow?
      2. Performance: Effiziente Nutzung von Gemini-Integrationen oder UI-Rendering?
      3. Sicherheit: Keine Hardcoded Secrets, korrekte Capacitor Permissions?
      4. Best Practices: Keine Verwendung von verbotenen Mustern (z.B. globale Regex-Ersetzung via replace(//g)).
      
      ANTWORTE IM JSON-FORMAT:
      {
        "status": "APPROVED" | "REVISIONS_REQUIRED",
        "score": 0-100,
        "criticalFlaws": [],
        "improvements": [],
        "isCapacitorCompatible": boolean
      }
    `;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      return JSON.parse(response.text().replace(/json|/g, "").trim());
    } catch (error) {
      return {
        status: "ERROR",
        message: "Review-Prozess fehlgeschlagen",
        details: error.message
      };
    }
  }

  /**
   * Statische Code-Analyse basierend auf Sovereign Studio Restriktionen.
   */
  _performStaticCheck(code) {
    const errors = [];

    // Verbot von replace(//g)
    if (code.includes(".replace(/") && code.includes("/g)")) {
      errors.push("Verbotenes Muster erkannt: 'replace(//g)' ist nicht erlaubt. Nutzen Sie 'replaceAll' oder spezifische Logik.");
    }

    // Prävention von TS1135 (häufig durch fehlerhafte Labels oder unvollständige Syntax)
    if (code.includes(" : ") && !code.includes("?") && !code.match(/case|default|get|set/)) {
      if (this._detectPotentialTS1135(code)) {
        errors.push("Potenzieller TS1135 Fehler: Verdächtige Doppelpunkt-Nutzung außerhalb von Ternary-Operatoren oder Objektliteralen.");
      }
    }

    // Leere JSX-Tags Suche (Keine <></> ohne Inhalt oder leere Divs ohne Zweck)
    if (code.match(/<>\s*<\/>/) || code.match(/<div>\s*<\/div>/)) {
      errors.push("Leere JSX-Tags oder Fragmente erkannt. Sovereign Studio verbietet redundante DOM-Nodes.");
    }

    return {
      passed: errors.length === 0,
      errors
    };
  }

  _detectPotentialTS1135(code) {
    // Einfache Heuristik zur Erkennung verwaister Labels oder Syntax-Fragmente
    const lines = code.split("\n");
    return lines.some(line => {
      const trimmed = line.trim();
      return /^[a-zA-Z0-9_]+:$/.test(trimmed) && !["default:", "case:"].some(k => trimmed.startsWith(k));
    });
  }

  /**
   * Validiert die Gradle-Patching Integrität für Android-Builds.
   */
  validateGradleConfig(configString) {
    const requiredPlugins = ["com.android.application", "com.google.gms.google-services"];
    const missing = requiredPlugins.filter(p => !configString.includes(p));
    
    return {
      valid: missing.length === 0,
      missingPlugins: missing
    };
  }
}