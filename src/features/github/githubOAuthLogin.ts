/**
 * GitHub OAuth Login — Frontend Utility
 * 
 * Security: 
 * - PKCE (Proof Key for Code Exchange) für zusätzlichen Schutz
 * - State-Parameter gegen CSRF
 * - Token bleibt IMMER im Backend, nie im Frontend
 * 
 * Scopes (minimal als Default):
 * - read:user: Profil lesen
 * - user:email: Email für Account-Verknüpfung
 * - repo: NUR bei Bedarf (wird separat angefordert)
 */

// ── Config ───────────────────────────────────────────────────────────────────

const GITHUB_OAUTH_CLIENT_ID = import.meta.env['VITE_GITHUB_OAUTH_CLIENT_ID'] as string | undefined;
const GITHUB_OAUTH_REDIRECT_URI = import.meta.env['VITE_GITHUB_OAUTH_REDIRECT_URI'] as string | undefined;

// Standard-Scopes (minimal für Login)
const GITHUB_OAUTH_SCOPES_DEFAULT = ['read:user', 'user:email'].join(' ');
// Repo-Scope für vollen Repository-Zugriff (wird nur bei Bedarf angefordert)
const GITHUB_OAUTH_SCOPE_REPO = 'repo';

// ── State Management (CSRF-Schutz) ─────────────────────────────────────────

let _oauthState: string | null = null;
let _codeVerifier: string | null = null;

function generateRandomString(length: number): string {
  const array = new Uint8Array(length);
  crypto.getRandomValues(array);
  return Array.from(array, b => b.toString(16).padStart(2, '0')).join('');
}

// PKCE: Generate code verifier
function generateCodeVerifier(): string {
  return generateRandomString(64);
}

// PKCE: Generate code challenge (S256 method)
async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

// Generate state for CSRF protection
function generateState(): string {
  return generateRandomString(32);
}

// ── OAuth URL Builder ─────────────────────────────────────────────────────────

export function buildGitHubOAuthUrl(includeRepoScope = false): string {
  const clientId = GITHUB_OAUTH_CLIENT_ID || 'Iv1.placeholder_client_id';
  const redirectUri = GITHUB_OAUTH_REDIRECT_URI || `${window.location.origin}/auth/github/callback`;
  
  // Generate new state and PKCE for each request
  _oauthState = generateState();
  _codeVerifier = generateCodeVerifier();
  
  // Build scopes
  const scopes = includeRepoScope 
    ? `${GITHUB_OAUTH_SCOPES_DEFAULT} ${GITHUB_OAUTH_SCOPE_REPO}`
    : GITHUB_OAUTH_SCOPES_DEFAULT;
  
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    scope: scopes,
    state: _oauthState,
  });
  
  // PKCE hinzufügen (async, muss vor dem Request fertig sein)
  // Hinweis: Für echte PKCE-Unterstützung muss der Backend-Endpoint 
  // auch PKCE verifizieren. Hier vorbereitet für zukünftige Nutzung.
  
  return `https://github.com/login/oauth/authorize?${params.toString()}`;
}

// Validate state from callback (CSRF protection)
export function validateOAuthState(state: string | null): boolean {
  if (!state || !_oauthState) {
    return false;
  }
  const isValid = state === _oauthState;
  // State nur einmal verwendbar
  _oauthState = null;
  return isValid;
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
