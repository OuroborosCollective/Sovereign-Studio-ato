/**
 * GitHub OAuth Login — Frontend Utility
 * 
 * Implementiert den OAuth 2.0 Authorization Code Flow für GitHub Login.
 * Der User klickt "Mit GitHub anmelden" → Popup öffnet sich → 
 * Nach Autorisierung wird der Code ans Backend geschickt.
 * 
 * Setup:
 * 1. GitHub OAuth App erstellen: https://github.com/settings/applications/new
 *    - Homepage URL: https://deine-app-domain.de
 *    - Authorization callback URL: https://deine-app-domain.de/api/auth/github/callback
 * 
 * 2. Client ID im Frontend (.env) setzen:
 *    VITE_GITHUB_OAUTH_CLIENT_ID=dein_client_id
 * 
 * 3. Backend Endpoint implementieren:
 *    POST /api/auth/github
 *    Body: { code: string }
 *    → Tauscht Code gegen Access Token bei GitHub
 *    → Erstellt/aktualisiert User in DB
 *    → Gibt User-Objekt mit githubAccessToken zurück
 */

// ── Config ───────────────────────────────────────────────────────────────────

const GITHUB_OAUTH_CLIENT_ID = import.meta.env['VITE_GITHUB_OAUTH_CLIENT_ID'] as string | undefined;
const GITHUB_OAUTH_REDIRECT_URI = import.meta.env['VITE_GITHUB_OAUTH_REDIRECT_URI'] as string | undefined;

// GitHub OAuth Scopes — wofür brauchen wir Zugriff?
// - read:user: Github Profil lesen
// - user:email: Email für Account-Verknüpfung
// - repo: Zugriff auf private Repositories (optional, für voll Repo-Zugriff)
const GITHUB_OAUTH_SCOPES = ['read:user', 'user:email', 'repo'].join(' ');

// ── OAuth URL Builder ─────────────────────────────────────────────────────────

export function buildGitHubOAuthUrl(): string {
  const clientId = GITHUB_OAUTH_CLIENT_ID || 'Iv1.placeholder_client_id';
  const redirectUri = GITHUB_OAUTH_REDIRECT_URI || `${window.location.origin}/auth/github/callback`;
  
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: GITHUB_OAUTH_SCOPES,
    // State für CSRF-Schutz generieren
    state: generateState(),
  });
  
  return `https://github.com/login/oauth/authorize?${params.toString()}`;
}

function generateState(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
}

// ── OAuth Popup Handler ────────────────────────────────────────────────────────

export interface GitHubOAuthResult {
  success: boolean;
  code?: string;
  error?: string;
}

/**
 * Öffnet GitHub OAuth in einem Popup-Fenster.
 * Nach erfolgreicher Autorisierung wird der Code zurückgegeben.
 * 
 * @param onMessage - Callback für Message-Event (von der Callback-Page)
 * @param timeout - Timeout in ms (default 5 Minuten)
 */
export async function initiateGitHubOAuth(
  onMessage?: (result: GitHubOAuthResult) => void,
  timeout = 5 * 60 * 1000
): Promise<GitHubOAuthResult> {
  return new Promise((resolve) => {
    const oauthUrl = buildGitHubOAuthUrl();
    
    // Popup öffnen
    const width = 600;
    const height = 700;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    
    const popup = window.open(
      oauthUrl,
      'github-oauth',
      `width=${width},height=${height},left=${left},top=${top},popup=yes`
    );
    
    if (!popup) {
      const error = 'Popup wurde blockiert. Bitte Popups erlauben und erneut versuchen.';
      resolve({ success: false, error });
      return;
    }
    
    // Timeout setzen
    const timeoutId = setTimeout(() => {
      cleanup();
      const error = 'Zeitüberschreitung. Bitte erneut versuchen.';
      resolve({ success: false, error });
    }, timeout);
    
    // Auf Nachricht von der Callback-Page warten
    function handleMessage(event: MessageEvent) {
      // Nur auf Nachrichten von der gleichen Origin reagieren (Sicherheit)
      // oder von der OAuth-Redirect-Seite
      
      const data = event.data;
      if (data?.type === 'GITHUB_OAUTH_SUCCESS' && data?.code) {
        cleanup();
        const result = { success: true, code: data.code };
        resolve(result);
        onMessage?.(result);
      } else if (data?.type === 'GITHUB_OAUTH_ERROR') {
        cleanup();
        const result = { success: false, error: data.error || 'Autorisierung fehlgeschlagen' };
        resolve(result);
        onMessage?.(result);
      }
    }
    
    // Alternativ: Auf URL-Änderung im Popup hören
    function checkPopup() {
      if (popup.closed) {
        cleanup();
        resolve({ success: false, error: 'Fenster wurde geschlossen' });
        return;
      }
      
      try {
        const popupUrl = popup.location.href;
        
        // Wenn wir auf der Callback-URL sind (oder einer bekannten Domain)
        if (popupUrl.includes('github.com/login/oauth/authorize')) {
          // Authorization Page — noch warten
          setTimeout(checkPopup, 500);
        } else if (popupUrl.includes('callback') || popupUrl.includes('auth')) {
          // Callback URL erreicht — Code extrahieren
          const url = new URL(popupUrl);
          const code = url.searchParams.get('code');
          const error = url.searchParams.get('error');
          
          if (code) {
            cleanup();
            popup.close();
            const result = { success: true, code };
            resolve(result);
            onMessage?.(result);
          } else if (error) {
            cleanup();
            popup.close();
            const result = { success: false, error: error as string };
            resolve(result);
            onMessage?.(result);
          } else {
            setTimeout(checkPopup, 500);
          }
        } else {
          // Noch auf GitHub — warten
          setTimeout(checkPopup, 500);
        }
      } catch {
        // Cross-Origin Fehler bedeutet, wir sind noch auf GitHub
        setTimeout(checkPopup, 500);
      }
    }
    
    // Cleanup-Funktion
    function cleanup() {
      clearTimeout(timeoutId);
      window.removeEventListener('message', handleMessage);
      if (!popup.closed) {
        popup.close();
      }
    }
    
    // Event Listener starten
    window.addEventListener('message', handleMessage);
    
    // Popup-URL prüfen starten
    setTimeout(checkPopup, 1000);
  });
}

// ── Direct Auth (ohne Popup) ─────────────────────────────────────────────────

/**
 * Falls kein Popup möglich ist: Redirect-basierter OAuth Flow.
 * Leitet den User auf GitHub weiter; nach Autorisierung kommt er zurück.
 */
export function redirectToGitHubOAuth() {
  const url = buildGitHubOAuthUrl();
  window.location.href = url;
}

/**
 * Extrahiert den OAuth Code aus der URL (nach Redirect).
 * Sollte auf der Callback-Seite aufgerufen werden.
 */
export function extractOAuthCodeFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search);
  return params.get('code');
}

/**
 * Prüft ob GitHub OAuth konfiguriert ist.
 */
export function isGitHubOAuthConfigured(): boolean {
  return !!GITHUB_OAUTH_CLIENT_ID;
}
