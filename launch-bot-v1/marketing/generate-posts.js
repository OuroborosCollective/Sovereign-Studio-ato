import { GoogleGenerativeAI } from '@google/generative-ai';
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

async function generateMarketingPosts() {
  try {
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });

    const prompt = `
You are a top-tier marketing copywriter. Your task is to write engaging, viral-ready social media posts for our new consumer app: "NOCode Studio".

CRITICAL CONTEXT & RULES:
- The product name is ALWAYS "NOCode Studio". Never mention "Sovereign Studio" or anything related to "Sovereign".
- The product is a premium, no-code app builder that allows regular people to create their own apps effortlessly.
- NEVER mention that this app is backed by a GitHub repository, an autonomous CI/CD pipeline, an APK generator, or any AI coding agents. The user ONLY gets the polished, consumer "NOCode Studio" app.
- We need 14 active beta testers who will use the app for 14 days to pass Google Play Store requirements.
- We have 135 promo codes available.
- The app normally costs €6.49, but beta testers get it completely FREE using a promo code.
- Focus on the value: "Save €6.49", "Get a premium app builder for free", "Create apps without coding".
- Create 3 distinct posts:
  1. A short, punchy tweet (Twitter/X style) with relevant hashtags.
  2. A slightly longer, community-focused post suitable for Reddit (e.g., r/AppIdeas, r/SideProject, r/BetaTesters).
  3. An engaging, visually descriptive post for Facebook Groups or LinkedIn.

Output the results clearly formatted in markdown.
`;

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
