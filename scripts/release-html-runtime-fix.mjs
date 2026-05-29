import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';

const distIndexPath = resolve('dist/index.html');

if (!existsSync(distIndexPath)) {
  console.warn('[release-html-runtime-fix] dist/index.html not found. Skipping runtime auth hotfix.');
  process.exit(0);
}

let html = readFileSync(distIndexPath, 'utf8');
let changed = false;

const replaceOnce = (from, to, label) => {
  if (html.includes(from)) {
    html = html.replace(from, to);
    changed = true;
    console.log(`[release-html-runtime-fix] patched ${label}`);
  } else {
    console.warn(`[release-html-runtime-fix] pattern not found for ${label}`);
  }
};

const runtimeHelpers = `
        // --- Release Runtime Auth Fixes ---
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
                'Accept': accept || 'application/vnd.github.v3+json',
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
`;

replaceOnce(
`        // --- API & Tree ---
        function changeRepository() {`,
`        // --- API & Tree ---
${runtimeHelpers}
        function changeRepository() {`,
'credential helper injection',
);

replaceOnce(
`            const customKey = document.getElementById('gemini-key').value.trim();
            const activeApiKey = customKey;`,
`            const activeApiKey = getGeminiKey();
            if (!activeApiKey) throw new Error('Gemini API Key fehlt. Bitte Key eintragen und erneut synchronisieren.');`,
'Gemini key loading',
);

replaceOnce(
`            const customKey = document.getElementById('gemini-key').value.trim();
            const activeApiKey = customKey;`,
`            const activeApiKey = getGeminiKey();
            if (!activeApiKey) throw new Error('Gemini API Key fehlt.');`,
'Gemini TTS key loading',
);

replaceOnce(
`                const patInput = document.getElementById('gh-pat');
                const pat = patInput ? patInput.value.trim() : '';
                const headers = pat ? { 'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github.v3+json' } : {};
                
                const repoRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName, { headers });
                if (!repoRes.ok) throw new Error('Kein Zugriff auf das Repository. Status: ' + repoRes.status + '. Hast du einen PAT hinterlegt?');`,
`                const headers = githubHeaders();
                const repoRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName, { headers });
                if (!repoRes.ok) throw new Error(await githubErrorMessage(repoRes, 'Kein Zugriff auf das Repository.'));`,
'GitHub tree auth headers',
);

replaceOnce(
`                const treeRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName + '/git/trees/' + defaultBranch + '?recursive=1', { headers });
                if (!treeRes.ok) throw new Error('Konnte den Tree für Branch \' + defaultBranch + '\' nicht laden.');`,
`                const treeRes = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName + '/git/trees/' + encodeURIComponent(defaultBranch) + '?recursive=1', { headers });
                if (!treeRes.ok) throw new Error(await githubErrorMessage(treeRes, 'Konnte den Tree für Branch ' + defaultBranch + ' nicht laden.'));`,
'GitHub tree error detail',
);

replaceOnce(
`        async function fetchFileContent(path, branch) {
            branch = branch || 'main';
            try {
                let response = await fetch('https://raw.githubusercontent.com/' + repoOwner + '/' + repoName + '/' + branch + '/' + path);
                if (!response.ok) {
                    const pat = document.getElementById('gh-pat').value.trim();
                    const headers = pat ? { 'Authorization': 'Bearer ' + pat, 'Accept': 'application/vnd.github.v3.raw' } : {};
                    response = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName + '/contents/' + path + '?ref=' + branch, { headers });
                    if (!response.ok) return "";
                }
                return await response.text();
            } catch { return ""; }
        }`,
`        async function fetchFileContent(path, branch) {
            branch = branch || 'main';
            const safePath = path.split('/').map(encodeURIComponent).join('/');
            const safeBranch = encodeURIComponent(branch);
            try {
                const headers = githubHeaders('application/vnd.github.raw+json');
                let response = await fetch('https://api.github.com/repos/' + repoOwner + '/' + repoName + '/contents/' + safePath + '?ref=' + safeBranch, { headers });
                if (response.ok) return await response.text();

                const rawResponse = await fetch('https://raw.githubusercontent.com/' + repoOwner + '/' + repoName + '/' + safeBranch + '/' + safePath);
                if (rawResponse.ok) return await rawResponse.text();

                window.logToSystem('⚠️ <b>Datei konnte nicht geladen werden:</b> <code>' + path + '</code><br>' + await githubErrorMessage(response, 'GitHub Datei-Fehler'), 'warning');
                return "";
            } catch (err) {
                window.logToSystem('⚠️ <b>Datei-Ladefehler:</b> <code>' + path + '</code><br>' + err.message, 'warning');
                return "";
            }
        }`,
'authenticated file loading',
);

replaceOnce(
`        document.getElementById('autofix-pr-btn').onclick = () => runArchitectWorkflow('Behebe folgenden Bruch in meiner Matrix:\\n\\n' + activePR.lastErrorLog, true);
        document.addEventListener('DOMContentLoaded', function() { fetchRepoTree(); if (window.innerWidth < 1024) switchTab('explorer'); });`,
`        document.getElementById('autofix-pr-btn').onclick = () => runArchitectWorkflow('Behebe folgenden Bruch in meiner Matrix:\\n\\n' + activePR.lastErrorLog, true);
        document.addEventListener('DOMContentLoaded', function() {
            if (typeof loadKeys === 'function') loadKeys((typeof currentUserUid !== 'undefined' && currentUserUid) ? currentUserUid : 'default');
            setTimeout(fetchRepoTree, 50);
            if (window.innerWidth < 1024) switchTab('explorer');
        });`,
'startup key load order',
);

replaceOnce(
`        function saveKeys() {
            const pat = document.getElementById('gh-pat')?.value || '';
            const gemini = document.getElementById('gemini-key')?.value || '';
            localStorage.setItem('sov_pat_' + currentUserUid, pat);
            localStorage.setItem('sov_gemini_' + currentUserUid, gemini);
        }

        function loadKeys(uid) {
            const patEl = document.getElementById('gh-pat');
            const geminiEl = document.getElementById('gemini-key');
            if (patEl) patEl.value = localStorage.getItem('sov_pat_' + uid) || '';
            if (geminiEl) geminiEl.value = localStorage.getItem('sov_gemini_' + uid) || '';
        }`,
`        function saveKeys() {
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
            const pat = getStoredCredential('sov_pat', effectiveUid);
            const gemini = getStoredCredential('sov_gemini', effectiveUid);
            if (patEl && pat) patEl.value = pat;
            if (geminiEl && gemini) geminiEl.value = gemini;
        }`,
'scoped key fallback storage',
);

replaceOnce(
`                if (window.GoogleAuth) {
                    useCapacitorOAuth = true;
                    return true;
                }`,
`                const plugin = window.GoogleAuth || window.Capacitor?.Plugins?.GoogleAuth;
                if (plugin) {
                    window.GoogleAuth = plugin;
                    useCapacitorOAuth = true;
                    return true;
                }`,
'Capacitor GoogleAuth detection',
);

replaceOnce(
`                    const result = await window.GoogleAuth.signIn();
                    updateAuthUI({
                        uid: result.user.uid,
                        displayName: result.user.displayName,
                        photoURL: result.user.imageURL
                    });`,
`                    const result = await window.GoogleAuth.signIn();
                    const rawUser = result?.user || result || {};
                    updateAuthUI({
                        uid: rawUser.uid || rawUser.id || rawUser.email || 'google_user',
                        displayName: rawUser.displayName || rawUser.name || rawUser.email || 'Google User',
                        photoURL: rawUser.photoURL || rawUser.imageURL || rawUser.imageUrl || rawUser.picture || ''
                    });`,
'GoogleAuth result normalization',
);

replaceOnce(
`            if (user) {
                currentUserUid = user.uid;
                loadKeys(user.uid);`,
`            if (user) {
                saveKeys();
                currentUserUid = user.uid || 'default';
                loadKeys(currentUserUid);`,
'preserve keys on Google user switch',
);

replaceOnce(
`            } else {
                currentUserUid = 'default';
                loadKeys('default');`,
`            } else {
                saveKeys();
                currentUserUid = 'default';
                loadKeys('default');`,
'preserve keys on logout',
);

if (changed) {
  writeFileSync(distIndexPath, html, 'utf8');
  console.log('[release-html-runtime-fix] dist/index.html updated');
} else {
  console.warn('[release-html-runtime-fix] no changes applied');
}
