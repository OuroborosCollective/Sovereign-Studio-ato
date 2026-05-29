import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const distIndexPath = resolve('dist/index.html');

if (!existsSync(distIndexPath)) {
  console.warn('[release-html-runtime-fix] dist/index.html not found. Skipping.');
  process.exit(0);
}

let html = readFileSync(distIndexPath, 'utf8');
let changed = false;

function replaceAllText(from, to, label) {
  if (!html.includes(from)) {
    console.warn(`[release-html-runtime-fix] text not found: ${label}`);
    return;
  }
  html = html.split(from).join(to);
  changed = true;
  console.log(`[release-html-runtime-fix] patched ${label}`);
}

function replaceRegex(pattern, to, label) {
  if (!pattern.test(html)) {
    console.warn(`[release-html-runtime-fix] pattern not found: ${label}`);
    return;
  }
  html = html.replace(pattern, to);
  changed = true;
  console.log(`[release-html-runtime-fix] patched ${label}`);
}

const runtimeHelpers = `
        // --- Phase 1 Release Runtime: local user-owned credentials ---
        const GEMINI_TEXT_MODELS = ['gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash'];
        const GEMINI_TTS_MODELS = ['gemini-2.5-flash-preview-tts'];

        function getStoredCredential(prefix, uid) {
            try {
                const scoped = localStorage.getItem(prefix + '_' + uid) || '';
                const fallback = localStorage.getItem(prefix + '_default') || '';
                return (scoped || fallback || '').trim();
            } catch (_) {
                return '';
            }
        }

        function normalizeBearerToken(token) {
            return (token || '').trim().replace(/^Bearer\\s+/i, '');
        }

        function getGitHubPAT() {
            const uid = (typeof currentUserUid !== 'undefined' && currentUserUid) ? currentUserUid : 'default';
            const el = document.getElementById('gh-pat');
            let pat = normalizeBearerToken(el?.value || '');
            if (!pat) {
                pat = normalizeBearerToken(getStoredCredential('sov_pat', uid));
                if (el && pat) el.value = pat;
            }
            return pat;
        }

        function getGeminiKey() {
            const uid = (typeof currentUserUid !== 'undefined' && currentUserUid) ? currentUserUid : 'default';
            const el = document.getElementById('gemini-key');
            let key = (el?.value || '').trim();
            if (!key) {
                key = getStoredCredential('sov_gemini', uid);
                if (el && key) el.value = key;
            }
            return key;
        }

        function githubHeaders(accept) {
            const pat = getGitHubPAT();
            const headers = {
                Accept: accept || 'application/vnd.github.v3+json',
                'X-GitHub-Api-Version': '2022-11-28'
            };
            if (pat) headers.Authorization = 'Bearer ' + pat;
            return headers;
        }

        async function githubErrorMessage(response, fallback) {
            let detail = '';
            try {
                const data = await response.clone().json();
                detail = data?.message ? ' - ' + data.message : '';
            } catch (_) {}
            if (response.status === 401) return 'GitHub 401: Token fehlt, ist abgelaufen oder hat keinen Repo-Zugriff.' + detail;
            if (response.status === 403) return 'GitHub 403: Token hat zu wenig Rechte oder API Rate Limit ist erreicht.' + detail;
            if (response.status === 404) return 'GitHub 404: Repository, Branch oder Datei nicht gefunden. Bei privaten Repos braucht der PAT mindestens repo/contents Zugriff.' + detail;
            return (fallback || 'GitHub API Fehler') + ' Status: ' + response.status + detail;
        }

        function geminiUrl(model) {
            return 'https://generativelanguage.googleapis.com/v1beta/models/' + encodeURIComponent(model) + ':generateContent';
        }

        async function geminiErrorMessage(response, model) {
            let detail = '';
            try {
                const data = await response.clone().json();
                detail = data?.error?.message || data?.message || '';
            } catch (_) {}
            if (response.status === 400) return 'Gemini 400: Anfrage ungültig für Modell ' + model + (detail ? ' - ' + detail : '');
            if (response.status === 401) return 'Gemini 401: API Key fehlt oder ist ungültig.' + (detail ? ' - ' + detail : '');
            if (response.status === 403) return 'Gemini 403: API Key hat keine Berechtigung, ist eingeschränkt oder die API ist im Google-Projekt nicht aktiviert.' + (detail ? ' - ' + detail : '');
            if (response.status === 404) return 'Gemini 404: Modell ' + model + ' ist für diesen Key/Standort nicht verfügbar oder veraltet.' + (detail ? ' - ' + detail : '');
            if (response.status === 429) return 'Gemini 429: Rate Limit oder Kontingent erschöpft.' + (detail ? ' - ' + detail : '');
            return 'Gemini API Fehler ' + response.status + ' bei Modell ' + model + (detail ? ' - ' + detail : '');
        }
`;

const callGeminiAPI = `        async function callGeminiAPI(prompt, system) {
            const activeApiKey = getGeminiKey();
            if (!activeApiKey) throw new Error('Gemini API Key fehlt. Bitte eigenen Key eintragen und erneut synchronisieren.');

            const awarenessInjection = repoContext ? '\n\n[GLOBAL PROJECT AWARENESS: ' + repoContext + ']\nBerücksichtige dieses Wissen bei jeder Architekturentscheidung und Code-Generierung.' : '';
            const finalSystemMsg = system + awarenessInjection;
            const body = JSON.stringify({
                contents: [{ parts: [{ text: prompt }] }],
                systemInstruction: { parts: [{ text: finalSystemMsg }] }
            });

            let lastError = null;
            for (const model of GEMINI_TEXT_MODELS) {
                try {
                    const response = await fetch(geminiUrl(model), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': activeApiKey },
                        body
                    });
                    if (!response.ok) {
                        lastError = new Error(await geminiErrorMessage(response, model));
                        if ([400, 401, 403, 429].includes(response.status)) throw lastError;
                        continue;
                    }
                    const data = await response.json();
                    const text = data?.candidates?.[0]?.content?.parts?.map(part => part.text || '').join('') || '';
                    if (!text) throw new Error('Gemini lieferte keine Text-Antwort.');
                    return text;
                } catch (err) {
                    lastError = err;
                    if (String(err?.message || '').includes('Gemini 401') || String(err?.message || '').includes('Gemini 403')) break;
                }
            }
            throw lastError || new Error('Gemini API konnte kein verfügbares Modell erreichen.');
        }`;

const callGeminiTTSAPI = `        async function callGeminiTTSAPI(prompt) {
            const activeApiKey = getGeminiKey();
            if (!activeApiKey) throw new Error('Gemini API Key fehlt.');

            let lastError = null;
            for (const model of GEMINI_TTS_MODELS) {
                try {
                    const response = await fetch(geminiUrl(model), {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': activeApiKey },
                        body: JSON.stringify({
                            contents: [{ parts: [{ text: prompt }] }],
                            generationConfig: {
                                responseModalities: ['AUDIO'],
                                speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: 'Aoede' } } }
                            }
                        })
                    });
                    if (!response.ok) {
                        lastError = new Error(await geminiErrorMessage(response, model));
                        continue;
                    }
                    const data = await response.json();
                    const inlineData = data?.candidates?.[0]?.content?.parts?.find(part => part.inlineData)?.inlineData;
                    if (inlineData) return inlineData;
                    throw new Error('Keine Audio-Daten erhalten.');
                } catch (err) {
                    lastError = err;
                }
            }
            throw lastError || new Error('Gemini TTS konnte kein verfügbares Audio-Modell erreichen.');
        }`;

const fetchFileContent = `        async function fetchFileContent(path, branch) {
            branch = branch || 'main';
            const safePath = path.split('/').map(encodeURIComponent).join('/');
            const safeBranch = encodeURIComponent(branch);
            try {
                const headers = githubHeaders('application/vnd.github.raw+json');
                const response = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName + '/contents/' + safePath + '?ref=' + safeBranch, { headers });
                if (response.ok) return await response.text();

                const rawResponse = await fetch('https://raw.githubusercontent.com/' + repoOwner + '/' + repoName + '/' + safeBranch + '/' + safePath);
                if (rawResponse.ok) return await rawResponse.text();

                window.logToSystem('⚠️ <b>Datei konnte nicht geladen werden:</b> <code>' + path + '</code><br>' + await githubErrorMessage(response, 'GitHub Datei-Fehler'), 'warning');
                return '';
            } catch (err) {
                window.logToSystem('⚠️ <b>Datei-Ladefehler:</b> <code>' + path + '</code><br>' + err.message, 'warning');
                return '';
            }
        }`;

const phaseOneHelpers = `
        // --- Phase 1: credential UX ---
        window.saveKeys = saveKeys;
        window.loadKeys = loadKeys;
        window.testPhaseOneCredentials = async function() {
            try {
                saveKeys();
                const pat = getGitHubPAT();
                const gemini = getGeminiKey();
                if (!pat) {
                    window.logToSystem('⚠️ <b>GitHub PAT fehlt.</b><br>Öffentliche Repo-Reads können funktionieren, aber private Repos, Push und PRs brauchen einen User-PAT.', 'warning');
                } else {
                    const ghRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName, { headers: githubHeaders() });
                    if (!ghRes.ok) throw new Error(await githubErrorMessage(ghRes, 'GitHub Verbindung fehlgeschlagen.'));
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

replaceRegex(/\s*\/\/ --- API & Tree ---\s*function changeRepository\(\) \{/, `
        // --- API & Tree ---
${runtimeHelpers}
        function changeRepository() {`, 'runtime helpers');

replaceRegex(/\s*async function callGeminiAPI\(prompt, system\) \{[\s\S]*?\n\s*\}\s*\n\s*async function callGeminiTTSAPI\(prompt\) \{/, `
${callGeminiAPI}

        async function callGeminiTTSAPI(prompt) {`, 'callGeminiAPI');

replaceRegex(/\s*async function callGeminiTTSAPI\(prompt\) \{[\s\S]*?\n\s*\}\s*\n\s*function playWavFromPcm\(/, `
${callGeminiTTSAPI}

        function playWavFromPcm(`, 'callGeminiTTSAPI');

replaceRegex(/const patInput = document\.getElementById\('gh-pat'\);[\s\S]*?if \(!repoRes\.ok\) throw new Error\('Kein Zugriff auf das Repository\. Status: ' \+ repoRes\.status \+ '\. Hast du einen PAT hinterlegt\?'\);/, `const headers = githubHeaders();
                const repoRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName, { headers });
                if (!repoRes.ok) throw new Error(await githubErrorMessage(repoRes, 'Kein Zugriff auf das Repository.'));`, 'repo tree auth');

replaceRegex(/\s*async function fetchFileContent\(path, branch\) \{[\s\S]*?\n\s*\}\s*\n\s*function updateBatchUI\(\)/, `
${fetchFileContent}

        function updateBatchUI()`, 'fetchFileContent');

replaceRegex(/document\.addEventListener\('DOMContentLoaded', function\(\) \{ fetchRepoTree\(\); if \(window\.innerWidth < 1024\) switchTab\('explorer'\); \}\);/, `document.addEventListener('DOMContentLoaded', function() {
            if (typeof loadKeys === 'function') loadKeys((typeof currentUserUid !== 'undefined' && currentUserUid) ? currentUserUid : 'default');
            setTimeout(fetchRepoTree, 50);
            if (window.innerWidth < 1024) switchTab('explorer');
        });`, 'startup key load order');

replaceRegex(/function saveKeys\(\) \{[\s\S]*?\n\s*function loadKeys\(uid\) \{[\s\S]*?\n\s*\}/, `function saveKeys() {
            const uid = currentUserUid || 'default';
            const pat = document.getElementById('gh-pat')?.value || '';
            const gemini = document.getElementById('gemini-key')?.value || '';
            localStorage.setItem('sov_pat_' + uid, pat);
            localStorage.setItem('sov_gemini_' + uid, gemini);
            if (uid !== 'default') {
                if (pat && !localStorage.getItem('sov_pat_default')) localStorage.setItem('sov_pat_default', pat);
                if (gemini && !localStorage.getItem('sov_gemini_default')) localStorage.setItem('sov_gemini_default', gemini);
            }
        }

        function loadKeys(uid) {
            const effectiveUid = uid || 'default';
            const patEl = document.getElementById('gh-pat');
            const geminiEl = document.getElementById('gemini-key');
            const pat = typeof getStoredCredential === 'function' ? getStoredCredential('sov_pat', effectiveUid) : (localStorage.getItem('sov_pat_' + effectiveUid) || localStorage.getItem('sov_pat_default') || '');
            const gemini = typeof getStoredCredential === 'function' ? getStoredCredential('sov_gemini', effectiveUid) : (localStorage.getItem('sov_gemini_' + effectiveUid) || localStorage.getItem('sov_gemini_default') || '');
            if (patEl && pat) patEl.value = pat;
            if (geminiEl && gemini) geminiEl.value = gemini;
        }`, 'key storage');

replaceRegex(/if \(window\.GoogleAuth\) \{\s*useCapacitorOAuth = true;\s*return true;\s*\}/, `const plugin = window.GoogleAuth || window.Capacitor?.Plugins?.GoogleAuth;
                if (plugin) {
                    window.GoogleAuth = plugin;
                    useCapacitorOAuth = true;
                    return true;
                }`, 'GoogleAuth detection');

replaceRegex(/const result = await window\.GoogleAuth\.signIn\(\);\s*updateAuthUI\(\{[\s\S]*?photoURL: result\.user\.imageURL\s*\}\);/, `const result = await window.GoogleAuth.signIn();
                    const rawUser = result?.user || result || {};
                    updateAuthUI({
                        uid: rawUser.uid || rawUser.id || rawUser.email || 'google_user',
                        displayName: rawUser.displayName || rawUser.name || rawUser.email || 'Google User',
                        photoURL: rawUser.photoURL || rawUser.imageURL || rawUser.imageUrl || rawUser.picture || ''
                    });`, 'GoogleAuth result normalization');

replaceRegex(/catch\(e\) \{\s*window\.logToSystem\('⚠️ <b>OAuth Fehler:<\/b> ' \+ e\.message, 'error'\);\s*mockLogin\(\);\s*\}/, `catch(e) {
                    window.logToSystem('⚠️ <b>OAuth Fehler:</b> ' + e.message + '<br>Google Login ist optional. Deine lokal eingetragenen GitHub/Gemini Keys bleiben aktiv.', 'error');
                    return;
                }`, 'no mock login after OAuth failure');

replaceRegex(/\/\/ Fallback to mock for web\s*window\.logToSystem\('⚠️ <b>OAuth Demo-Modus:<\/b> Capacitor nicht verfügbar\. Verwende Mock-Modus\.', 'warning'\);\s*mockLogin\(\);/, `window.logToSystem('⚠️ <b>Google OAuth nicht verfügbar:</b> Die App läuft weiter mit lokal gespeicherten User-Keys.', 'warning');`, 'no mock login fallback');

replaceRegex(/function mockLogin\(\) \{[\s\S]*?\n\s*function mockLogout\(\)/, `function mockLogin() {
            window.logToSystem('⚠️ <b>Mock-Login ist in Phase 1 deaktiviert.</b><br>Bitte GitHub PAT und Gemini Key lokal eintragen und mit 🧪 TEST prüfen.', 'warning');
        }

        function mockLogout()`, 'disable mock login body');

replaceRegex(/if \(user\) \{\s*currentUserUid = user\.uid;\s*loadKeys\(user\.uid\);/, `if (user) {
                saveKeys();
                currentUserUid = user.uid || 'default';
                loadKeys(currentUserUid);`, 'preserve keys on login');

replaceRegex(/\} else \{\s*currentUserUid = 'default';\s*loadKeys\('default'\);/, `} else {
                saveKeys();
                currentUserUid = 'default';
                loadKeys('default');`, 'preserve keys on logout');

replaceRegex(/\/\/ Load keys on startup\s*loadKeys\('default'\);/, `${phaseOneHelpers}
        // Load keys on startup
        loadKeys('default');`, 'Phase 1 test helper');

replaceAllText('GitHub PAT:', 'GitHub PAT (User):', 'GitHub PAT label');
replaceAllText('Gemini Key:', 'Gemini Key (User):', 'Gemini Key label');
replaceAllText('Canvas Auto-Auth aktiv', 'Eigener Gemini API Key', 'Gemini placeholder');
replaceAllText('</svg> Login', '</svg> Google optional', 'Google button label');
replaceAllText('GitHub Token fehlt (Optional)', 'GitHub PAT fehlt', 'setup modal GitHub title');
replaceAllText('Um Code zu pushen oder PRs zu erstellen, benötigst du einen', 'Für private Repos, Push und PRs trägt jeder User seinen eigenen', 'setup modal GitHub copy');
replaceAllText('Der Architekt hat deinen persönlichen Workspace & Keys geladen.', 'Der Architekt nutzt deine lokal gespeicherten Workspace-Keys.', 'workspace key copy');
replaceAllText('API Fehler 404 - Bitte GitHub PAT und/oder Gemini Key eingeben!', 'Gemini 404: Modell oder API-Zugriff nicht verfügbar.', 'legacy ambiguous 404 text');
replaceAllText('gemini-1.5-flash', 'gemini-2.5-flash', 'legacy Gemini model string');
replaceAllText('Angemeldet als Privat', 'Lokaler Workspace aktiv', 'legacy private mock login text');

if (!html.includes('testPhaseOneCredentials()')) {
  replaceRegex(/<input type="password" id="gemini-key"([^>]+)>/, `<input type="password" id="gemini-key"$1>
                <button onclick="saveKeys(); window.logToSystem('🔐 <b>Keys lokal gespeichert.</b><br>Keine Tokens werden in die App eingebettet oder an Sovereign Studio übertragen.', 'success')" class="px-2 py-1 bg-emerald-100 border border-emerald-300 text-emerald-800 rounded text-[10px] font-bold hover:bg-emerald-200 transition-colors">💾 SPEICHERN</button>
                <button onclick="testPhaseOneCredentials()" class="px-2 py-1 bg-sky-100 border border-sky-300 text-sky-800 rounded text-[10px] font-bold hover:bg-sky-200 transition-colors">🧪 TEST</button>`, 'save/test controls');
}

if (changed) {
  writeFileSync(distIndexPath, html, 'utf8');
  console.log('[release-html-runtime-fix] dist/index.html updated');
} else {
  console.warn('[release-html-runtime-fix] no changes applied');
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
    console.error(`[release-html-runtime-fix] forbidden legacy marker still present: ${marker}`);
    process.exit(1);
  }
}

console.log('[release-html-runtime-fix] Phase 1 release checks passed.');
