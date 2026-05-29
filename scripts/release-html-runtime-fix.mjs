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
// Do not rewrite JavaScript function bodies in dist/index.html.
// The previous aggressive regex patch could corrupt the monolithic app script
// and break all buttons/menus when a pattern matched too much or too little.
// This file now only performs literal text/model replacements that cannot
// alter brace structure or event handler wiring.
safeReplaceAll('gemini-1.5-flash', 'gemini-2.0-flash', 'legacy Gemini model name');
safeReplaceAll(
  'API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!',
  'Gemini/API Fehler 404 - Modell, API-Zugriff oder Key prüfen.',
  'ambiguous legacy 404 message',
);
safeReplaceAll('Canvas Auto-Auth aktiv', 'Eigener Gemini API Key', 'Gemini input placeholder');
safeReplaceAll('GitHub PAT:', 'GitHub PAT:', 'keep GitHub label stable');
safeReplaceAll('Gemini Key:', 'Gemini Key:', 'keep Gemini label stable');

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
