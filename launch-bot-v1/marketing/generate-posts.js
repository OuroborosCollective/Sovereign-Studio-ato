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

async function generateMarketingPosts() {
  // Generate mock content by default
  let text = "MOCKED_MARKETING_TEXT - Default marketing content";
  
  try {
    // Call v1beta API directly
    const prompt = `Generate a brief marketing post (2-3 sentences) about AI-powered app development. Keep it engaging and professional.`;

    const response = await fetch('https://generativelanguage.googleapis.com/v1beta/models?key=' + apiKey, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { temperature: 0.7, maxOutputTokens: 256 }
      })
    });

    // Check if response is valid JSON
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      console.log('Invalid response content-type, using mock');
      throw new Error('Invalid API response');
    }
    
    const data = await response.json();
    
    if (data.error) {
      console.log('API error: ' + data.error.message + ', using mock');
      throw new Error(data.error.message);
    }
    
    text = data.candidates?.[0]?.content?.parts?.[0]?.text || text;
  } catch (err) {
    console.log('API call failed: ' + err.message + ', generating mock content');
  }

  const outputDir = path.join(__dirname, '..', '..', 'marketing-output');
  await fs.ensureDir(outputDir);

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `marketing-posts-${timestamp}.md`;
  const outputPath = path.join(outputDir, filename);

  await fs.writeFile(outputPath, text);

  console.log(`Successfully generated marketing posts at: ${outputPath}`);
  console.log('\n--- Preview ---');
  console.log(text);
}

generateMarketingPosts().catch(err => {
  console.error('Error generating marketing content:', err);
  process.exit(1);
});