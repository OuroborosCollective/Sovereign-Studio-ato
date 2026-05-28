import { GoogleGenerativeAI } from "@google/generative-ai";
import fs from "fs";
import path from "path";

/**
 * PostGenerator - Content Engine for Launch Marketing
 * Target Platforms: Product Hunt, Reddit, Indie Hackers
 */
class PostGenerator {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
  }

  async generatePosts(projectDetails) {
    const { name, description, features, targetAudience, usp } = projectDetails;

    const prompt = `
      You are an expert growth marketer for developer tools. 
      Generate highly engaging launch content for "${name}".
      Product Context: ${description}
      Key Features: ${features.join(", ")}
      USP: ${usp}
      Target Audience: ${targetAudience}

      Create content for exactly these three platforms:
      1. Product Hunt: Tagline (max 60 chars), Description (max 260 chars), and a First Maker Comment (passionate, story-driven).
      2. Reddit: One post for r/startups (educational/feedback focus) and one for r/webdev (technical/utility focus). Include catchy titles.
      3. Indie Hackers: A "Building in Public" style post focusing on the problem solved and the tech stack (Vite, TS, Capacitor 6, Gemini API).

      Format the output as a valid JSON object.
    `;

    try {
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const text = response.text();
      
      // Clean potential markdown blocks from AI response
      const cleanJson = text.split("json").join("").split("").join("").trim();
      return JSON.parse(cleanJson);
    } catch (error) {
      console.error("Post Generation Error:", error);
      throw new Error("Failed to generate marketing content.");
    }
  }

  static async runCLI() {
    const args = process.argv.slice(2);
    if (args.length === 0) {
      console.log("Usage: node postGenerator.js <json_config_path>");
      return;
    }

    const configPath = path.resolve(args[0]);
    const config = JSON.parse(await fs.promises.readFile(configPath, "utf-8"));
    const generator = new PostGenerator(process.env.GEMINI_API_KEY);

    console.log("🚀 Generating launch posts for Sovereign Studio project...");
    const posts = await generator.generatePosts(config);
    console.log(JSON.stringify(posts, null, 2));
  }
}

// CLI Execution Logic
if (import.meta.url.startsWith("file:")) {
  const modulePath = new URL(import.meta.url).pathname;
  if (process.argv[1] === modulePath || process.argv[1].endsWith("postGenerator.js")) {
    PostGenerator.runCLI().catch(console.error);
  }
}

export default PostGenerator;

/**
 * ARCHITECTURE NOTE:
 * This service leverages the Gemini 1.5 Pro model to ensure high-context awareness 
 * regarding the hybrid Vite/Capacitor architecture of Sovereign Studio. 
 * It avoids regex global replace to maintain compatibility with the core engine standards.
 */