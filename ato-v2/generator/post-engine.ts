import { GoogleGenerativeAI } from "@google/generative-ai";

export interface PostInput {
  version: string;
  features: string[];
  fixes: string[];
  breakingChanges: string[];
  context?: string;
}

export interface GeneratedContent {
  releaseNotes: string;
  socialMedia: {
    linkedin: string;
    twitter: string;
  };
  internalDocs: string;
}

export class PostEngine {
  private genAI: GoogleGenerativeAI;
  private model: any;

  constructor(apiKey: string) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
  }

  public async generateAll(input: PostInput): Promise<GeneratedContent> {
    const prompt = this.buildPrompt(input);
    const result = await this.model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    return this.parseResponse(text);
  }

  private buildPrompt(input: PostInput): string {
    return `
      Act as the Sovereign Studio V3 Release Manager. 
      Generate automated updates based on the following version data:
      Version: ${input.version}
      Features: ${input.features.join(", ")}
      Fixes: ${input.fixes.join(", ")}
      Breaking Changes: ${input.breakingChanges.join(", ")}
      Context: ${input.context || "Standard update for hybrid mobile-first architecture"}

      Requirements:
      1. Release Notes: Technical but accessible, Markdown format.
      2. Social Media: 
         - LinkedIn: Professional, industry-leading tone, include hashtags.
         - Twitter/X: Concise, punchy, mobile-first focus.
      3. Internal Docs: Detailed technical summary for the engineering team.

      Format the output as a JSON object with keys: releaseNotes, socialMedia (with subkeys linkedin, twitter), internalDocs.
      Return ONLY valid JSON.
    `;
  }

  private parseResponse(text: string): GeneratedContent {
    try {
      // Extracting JSON by identifying the first and last curly braces to avoid markdown noise
      const firstBrace = text.indexOf("{");
      const lastBrace = text.lastIndexOf("}") + 1;
      
      if (firstBrace === -1 || lastBrace === 0) {
        throw new Error("No JSON object found in response");
      }

      const cleaned = text.substring(firstBrace, lastBrace);
      return JSON.parse(cleaned) as GeneratedContent;
    } catch (error) {
      console.error("[PostEngine] Parsing failed:", error);
      return {
        releaseNotes: "Error parsing release notes.",
        socialMedia: { linkedin: "", twitter: "" },
        internalDocs: "Error parsing internal documentation."
      };
    }
  }

  public async generateChangelogFragment(input: PostInput): Promise<string> {
    const date = new Date().toISOString().split("T")[0];
    let fragment = `## [${input.version}] - ${date}\n\n`;

    if (input.features.length > 0) {
      fragment += `### Added\n${input.features.map(f => `- ${f}`).join("\n")}\n\n`;
    }

    if (input.fixes.length > 0) {
      fragment += `### Fixed\n${input.fixes.map(f => `- ${f}`).join("\n")}\n\n`;
    }

    if (input.breakingChanges.length > 0) {
      fragment += `### BREAKING CHANGES\n${input.breakingChanges.map(b => `- ${b}`).join("\n")}\n\n`;
    }

    return fragment;
  }

  /**
   * Helper to ensure WHATWG URL compliance for release links
   * Replaces deprecated url.parse() logic as per DEP0169
   */
  public constructReleaseUrl(baseUrl: string, version: string): string {
    try {
      const url = new URL(`/releases/tag/v${version}`, baseUrl);
      return url.toString();
    } catch (e) {
      return "";
    }
  }
}

export const postEngineFactory = (apiKey: string) => new PostEngine(apiKey);