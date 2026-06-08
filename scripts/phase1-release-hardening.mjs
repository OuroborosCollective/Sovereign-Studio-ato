import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const distIndexPath = resolve('dist/index.html');

if (!existsSync(distIndexPath)) {
  console.warn('[phase1-release-hardening] dist/index.html not found. Skipping Phase 1 hardening.');
  process.exit(0);
}

let html = readFileSync(distIndexPath, 'utf8');
let changed = false;

const replaceOnce = (from, to, label) => {
  if (html.includes(from)) {
    html = html.replace(from, to);
    changed = true;
    console.log(`[phase1-release-hardening] patched ${label}`);
  } else {
    console.warn(`[phase1-release-hardening] pattern not found for ${label}`);
  }
};

const replaceAll = (from, to, label) => {
  if (html.includes(from)) {
    html = html.split(from).join(to);
    changed = true;
    console.log(`[phase1-release-hardening] patched ${label}`);
  } else {
    console.warn(`[phase1-release-hardening] pattern not found for ${label}`);
  }
};

replaceAll('GitHub PAT:', 'GitHub PAT (User):', 'GitHub PAT label');
replaceAll('Gemini Key:', 'Gemini Key (User):', 'Gemini Key label');
replaceAll('</svg> Login', '</svg> Google optional', 'Google button label');
replaceAll('GitHub Token fehlt (Optional)', 'GitHub PAT fehlt', 'setup modal GitHub title');
replaceAll('Um Code zu pushen oder PRs zu erstellen, benötigst du einen', 'Für private Repos, Push und PRs trägt jeder User seinen eigenen', 'setup modal GitHub copy');
replaceAll('Der Architekt hat deinen persönlichen Workspace & Keys geladen.', 'Der Architekt nutzt deine lokal gespeicherten Workspace-Keys.', 'workspace key copy');

replaceOnce(
`<input type="password" id="gemini-key" placeholder="Canvas Auto-Auth aktiv" class="text-xs px-2 py-1 border border-stone-300 rounded w-48 focus:outline-none focus:border-indigo-500 bg-white">`,
`<input type="password" id="gemini-key" placeholder="Eigener Gemini API Key" class="text-xs px-2 py-1 border border-stone-300 rounded w-48 focus:outline-none focus:border-indigo-500 bg-white">
                <button onclick="saveKeys(); window.logToSystem('🔐 <b>Keys lokal gespeichert.</b><br>Keine Tokens werden in die App eingebettet oder an Sovereign Studio übertragen.', 'success')" class="px-2 py-1 bg-emerald-100 border border-emerald-300 text-emerald-800 rounded text-[10px] font-bold hover:bg-emerald-200 transition-colors">💾 SPEICHERN</button>
                <button onclick="testPhaseOneCredentials()" class="px-2 py-1 bg-sky-100 border border-sky-300 text-sky-800 rounded text-[10px] font-bold hover:bg-sky-200 transition-colors">🧪 TEST</button>`,
'Phase 1 save/test controls',
);

const phaseOneHelpers = `
        // --- Phase 1: local user-token workspace ---
        window.saveKeys = saveKeys;
        window.loadKeys = loadKeys;

        window.testPhaseOneCredentials = async function() {
            try {
                saveKeys();
                const pat = typeof getGitHubPAT === 'function' ? getGitHubPAT() : (document.getElementById('gh-pat')?.value || '').trim();
                const gemini = typeof getGeminiKey === 'function' ? getGeminiKey() : (document.getElementById('gemini-key')?.value || '').trim();

                if (!pat) {
                    window.logToSystem('⚠️ <b>GitHub PAT fehlt.</b><br>Öffentliche Repo-Reads können funktionieren, aber private Repos, Push und PRs brauchen einen User-PAT.', 'warning');
                } else {
                    const headers = typeof githubHeaders === 'function'
                        ? githubHeaders()
                        : { Authorization: 'Bearer ' + pat, Accept: 'application/vnd.github.v3+json' };
                    const ghRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName, { headers });
                    if (!ghRes.ok) throw new Error(typeof githubErrorMessage === 'function' ? await githubErrorMessage(ghRes, 'GitHub Verbindung fehlgeschlagen.') : 'GitHub Fehler ' + ghRes.status);
                    window.logToSystem('✅ <b>GitHub PAT funktioniert.</b><br><code>' + repoOwner + '/' + repoName + '</code> ist erreichbar.', 'success');
                }

                if (!gemini) {
                    window.logToSystem('⚠️ <b>Gemini Key fehlt.</b><br>Awareness Sync und KI-Funktionen brauchen in Phase 1 einen eigenen Gemini API Key.', 'warning');
                } else {
                    const answer = await callGeminiAPI('Antworte exakt mit: OK', 'Du bist ein minimaler API-Verbindungstest. Antworte nur mit OK.');
                    window.logToSystem('✅ <b>Gemini Key funktioniert.</b><br>Antwort: <code>' + String(answer).replace(/</g, '&lt;').replace(/>/g, '&gt;').slice(0, 80) + '</code>', 'success');
                }
            } catch (err) {
                window.logToSystem('❌ <b>Phase-1 Credential-Test fehlgeschlagen:</b><br>' + (err?.message || err), 'error');
            }
        };
`;

replaceOnce(
`        // Load keys on startup
        loadKeys('default');`,
`${phaseOneHelpers}
        // Load keys on startup
        loadKeys('default');`,
'Phase 1 credential test function',
);

const mockLoginPattern = /function mockLogin\(\) \{[\s\S]*?\n\s*function mockLogout\(\)/;
if (mockLoginPattern.test(html)) {
  html = html.replace(mockLoginPattern, `function mockLogin() {
            window.logToSystem('⚠️ <b>Mock-Login ist in Phase 1 deaktiviert.</b><br>Bitte GitHub PAT und Gemini Key lokal eintragen und mit 🧪 TEST prüfen.', 'warning');
        }

        function mockLogout()`);
  changed = true;
  console.log('[phase1-release-hardening] disabled mock login body');
}

replaceAll('mockLogin();', "window.logToSystem('⚠️ <b>Mock-Login ist in Phase 1 deaktiviert.</b><br>Bitte Keys lokal eintragen.', 'warning');", 'remaining mock login invocations');
replaceAll('Angemeldet als Privat', 'Lokaler Workspace aktiv', 'legacy private mock login text');

if (changed) {
  writeFileSync(distIndexPath, html, 'utf8');
  console.log('[phase1-release-hardening] dist/index.html updated');
}

const forbidden = [
  'API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!',
  'gemini-1.5-flash',
  'Angemeldet als Privat',
  'OAuth Demo-Modus: Capacitor nicht verfügbar. Verwende Mock-Modus.',
  'mockLogin();',
];

for (const marker of forbidden) {
  if (html.includes(marker)) {
    console.error(`[phase1-release-hardening] forbidden legacy marker still present: ${marker}`);
    process.exit(1);
  }
}

console.log('[phase1-release-hardening] Phase 1 release checks passed.');
