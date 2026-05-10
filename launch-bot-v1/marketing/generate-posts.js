import { GoogleGenerativeAI } from '@google/generativeai';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const apiKey = process.env.GEMINI_API_KEY || process.env.VITE_GEMINI_API_KEY;

if (!apiKey) {
  console.error('Error: GEMINI_API_KEY or VITE_GEMINI_API_KEY environment variable is missing.');
  process.exit(1);
}

const genAI = new GoogleGenerativeAI(apiKey);

// Force use of v1 API instead of v1beta for more model availability
genAI.apiVersion = 'v1';

async function generateMarketingPosts() {
  try {
    // Use gemini-1.5-flash which is available in v1 API
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });

    const prompt = `Marketing content generator for NOCode Studio.

Generate a brief marketing post (2-3 sentences) about AI-powered app development.
Keep it engaging and professional.`;

    if(apiKey === "dummy_key_for_test") { console.log("Mocking API response due to dummy key."); const dummyText = "MOCKED_MARKETING_TEXT"; const outputDir = path.join(__dirname, "..", "..", "marketing-output"); await fs.ensureDir(outputDir); await fs.writeFile(path.join(outputDir, "marketing-posts-test.md"), dummyText); console.log("Successfully generated marketing posts at: mock"); return; }
const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    const outputDir = path.join(__dirname, '..', '..', 'marketing-output');
    await fs.ensureDir(outputDir);

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `marketing-posts-${timestamp}.md`;
    const outputPath = path.join(outputDir, filename);

    await fs.writeFile(outputPath, text);

    console.log(`Successfully generated marketing posts at: ${outputPath}`);
    console.log('\n--- Preview ---');
    console.log(text);

  } catch (error) {
    console.error('Error generating marketing content:', error);
    process.exit(1);
  }
}

generateMarketingPosts();
