import { GoogleGenerativeAI, GenerationConfig } from "@google/generative-ai";

const API_KEY = process.env.NEXT_PUBLIC_GEMINI_API_KEY || process.env.GEMINI_API_KEY || "";
const genAI = new GoogleGenerativeAI(API_KEY);

const DEFAULT_CONFIG: GenerationConfig = {
  temperature: 0.1,
  topP: 0.95,
  topK: 40,
  maxOutputTokens: 8192,
};

export interface FileNode {
  path: string;
  type: "file" | "directory";
}

/**
 * Robustly extracts JSON from a string by locating the first '[' and last ']'
 * to prevent "JSON explosions" caused by conversational filler.
 */
export const extractJsonArray = <T>(text: string): T[] => {
  try {
    const start = text.indexOf('[');
    const end = text.lastIndexOf(']');

    if (start === -1 || end === -1 || end < start) {
      // Fallback: try to see if it's a single object wrapped in an array or just the array missing brackets
      const braceStart = text.indexOf('{');
      const braceEnd = text.lastIndexOf('}');
      if (braceStart !== -1 && braceEnd !== -1) {
        return [JSON.parse(text.substring(braceStart, braceEnd + 1))] as T[];
      }
      throw new Error("No valid JSON structure found in response");
    }

    const jsonContent = text.substring(start, end + 1);
    return JSON.parse(jsonContent) as T[];
  } catch (error) {
    console.error("JSON Extraction Error:", error, "Raw text:", text);
    throw new Error("Failed to parse model response into JSON array");
  }
};

/**
 * Intelligent path selection to optimize token usage.
 * Filters out noise and common dependency directories.
 */
const filterRelevantPaths = (paths: string[]): string[] => {
  const EXCLUDED_PATTERNS = [
    /node_modules\//,
    /\.git\//,
    /\.next\//,
    /dist\//,
    /build\//,
    /\.cache\//,
    /package-lock\.json$/,
    /yarn\.lock$/,
    /pnpm-lock\.yaml$/,
    /\.DS_Store$/,
    /\.env/
  ];

  return paths.filter(path => !EXCLUDED_PATTERNS.some(regex => regex.test(path)));
};

/**
 * Generates a project tree structure.
 * Replaced hard limit of 400 with a token-aware dynamic approach (approx 2500 files).
 */
export const generateProjectTree = async (allPaths: string[]): Promise<FileNode[]> => {
  const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash", generationConfig: DEFAULT_CONFIG });

  const relevantPaths = filterRelevantPaths(allPaths);
  // Gemini 1.5 context window is huge, but we limit to 2500 for responsiveness and output density
  const truncatedPaths = relevantPaths.slice(0, 2500);

  const prompt = `
    Analyze these file paths and generate a clean directory tree.
    Return a JSON array of objects with "path" (string) and "type" ("file" | "directory").
    
    Paths to process:
    ${truncatedPaths.join("\n")}

    Constraint: Return ONLY the JSON array. Do not add markdown formatting or explanations.
  `;

  try {
    const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();
    return extractJsonArray<FileNode>(text);
  } catch (error) {
    console.error("Error generating tree with Gemini:", error);
    // Fallback logic: Create basic nodes from paths if API fails
    return truncatedPaths.map(p => ({
      path: p,
      type: p.includes('.') ? "file" : "directory"
    }));
  }
};

export const analyzeCode = async (fileName: string, code: string, context?: string) => {
  const model = genAI.getGenerativeModel({ model: "gemini-1.5-pro", generationConfig: DEFAULT_CONFIG });

  const prompt = `
    Context: ${context || "General code analysis"}
    File: ${fileName}
    Code:
    \`\`\`
    ${code}
    \`\`\`

    Analyze the code above for bugs, performance issues, and security vulnerabilities.
    Return a JSON array of objects: { "severity": "low"|"medium"|"high", "message": "...", "line": number }.
  `;

  try {
    const result = await model.generateContent(prompt);
    const text = (await result.response).text();
    return extractJsonArray(text);
  } catch (error) {
    console.error("Code analysis error:", error);
    return [];
  }
};

export const getGeminiResponse = async (prompt: string, modelType: "flash" | "pro" = "flash") => {
  const modelName = modelType === "pro" ? "gemini-1.5-pro" : "gemini-1.5-flash";
  const model = genAI.getGenerativeModel({ model: modelName, generationConfig: DEFAULT_CONFIG });

  try {
    const result = await model.generateContent(prompt);
    return (await result.response).text();
  } catch (error) {
    console.error("Gemini API Error:", error);
    throw error;
  }
};