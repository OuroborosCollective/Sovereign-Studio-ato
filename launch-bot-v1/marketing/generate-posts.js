import { GoogleGenerativeAI } from '@google/generative-ai';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const apiKey = process.env.GEMINI_API_KEY || process.env.VITE_GEMINI_API_KEY;

// Command-line argument: beta codes
const betaCodes = process.argv[2] || '';

const PLAY_STORE_URL = 'https://play.google.com/store/apps/details?id=com.arestudio.nocode.aab';

if (!apiKey) {
  console.error('Error: GEMINI_API_KEY or VITE_GEMINI_API_KEY environment variable is missing.');
  process.exit(1);
}

const genAI = new GoogleGenerativeAI(apiKey);

async function generateMarketingPosts() {
  let text = '';
  let retries = 3;
  let delay = 5000;
  
  while (retries > 0) {
    try {
      const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

      const betaCodesList = betaCodes.split(',').filter(c => c.trim());
      const codesPreview = betaCodesList.slice(0, 3).join(', ') + (betaCodesList.length > 3 ? '...' : '');
      
      const prompt = `Generate exciting marketing content for NOCode Studio - an AI-powered app development platform!

Target: Google Play Store app users
App Link: ${PLAY_STORE_URL}

${betaCodesList.length > 0 ? `EXCLUSIVE BETA CODES: ${codesPreview}` : ''}

Requirements:
1. Include the exact Play Store URL: ${PLAY_STORE_URL}
2. Create excitement about the AI-powered app building experience
3. If beta codes provided, mention them prominently - users can use these codes for premium features
4. Keep it engaging and professional (2-3 short paragraphs)
5. End with a clear call-to-action to download

Make it compelling and unique - stand out from typical app promotions!`;

      console.log('Generating marketing content for:', PLAY_STORE_URL);
      if (betaCodesList.length > 0) {
        console.log('Including beta codes:', codesPreview);
      }
      
      const result = await model.generateContent(prompt);
      const response = await result.response;
      text = response.text();
      break;
    } catch (error) {
      retries--;
      const retryAfter = error.errorDetails?.find(e => e['@type'] === 'type.googleapis.com/google.rpc.RelayInfo')?.retryDelaySeconds;
      const waitTime = retryAfter ? retryAfter * 1000 : delay;
      
      if ((error.status === 429 || error.message?.includes('quota')) && retries > 0) {
        console.log(`Rate limited/quota exceeded, retrying in ${waitTime/1000}s... (${retries} attempts left)`);
        await new Promise(resolve => setTimeout(resolve, waitTime));
        delay *= 2;
      } else if (retries > 0) {
        console.log(`API error: ${error.message}, retrying in ${delay/1000}s... (${retries} attempts left)`);
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 1.5;
      } else {
        // Fall back to mock content on complete failure
        console.log('All retries exhausted, using fallback content');
        const betaCodesList = betaCodes.split(',').filter(c => c.trim());
        text = `🚀 Build Apps with AI - No Coding Required!

NOCODE Studio brings the power of AI to app development. Describe your idea in plain English, and watch your app come to life INSTANTLY.

📱 Get the app: ${PLAY_STORE_URL}
${betaCodesList.length > 0 ? `\n🎁 Exclusive beta access codes: ${betaCodesList.join(', ')}` : ''}

Built for creators, entrepreneurs, and anyone with a great idea. Download now and start building!`;
      }
    }
  }

  const outputDir = path.join(__dirname, '..', '..', 'marketing-output');
  await fs.ensureDir(outputDir);

  // Add metadata footer
  const betaCodesList = betaCodes.split(',').filter(c => c.trim());
  const contentWithMeta = `${text}

---
📱 Download: ${PLAY_STORE_URL}
${betaCodesList.length > 0 ? `🎁 Beta Codes: ${betaCodesList.join(', ')}` : ''}`;

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const filename = `marketing-posts-${timestamp}.md`;
  const outputPath = path.join(outputDir, filename);

  await fs.writeFile(outputPath, contentWithMeta);

  console.log(`Successfully generated marketing posts at: ${outputPath}`);
  console.log('\n--- Preview ---');
  console.log(text);
}

generateMarketingPosts().catch(err => {
  console.error('Error generating marketing content:', err);
  process.exit(1);
});