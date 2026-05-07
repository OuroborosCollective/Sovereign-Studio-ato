import { GoogleGenerativeAI, GenerativeModel } from "@google/generative-ai";

export type SignalCategory = "UI" | "Logic" | "Infrastructure" | "Security" | "Performance" | "Unknown";
export type SignalPriority = "P0" | "P1" | "P2" | "P3";

export interface RawSignal {
  id: string;
  source: string;
  content: string;
  timestamp: number;
  metadata?: Record<string, any>;
}

export interface AnalyzedSignal {
  id: string;
  category: SignalCategory;
  priority: SignalPriority;
  isDuplicate: boolean;
  duplicateOf?: string;
  summary: string;
  tags: string[];
  actionRequired: boolean;
  confidence: number;
  normalizedSource?: string;
}

export class BrainAnalyzer {
  private model: GenerativeModel;

  constructor(apiKey: string) {
    const genAI = new GoogleGenerativeAI(apiKey);
    this.model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
  }

  /**
   * Normalizes the signal source using the WHATWG URL API to prevent 
   * security risks and DEP0169 deprecation issues.
   */
  private normalizeSource(source: string): string {
    try {
      // Transitioned from legacy url.parse() to WHATWG URL API
      const url = new URL(source);
      return url.href;
    } catch {
      return source;
    }
  }

  async analyze(signal: RawSignal, history: AnalyzedSignal[] = []): Promise<AnalyzedSignal> {
    const normalizedSource = this.normalizeSource(signal.source);
    
    const contextPrompt = history.length > 0 
      ? `Existing signals for deduplication check: ${JSON.stringify(history.slice(-10).map(h => ({ id: h.id, summary: h.summary })))}`
      : "";

    const prompt = `
      Analyze the following signal for Sovereign Studio V3 Repository Assistant.
      
      Signal Content: "${signal.content}"
      Source: "${normalizedSource}"
      ${contextPrompt}

      Task:
      1. Categorize: UI, Logic, Infrastructure, Security, Performance.
      2. Prioritize: P0 (Critical/Crash), P1 (Feature Block), P2 (Task), P3 (Minor).
      3. Deduplicate: Compare with existing signals.
      4. Summarize: Brief technical description.

      Respond ONLY in valid JSON format:
      {
        "category": "SignalCategory",
        "priority": "SignalPriority",
        "isDuplicate": boolean,
        "duplicateOf": "string | undefined",
        "summary": "string",
        "tags": ["string"],
        "actionRequired": boolean,
        "confidence": number
      }
    `;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const text = response.text();
      
      // Extracting JSON blocks safely without using illegal regex patterns
      const jsonStart = text.indexOf("{");
      const jsonEnd = text.lastIndexOf("}") + 1;
      
      if (jsonStart === -1 || jsonEnd === 0) {
        throw new Error("Invalid LLM response format");
      }

      const cleanJson = text.substring(jsonStart, jsonEnd);
      const analysis = JSON.parse(cleanJson);

      return {
        id: signal.id,
        category: analysis.category || "Unknown",
        priority: analysis.priority || "P3",
        isDuplicate: !!analysis.isDuplicate,
        duplicateOf: analysis.duplicateOf,
        summary: analysis.summary || "No summary provided.",
        tags: analysis.tags || [],
        actionRequired: !!analysis.actionRequired,
        confidence: analysis.confidence || 0,
        normalizedSource
      };
    } catch (error) {
      console.error("BrainAnalyzer Error:", error);
      return this.getDefaultAnalysis(signal, normalizedSource);
    }
  }

  private getDefaultAnalysis(signal: RawSignal, normalizedSource?: string): AnalyzedSignal {
    return {
      id: signal.id,
      category: "Unknown",
      priority: "P3",
      isDuplicate: false,
      summary: "Failed to analyze signal content.",
      tags: [],
      actionRequired: false,
      confidence: 0,
      normalizedSource: normalizedSource || signal.source
    };
  }
}