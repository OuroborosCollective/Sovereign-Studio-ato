import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const targetPaths = [
  resolve('dist/index.html'),
  resolve('android/app/src/main/assets/public/index.html'),
];

const replacements = [
  { from: 'gemini-1.5-flash', to: 'gemini-2.0-flash', label: 'legacy Gemini model name' },
  { from: 'API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!', to: 'Gemini/API Fehler 404 - Modell, API-Zugriff oder Key prüfen.', label: 'legacy 404 message' },
  { from: 'Canvas Auto-Auth aktiv', to: 'Eigener Gemini API Key', label: 'Gemini input placeholder' },
];

const forbidden = [
  'Bitte GitHub PAT und/oder Gemini Key eingeben!',
  'gemini-1.5-flash',
  'testPhaseOneCredentials()',
  'Mock-Login ist in Phase 1 deaktiviert',
  'Phase 1 Release Runtime: local user-owned credentials',
];

function injectBootFallback(html) {
  if (html.includes('SOVEREIGN_BOOT_FALLBACK_V1')) return html;
  const script = `\n<script id="SOVEREIGN_BOOT_FALLBACK_V1">\n(function(){\n  function bootFallback(){\n    var root=document.getElementById('root');\n    if(!root||!/Loading Refactor/i.test(root.textContent||''))return;\n    root.innerHTML='<main style="min-height:100vh;box-sizing:border-box;padding:28px 18px;background:#1c1917;color:#f5f5f4;font-family:system-ui">' +\n      '<section style="border:1px solid #574522;border-radius:18px;padding:18px;background:#292524">' +\n      '<h1 style="color:#fbbf24;margin-top:0">Sovereign Studio Boot-Fix aktiv</h1>' +\n      '<p>Der Web-Bundle wurde nicht geladen. Statt Endlos-Loader ist die App jetzt in einem sicheren Recovery-Modus.</p>' +\n      '<p>Release-Fix: npm run build ausfuehren, damit Capacitor die aktuellen Android Assets synchronisiert.</p>' +\n      '<button onclick="location.reload()" style="border:0;border-radius:12px;padding:14px 16px;background:#f59e0b;color:#1c1917;font-weight:800">Neu laden</button>' +\n      '</section></main>';\n  }\n  window.addEventListener('error',function(){setTimeout(bootFallback,100)});\n  setTimeout(bootFallback,1800);\n})();\n</script>\n`;
  return html.replace('</body>', `${script}</body>`);
}

function patchFile(filePath) {
  if (!existsSync(filePath)) {
    console.warn(`[release-html-runtime-fix] ${filePath} not found. Skipping.`);
    return;
  }

  let html = readFileSync(filePath, 'utf8');
  let changed = false;

  for (const replacement of replacements) {
    if (!html.includes(replacement.from)) continue;
    html = html.split(replacement.from).join(replacement.to);
    changed = true;
    console.log(`[release-html-runtime-fix] patched ${replacement.label} in ${filePath}`);
  }

  const withFallback = injectBootFallback(html);
  if (withFallback !== html) {
    html = withFallback;
    changed = true;
    console.log(`[release-html-runtime-fix] injected Android/WebView boot fallback in ${filePath}`);
  }

  for (const marker of forbidden) {
    if (html.includes(marker)) {
      console.error(`[release-html-runtime-fix] forbidden marker still present in ${filePath}: ${marker}`);
      process.exit(1);
    }
  }

  if (changed) writeFileSync(filePath, html, 'utf8');
}

for (const filePath of targetPaths) patchFile(filePath);
console.log('[release-html-runtime-fix] HTML workspace release patch completed.');
