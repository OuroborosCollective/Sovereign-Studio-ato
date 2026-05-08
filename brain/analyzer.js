/**
 * Sovereign Studio V3 - Brain Signal Analyzer
 * Converts GitHub issues into actionable metadata for LLM-driven workflows.
 */

export class SignalAnalyzer {
  /**
   * Processes raw GitHub issue data into structured signals.
   * @param {Object} issue - The GitHub issue payload.
   * @returns {Object} Actionable metadata for the Sovereign Studio engine.
   */
  static analyze(issue) {
    const title = issue.title || "";
    const body = issue.body || "";
    const labels = (issue.labels || []).map(l => (typeof l === "string" ? l : l.name).toLowerCase());

    const combinedText = `${title} ${body}`.toLowerCase();

    return {
      id: issue.number || issue.id,
      timestamp: new Date().toISOString(),
      intent: this.determineIntent(labels, combinedText),
      priority: this.calculatePriority(labels, combinedText),
      domain: this.mapToDomain(labels, combinedText),
      context: {
        isNativeRequirement: this.detectNativeRequirement(combinedText),
        affectedPlatforms: this.identifyPlatforms(combinedText),
        requiresBiometrics: combinedText.includes("biometric") || combinedText.includes("faceid") || combinedText.includes("fingerprint"),
        requiresPush: combinedText.includes("notification") || combinedText.includes("fcm") || combinedText.includes("apns")
      },
      rawSummary: {
        title,
        labelCount: labels.length,
        hasDescription: body.length > 0
      }
    };
  }

  /**
   * Identifies the core intent of the issue.
   */
  static determineIntent(labels, text) {
    if (labels.includes("bug") || text.includes("fix") || text.includes("error")) return "REPAIR";
    if (labels.includes("enhancement") || labels.includes("feature") || text.includes("implement")) return "EVOLVE";
    if (labels.includes("refactor") || text.includes("cleanup")) return "REFACTOR";
    if (labels.includes("documentation") || text.includes("docs")) return "DOCUMENT";
    return "ANALYZE";
  }

  /**
   * Calculates priority based on signals.
   */
  static calculatePriority(labels, text) {
    if (labels.includes("critical") || labels.includes("p0") || text.includes("urgent") || text.includes("crash")) return "CRITICAL";
    if (labels.includes("high") || labels.includes("p1")) return "HIGH";
    if (labels.includes("low") || text.includes("minor")) return "LOW";
    return "MEDIUM";
  }

  /**
   * Maps the issue to specific architectural domains of Sovereign Studio V3.
   */
  static mapToDomain(labels, text) {
    if (text.includes("capacitor") || text.includes("android") || text.includes("ios") || text.includes("native")) return "NATIVE_BRIDGE";
    if (text.includes("vite") || text.includes("ui") || text.includes("css") || text.includes("tailwind")) return "FRONTEND_VITE";
    if (text.includes("gemini") || text.includes("llm") || text.includes("ai")) return "AI_CORE";
    if (text.includes("ci") || text.includes("pipeline") || text.includes("deployment")) return "DEVOPS_AUTOMATION";
    return "GENERAL_CONTEXT";
  }

  /**
   * Detects if the signal requires Capacitor native API access.
   */
  static detectNativeRequirement(text) {
    const nativeKeywords = ["camera", "geolocation", "filesystem", "device", "network", "biometry", "haptics"];
    return nativeKeywords.some(keyword => text.includes(keyword));
  }

  /**
   * Identifies targeted platforms within the hybrid architecture.
   */
  static identifyPlatforms(text) {
    const platforms = [];
    if (text.includes("ios")) platforms.push("ios");
    if (text.includes("android")) platforms.push("android");
    if (text.includes("web") || text.includes("browser")) platforms.push("web");
    return platforms.length > 0 ? platforms : ["cross-platform"];
  }

  /**
   * Sanitizes text without using forbidden global regex patterns.
   * Utilizes split/join for safety in the Sovereign environment.
   * @param {string} input 
   */
  static sanitizeSignalText(input) {
    if (!input) return "";
    return input.split("\r").join(" ").split("\n").join(" ").trim();
  }
}