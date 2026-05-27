import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { MarketerAgent } from '../../mesh-system/agents/marketer.js';
import { ReviewerAgent } from '../../mesh-system/agents/reviewer.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  console.log('Starting automated marketing campaign generation...');

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error('GEMINI_API_KEY is not set. Skipping live generation for tests.');
    return;
  }

  const marketer = new MarketerAgent(apiKey);
  const reviewer = new ReviewerAgent(apiKey);

  const codesPath = path.join(__dirname, 'promo-codes.txt');
  let codes = [];
  try {
    const codesContent = await fs.readFile(codesPath, 'utf8');
    codes = codesContent.split('\n').map(c => c.trim()).filter(c => c.length > 0);
  } catch (error) {
    console.error('Failed to read promo codes file', error);
    process.exit(1);
  }

  if (codes.length === 0) {
     console.log('No more promo codes available. Exiting.');
     process.exit(0);
  }

  // Select a batch of 10 codes for this campaign
  const selectedCodes = codes.slice(0, 10);
  const remainingCodes = codes.slice(10);

  console.log(`Generating campaign for ${selectedCodes.length} codes...`);

  const featureUpdate = {
    goal: "Get 14 active testers for 2 weeks",
    codes: selectedCodes,
    description: "Exclusive Beta Tester Access"
  };

  try {
    const campaignText = await marketer.generateSocialMediaCampaign(featureUpdate);
    console.log('Campaign generated. Running through reviewer for sanitization...');

    const sanitizedChannels = {};
    for (const channel of ['reddit', 'twitter', 'discord']) {
      if (campaignText[channel]) {
         const result = reviewer.sanitizeMarketingContent(campaignText[channel]);
         if (!result.isClean) {
            console.warn(`Issues detected in ${channel}:`, result.detectedIssues);
         }
         sanitizedChannels[channel] = result.sanitizedContent;
      }
    }

    sanitizedChannels.timestamp = new Date().toISOString();

    const outputPath = path.join(__dirname, 'campaign-output.json');
    await fs.writeFile(outputPath, JSON.stringify(sanitizedChannels, null, 2), 'utf8');

    // Update the promo-codes.txt file with remaining codes
    await fs.writeFile(codesPath, remainingCodes.join('\n') + (remainingCodes.length > 0 ? '\n' : ''), 'utf8');
    console.log(`Updated promo codes list. ${remainingCodes.length} remaining.`);
    console.log(`Sanitized campaign saved to ${outputPath}`);
  } catch (error) {
    console.error('Failed during campaign generation or review:', error);
    process.exit(1);
  }
}

main();
