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
  if (html.includes('SOVEREIGN_BOOT_FALLBACK_V2')) return html;
  const script = `
<script id="SOVEREIGN_BOOT_FALLBACK_V2">
(function(){
  var lastBootError='';
  function hasMountedShell(){
    return Boolean(document.querySelector('[data-testid="app-shell__root"],[data-testid="repo-snapshot-container"],[data-testid="builder-container"],[data-testid="operator-monitor"],.sovereign-login-shell,[data-sovereign-admin-producer],.admin-shell,.admin-auth-shell'));
  }
  function bootFallback(reason){
    var root=document.getElementById('root');
    if(!root||hasMountedShell())return;
    var text=(root.textContent||'').trim();
    var hasRenderedContent=root.childElementCount>0&&text.length>120;
    if(hasRenderedContent)return;
    if(text&&!/^(Loading|Lade|Refactor)/i.test(text))return;
    root.innerHTML='<main style="min-height:100dvh;box-sizing:border-box;padding:24px 16px;background:#0f172a;color:#e5e7eb;font-family:system-ui,-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;overflow:auto;-webkit-overflow-scrolling:touch">' +
      '<section style="max-width:720px;margin:0 auto;border:1px solid #334155;padding:18px;background:#111827">' +
      '<p style="margin:0 0 8px;color:#38bdf8;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase">Sovereign Studio · Android Recovery</p>' +
      '<h1 style="margin:0 0 12px;color:#f8fafc;font-size:24px">App-Bundle konnte nicht starten</h1>' +
      '<p style="margin:0 0 10px;color:#cbd5e1;line-height:1.5">Die eigentliche Sovereign-App wurde nicht ersetzt. Dieser Bildschirm erscheint nur, wenn der Android/WebView-Bundle nicht geladen oder nicht sauber synchronisiert wurde.</p>' +
      '<p style="margin:0 0 14px;color:#94a3b8;font-size:13px;line-height:1.45">Recovery-Hinweis: Build erneut ausfuehren und sicherstellen, dass die aktuellen Web-Assets nach Android synchronisiert wurden.</p>' +
      '<pre style="white-space:pre-wrap;border:1px solid #1f2937;background:#020617;color:#93c5fd;padding:10px;font-size:12px">npm run build:web\\nnpx cap sync android</pre>' +
      '<button onclick="location.reload()" style="margin-top:14px;border:1px solid #38bdf8;padding:12px 14px;background:#0ea5e9;color:#020617;font-weight:800">Neu laden</button>' +
      '</section></main>';
    if(window.console&&console.warn)console.warn('[Sovereign Recovery] Android boot fallback shown:',reason||lastBootError||'startup timeout');
  }
  window.addEventListener('error',function(event){
    lastBootError=event&&event.message?String(event.message).slice(0,160):'runtime error';
  });
  setTimeout(function(){bootFallback(lastBootError||'startup timeout')},15000);
})();
</script>
`;
  return html.replace('</body>', `${script}</body>`);
}

function removeOldBootFallback(html) {
  return html.replace(/\n?<script id="SOVEREIGN_BOOT_FALLBACK_V1">[\s\S]*?<\/script>\n?/g, '\n');
}

function patchFile(filePath) {
  if (!existsSync(filePath)) {
    console.warn(`[release-html-runtime-fix] ${filePath} not found. Skipping.`);
    return;
  }

  let html = readFileSync(filePath, 'utf8');
  let changed = false;

  const withoutOldFallback = removeOldBootFallback(html);
  if (withoutOldFallback !== html) {
    html = withoutOldFallback;
    changed = true;
    console.log(`[release-html-runtime-fix] removed legacy Android/WebView boot fallback in ${filePath}`);
  }

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
    console.log(`[release-html-runtime-fix] injected Android/WebView recovery fallback in ${filePath}`);
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
