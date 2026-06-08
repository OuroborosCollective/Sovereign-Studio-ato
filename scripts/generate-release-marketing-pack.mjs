import { mkdirSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

const version = process.env.RELEASE_VERSION || process.argv[2] || '0.0.0';
const buildNumber = process.env.RELEASE_BUILD || process.argv[3] || 'local';
const platform = process.env.RELEASE_PLATFORM || process.argv[4] || 'android';
const voucherCount = Number(process.env.RELEASE_VOUCHERS || process.argv[5] || 66);
const outDir = resolve(process.env.MARKETING_OUT_DIR || 'release-bundle/marketing');
const releaseDate = new Date().toISOString().slice(0, 10);

mkdirSync(outDir, { recursive: true });

function run(command, fallback = '') {
  try {
    return execSync(command, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return fallback;
  }
}

const previousTag = run('git describe --tags --abbrev=0 --match "v*" HEAD^', '');
const range = previousTag ? `${previousTag}..HEAD` : 'HEAD~30..HEAD';
const commits = run(`git log ${range} --no-merges --pretty=format:%s`, '')
  .split('\n')
  .map(line => line.trim())
  .filter(Boolean)
  .filter((line, index, all) => all.indexOf(line) === index);

const fallbackItems = [
  'Lokale User-Credentials für GitHub PAT und Gemini API Key stabilisiert.',
  'Awareness Sync und KI-Funktionen für Phase 1 releasefähiger gemacht.',
  'Android Release Build und Runtime-Patching gehärtet.'
];

const items = commits.length ? commits.slice(0, 12) : fallbackItems;
const highlights = items.slice(0, 6).map(item => item.replace(/^[a-z]+\([^)]*\)!?:\s*/i, '').replace(/^[a-z]+!?:\s*/i, ''));
const summary = `Sovereign Studio ${version} bündelt Release-Stabilität, lokale User-Credentials und klarere GitHub/Gemini-Diagnosen in einem einheitlichen Phase-1-Release.`;

function bullets(list) {
  return list.map(item => `- ${item}`).join('\n');
}

const patchNotes = `# Sovereign Studio ${version} Patchnotes\n\nRelease-Date: ${releaseDate}\nBuild: ${buildNumber}\nPlatform: ${platform}\nPrevious tag: ${previousTag || 'n/a'}\n\n## Unisono Summary\n\n${summary}\n\n## Änderungen\n\n${bullets(highlights)}\n\n## Credential-Hinweis\n\nGitHub PAT und Gemini API Key werden nicht in der App ausgeliefert. Jeder User trägt eigene Credentials ein; diese bleiben lokal auf dem Gerät.\n`;

const playStoreDe = `${summary}\n\nNeu:\n${highlights.slice(0, 4).map(item => `• ${item}`).join('\n')}\n\nHinweis: GitHub PAT und Gemini API Key bleiben lokale User-Credentials auf dem Gerät.`;
const playStoreEn = `Sovereign Studio ${version} improves release stability, local user credentials, and clearer GitHub/Gemini diagnostics.\n\nWhat's new:\n${highlights.slice(0, 4).map(item => `• ${item}`).join('\n')}\n\nNote: GitHub PAT and Gemini API key remain local user-owned credentials on the device.`;

const socialPosts = `# Sovereign Studio ${version} Social Posts\n\n## DE\n${summary}\n\n${highlights.slice(0, 4).map(item => `✅ ${item}`).join('\n')}\n\n#SovereignStudio #NoCode #Android #AI\n\n## EN\nSovereign Studio ${version} is ready for Phase 1: safer local credentials, clearer diagnostics, and a harder Android release path.\n\n${highlights.slice(0, 4).map(item => `✅ ${item}`).join('\n')}\n\n#SovereignStudio #NoCode #Android #AI\n`;

const testerOutreach = `# Tester Outreach Template\n\nHallo! Sovereign Studio ${version} ist bereit für einen neuen Android-Testlauf.\n\n${summary}\n\nBitte teste besonders:\n${bullets(highlights.slice(0, 5))}\n\nWichtig: Für GitHub/Gemini-Funktionen nutzt jeder Tester eigene lokale Credentials. Es werden keine zentralen Tokens in der App ausgeliefert.\n`;

const vouchers = {
  note: 'Placeholders only. Replace with real Google Play promo/voucher codes from Play Console before publishing.',
  version,
  buildNumber,
  platform,
  voucherCount,
  slots: Array.from({ length: voucherCount }, (_, index) => ({
    slot: index + 1,
    label: `tester-voucher-${String(index + 1).padStart(2, '0')}`,
    code: null,
    assignedTo: null,
    status: 'empty'
  }))
};

const campaign = {
  campaign: 'initial_spark',
  version,
  buildNumber,
  platform,
  releaseDate,
  summary,
  previousTag: previousTag || null,
  voucherCount,
  files: [
    'PATCH_NOTES.md',
    'PLAY_STORE_NOTES_de-DE.txt',
    'PLAY_STORE_NOTES_en-US.txt',
    'SOCIAL_POSTS.md',
    'TESTER_OUTREACH.md',
    'voucher-placeholders.json',
    'campaign.json'
  ]
};

writeFileSync(resolve(outDir, 'PATCH_NOTES.md'), patchNotes, 'utf8');
writeFileSync(resolve(outDir, 'PLAY_STORE_NOTES_de-DE.txt'), playStoreDe, 'utf8');
writeFileSync(resolve(outDir, 'PLAY_STORE_NOTES_en-US.txt'), playStoreEn, 'utf8');
writeFileSync(resolve(outDir, 'SOCIAL_POSTS.md'), socialPosts, 'utf8');
writeFileSync(resolve(outDir, 'TESTER_OUTREACH.md'), testerOutreach, 'utf8');
writeFileSync(resolve(outDir, 'voucher-placeholders.json'), `${JSON.stringify(vouchers, null, 2)}\n`, 'utf8');
writeFileSync(resolve(outDir, 'campaign.json'), `${JSON.stringify(campaign, null, 2)}\n`, 'utf8');

console.log(`[marketing-pack] Generated marketing pack for v${version} build ${buildNumber} in ${outDir}`);
