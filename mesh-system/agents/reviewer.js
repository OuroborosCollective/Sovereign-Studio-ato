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
   * Führt eine tiefgreifende Qualitätsprüfung des Codes und Inhalts durch.
   * @param {string} content - Der zu prüfende Code oder Text.
   * @param {string} filePath - Pfad der Datei für kontextuelle Analyse.
   * @returns {Promise<Object>} Review-Ergebnis.
   */
  async review(content, filePath) {
    // 1. Statische Code-Analyse
    const staticAnalysis = this._performStaticCheck(content);
    
    // 2. Marketing & Security Sanitization Pipeline
    const sanitization = this.sanitizeMarketingContent(content);

    if (!staticAnalysis.passed) {
      return {
        status: "REJECTED",
        score: 0,
        errors: staticAnalysis.errors,
        suggestions: ["Beheben Sie die kritischen Syntax-Verstöße gegen die NOCode Studio Guidelines."]
      };
    }

    if (!sanitization.isClean && (filePath.endsWith('.md') || filePath.includes('marketing') || filePath.includes('docs'))) {
      return {
        status: "REVISIONS_REQUIRED",
        score: 40,
        errors: sanitization.detectedIssues,
        sanitizedVersion: sanitization.sanitizedContent,
        suggestions: ["Interne Pfade, Secrets oder falsches Branding in Marketing-Materialien erkannt."]
      };
    }

    const prompt = `
      Analysiere den folgenden Dateiinhalt für das NOCode Studio (Vite/Capacitor-6 Stack).
      
      DATEI: ${filePath}
      INHALT:
      ${content}

      KRITERIEN:
      1. Architektur: Entspricht es dem Build-to-Deploy Workflow?
      2. Performance: Effiziente Nutzung von Gemini-Integrationen oder UI-Rendering?
      3. Sicherheit: Keine Hardcoded Secrets, korrekte Capacitor Permissions?
      4. Branding: Wird "NOCode Studio" korrekt und exklusiv verwendet?
      5. Best Practices: Keine Verwendung von verbotenen Mustern (z.B. globale Regex-Ersetzung via replace(//g)).
      
      ANTWORTE IM JSON-FORMAT:
      {
        "status": "APPROVED" | "REVISIONS_REQUIRED",
        "score": 0-100,
        "criticalFlaws": [],
        "improvements": [],
        "isCapacitorCompatible": boolean,
        "brandingCheck": "PASSED" | "FAILED"
      }
    `;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const jsonResponse = JSON.parse(response.text().replace(/json|/g, "").trim());
      
      // Merge sanitization results if applicable
      if (!sanitization.isClean) {
        jsonResponse.status = "REVISIONS_REQUIRED";
        jsonResponse.criticalFlaws.push(...sanitization.detectedIssues);
      }

      return jsonResponse;
    } catch (error) {
      return {
        status: "ERROR",
        message: "Review-Prozess fehlgeschlagen",
        details: error.message
      };
    }
  }

  /**
   * Scannt und bereinigt Marketing-Texte von internen Informationen.
   */
  sanitizeMarketingContent(text) {
    const issues = [];
    let sanitized = text;

    // 1. Interne GitHub-Links (Deep-Links in Repos)
    const githubRegex = /https:\/\/github\.com\/[^\s/]+\/[^\s/]+\/(blob|tree)\/[^\s]+/g;
    if (githubRegex.test(sanitized)) {
      issues.push("Interne GitHub-Struktur-Links erkannt.");
      sanitized = sanitized.replace(githubRegex, "[OFFICIAL_REPOSITORY_ROOT]");
    }

    // 2. Lokale Dateipfade (Unix & Windows Heuristik)
    const pathRegex = /(\/[a-zA-Z0-9._\-/]+|[A-Z]:\\[a-zA-Z0-9._\-\\]+)/g;
    sanitized = sanitized.replace(pathRegex, (match) => {
      if (match.includes('/') && match.split('/').length > 2 && !match.startsWith('http')) {
        issues.push(`Interner Pfad erkannt: ${match}`);
        return "[INTERNAL_FILE_PATH]";
      }
      return match;
    });

    // 3. .env Variablen & Secrets
    const envRegex = /(VITE_[A-Z0-9_]+|process\.env\.[A-Z0-9_]+|[A-Z0-9_]{20,})/g;
    if (envRegex.test(sanitized)) {
      issues.push("Potenzielle Environment-Variablen oder Secrets erkannt.");
      sanitized = sanitized.replace(envRegex, "[REDACTED_CONFIG]");
    }

    // 4. Lokale URLs (localhost/IPs)
    const localUrlRegex = /http:\/\/(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?/g;
    if (localUrlRegex.test(sanitized)) {
      issues.push("Lokale Entwicklungs-URLs gefunden.");
      sanitized = sanitized.replace(localUrlRegex, "https://sovereign-studio.app");
    }

    // 5. Branding Enforcement (Enforce "NOCode Studio")
    const forbiddenBrands = /Sovereign Studio V3|Sovereign Studio|Ghost Pilot/gi;
    if (forbiddenBrands.test(sanitized)) {
      issues.push("Falsches Branding erkannt. Begriffe wie Sovereign Studio oder Ghost Pilot sind verboten.");
      sanitized = sanitized.replace(forbiddenBrands, "NOCode Studio");
    }

    return {
      isClean: issues.length === 0,
      sanitizedContent: sanitized,
      detectedIssues: issues
    };
  }

  /**
   * Statische Code-Analyse basierend auf NOCode Studio Restriktionen.
   */
  _performStaticCheck(code) {
    const errors = [];

    // Verbot von replace(//g) -> Muss replaceAll sein
    if (code.includes(".replace(/") && code.includes("/g)")) {
      errors.push("Verbotenes Muster: 'replace(//g)' ist instabil. Nutzen Sie 'replaceAll' oder String-Literale.");
    }

    // Prävention von TS1135
    if (code.includes(" : ") && !code.includes("?") && !code.match(/case|default|get|set/)) {
      if (this._detectPotentialTS1135(code)) {
        errors.push("Potenzieller TS1135 Fehler: Verdächtige Doppelpunkt-Nutzung (Label-Syntax-Fehler).");
      }
    }

    // Leere JSX-Tags Suche
    if (code.match(/<>\s*<\/>/) || code.match(/<div>\s*<\/div>/)) {
      errors.push("Leere JSX-Tags oder Fragmente ohne Inhalt erkannt.");
    }

    return {
      passed: errors.length === 0,
      errors
    };
  }

  _detectPotentialTS1135(code) {
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
