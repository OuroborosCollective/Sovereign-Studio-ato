import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const distIndexPath = resolve('dist/index.html');

if (!existsSync(distIndexPath)) {
  console.warn('[release-html-runtime-fix] dist/index.html not found. Skipping safe runtime patch.');
  process.exit(0);
}

let html = readFileSync(distIndexPath, 'utf8');
let changed = false;

function safeReplaceAll(from, to, label) {
  if (!html.includes(from)) {
    console.warn(`[release-html-runtime-fix] not found: ${label}`);
    return;
  }
  html = html.split(from).join(to);
  changed = true;
  console.log(`[release-html-runtime-fix] safely patched: ${label}`);
}

// Emergency-safe Phase 1 patch:
// Do not rewrite large JavaScript function bodies in dist/index.html.
// Only literal single-line/small-block replacements are allowed here.
safeReplaceAll('gemini-1.5-flash', 'gemini-2.0-flash', 'legacy Gemini model name');
safeReplaceAll(
  'API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!',
  'Gemini/API Fehler 404 - Modell, API-Zugriff oder Key prüfen.',
  'ambiguous legacy 404 message',
);
safeReplaceAll(
  "throw new Error('API Fehler ' + response.status + ' - Bitte GitHub PAT und/oder Gemini Key eingeben!');",
  "if (response.status === 429) throw new Error('Gemini 429: Rate-Limit oder Kontingent erreicht. Bitte später erneut versuchen oder einen Gemini API Key mit freiem Kontingent nutzen.');\n                        if (response.status === 404) throw new Error('Gemini 404: Modell nicht verfügbar. App-Build nutzt ein veraltetes oder nicht freigeschaltetes Gemini-Modell.');\n                        throw new Error('Gemini API Fehler ' + response.status + ' - Key, Modell, API-Freigabe oder Kontingent prüfen.');",
  'Gemini non-401 error handling',
);
safeReplaceAll(
  "                } catch (err) {\n                    if (i === maxRetries) throw err;\n                    await new Promise(resolve => setTimeout(resolve, delays[i]));\n                }",
  "                } catch (err) {\n                    const message = String(err && err.message ? err.message : err);\n                    if (message.includes('Gemini 429') || message.includes('401 Unauthorized')) throw err;\n                    if (i === maxRetries) throw err;\n                    await new Promise(resolve => setTimeout(resolve, delays[i]));\n                }",
  'stop retrying quota/auth failures',
);
safeReplaceAll('Canvas Auto-Auth aktiv', 'Eigener Gemini API Key', 'Gemini input placeholder');

if (changed) {
  writeFileSync(distIndexPath, html, 'utf8');
  console.log('[release-html-runtime-fix] dist/index.html updated with safe literal replacements only.');
} else {
  console.warn('[release-html-runtime-fix] no safe replacements applied.');
}

// Guard against accidentally reintroducing the dangerous generated patch style.
const dangerousMarkers = [
  'testPhaseOneCredentials()',
  'Mock-Login ist in Phase 1 deaktiviert',
  'Phase 1 Release Runtime: local user-owned credentials',
];

for (const marker of dangerousMarkers) {
  if (html.includes(marker)) {
    console.error(`[release-html-runtime-fix] dangerous generated marker still present: ${marker}`);
    process.exit(1);
  }
}

console.log('[release-html-runtime-fix] Safe emergency runtime patch completed.');
