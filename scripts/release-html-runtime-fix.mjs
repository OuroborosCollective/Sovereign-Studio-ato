import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const targetPaths = [
  resolve('dist/index.html'),
  resolve('android/app/src/main/assets/public/index.html'),
];

const replacements = [
  {
    from: 'gemini-1.5-flash',
    to: 'gemini-2.0-flash',
    label: 'legacy Gemini model name',
  },
  {
    from: 'API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!',
    to: 'Gemini/API Fehler 404 - Modell, API-Zugriff oder Key prüfen.',
    label: 'legacy 404 message',
  },
  {
    from: "throw new Error('API Fehler ' + response.status + ' - Bitte GitHub PAT und/oder Gemini Key eingeben!');",
    to: "if (response.status === 429) throw new Error('Gemini 429: Rate-Limit oder Kontingent erreicht. Bitte später erneut versuchen oder einen Gemini API Key mit freiem Kontingent nutzen.');\n                        if (response.status === 404) throw new Error('Gemini 404: Modell nicht verfügbar. App-Build nutzt ein veraltetes oder nicht freigeschaltetes Gemini-Modell.');\n                        throw new Error('Gemini API Fehler ' + response.status + ' - Key, Modell, API-Freigabe oder Kontingent prüfen.');",
    label: 'Gemini non-401 error handling',
  },
  {
    from: "                } catch (err) {\n                    if (i === maxRetries) throw err;\n                    await new Promise(resolve => setTimeout(resolve, delays[i]));\n                }",
    to: "                } catch (err) {\n                    const message = String(err && err.message ? err.message : err);\n                    if (message.includes('Gemini 429') || message.includes('401 Unauthorized')) throw err;\n                    if (i === maxRetries) throw err;\n                    await new Promise(resolve => setTimeout(resolve, delays[i]));\n                }",
    label: 'stop retrying quota/auth failures',
  },
  {
    from: 'Canvas Auto-Auth aktiv',
    to: 'Eigener Gemini API Key',
    label: 'Gemini input placeholder',
  },
];

const forbidden = [
  'Bitte GitHub PAT und/oder Gemini Key eingeben!',
  'gemini-1.5-flash',
  'testPhaseOneCredentials()',
  'Mock-Login ist in Phase 1 deaktiviert',
  'Phase 1 Release Runtime: local user-owned credentials',
];

function patchFile(filePath) {
  if (!existsSync(filePath)) {
    console.warn(`[release-html-runtime-fix] ${filePath} not found. Skipping.`);
    return;
  }

  let html = readFileSync(filePath, 'utf8');
  let changed = false;

  for (const replacement of replacements) {
    if (!html.includes(replacement.from)) {
      console.warn(`[release-html-runtime-fix] not found in ${filePath}: ${replacement.label}`);
      continue;
    }
    html = html.split(replacement.from).join(replacement.to);
    changed = true;
    console.log(`[release-html-runtime-fix] patched ${replacement.label} in ${filePath}`);
  }

  if (changed) {
    writeFileSync(filePath, html, 'utf8');
    console.log(`[release-html-runtime-fix] ${filePath} updated.`);
  } else {
    console.warn(`[release-html-runtime-fix] no replacements applied to ${filePath}.`);
  }

  for (const marker of forbidden) {
    if (html.includes(marker)) {
      console.error(`[release-html-runtime-fix] forbidden marker still present in ${filePath}: ${marker}`);
      process.exit(1);
    }
  }
}

for (const filePath of targetPaths) {
  patchFile(filePath);
}

console.log('[release-html-runtime-fix] HTML workspace release patch completed.');
