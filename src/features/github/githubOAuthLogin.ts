import { App } from '@capacitor/app';
import { Browser } from '@capacitor/browser';
import { Capacitor } from '@capacitor/core';

const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export interface GitHubOAuthResult {
  success: boolean;
  code?: string;
  state?: string;
  codeVerifier?: string;
  error?: string;
}

interface GitHubOAuthInitResult {
  authUrl: string;
  state: string;
  codeVerifier: string;
  callbackOrigin: string;
  openerOrigin: string;
}

interface GitHubOAuthCallbackMessage {
  type?: string;
  code?: string;
  state?: string;
  error?: string;
}

async function initializeGitHubOAuth(
  openerOrigin: string,
): Promise<GitHubOAuthInitResult> {
  const response = await fetch(`${API_BASE}/api/auth/github/init`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      opener_origin: openerOrigin,
    }),
  });
  const payload = await response.json().catch(() => ({})) as Partial<GitHubOAuthInitResult> & { error?: string };
  if (!response.ok) throw new Error(payload.error || `GitHub OAuth Init HTTP ${response.status}`);
  if (
    !payload.authUrl
    || !payload.state
    || !payload.codeVerifier
    || !payload.callbackOrigin
    || !payload.openerOrigin
  ) {
    throw new Error('GitHub OAuth Init lieferte keine vollständige State-/PKCE-/Rückkanal-Evidence.');
  }
  if (payload.openerOrigin !== openerOrigin) {
    throw new Error('GitHub OAuth Init bestätigte nicht den aktuellen App-Origin.');
  }
  return payload as GitHubOAuthInitResult;
}

export function validateOAuthState(returnedState: string | null, expectedState: string | null): boolean {
  return Boolean(returnedState && expectedState && returnedState === expectedState);
}

const NATIVE_CALLBACK_PROTOCOL = 'com.arestudio.nocode.aab:';
const NATIVE_CALLBACK_HOST = 'auth';
const NATIVE_CALLBACK_PATH = '/github/callback';

function readNativeOAuthCallback(url: string): GitHubOAuthCallbackMessage | null {
  try {
    const parsed = new URL(url);
    if (
      parsed.protocol !== NATIVE_CALLBACK_PROTOCOL
      || parsed.hostname !== NATIVE_CALLBACK_HOST
      || parsed.pathname !== NATIVE_CALLBACK_PATH
    ) return null;
    return {
      code: parsed.searchParams.get('code') || undefined,
      state: parsed.searchParams.get('state') || undefined,
      error: parsed.searchParams.get('error') || undefined,
    };
  } catch {
    return null;
  }
}

async function initiateNativeGitHubOAuth(
  initialized: GitHubOAuthInitResult,
  onMessage: ((result: GitHubOAuthResult) => void) | undefined,
  timeout: number,
): Promise<GitHubOAuthResult> {
  return await new Promise<GitHubOAuthResult>((resolve) => {
    let settled = false;
    let listener: { remove: () => Promise<void> } | null = null;
    let timeoutId = 0;
    const finish = (result: GitHubOAuthResult) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timeoutId);
      if (listener) void listener.remove();
      void Browser.close().catch(() => undefined);
      resolve(result);
      onMessage?.(result);
    };
    timeoutId = window.setTimeout(
      () => finish({ success: false, error: 'Zeitüberschreitung. Bitte erneut versuchen.' }),
      timeout,
    );

    void App.addListener('appUrlOpen', ({ url }) => {
      const callback = readNativeOAuthCallback(url);
      if (!callback) return;
      if (callback.error) {
        finish({ success: false, error: callback.error });
        return;
      }
      if (!callback.code || !callback.state) {
        finish({ success: false, error: 'GitHub OAuth Rückkanal ist unvollständig.' });
        return;
      }
      if (!validateOAuthState(callback.state, initialized.state)) {
        finish({ success: false, error: 'GitHub OAuth State stimmt nicht mit der gestarteten Anmeldung überein.' });
        return;
      }
      finish({
        success: true,
        code: callback.code,
        state: callback.state,
        codeVerifier: initialized.codeVerifier,
      });
    }).then((handle) => {
      listener = handle;
      if (settled) {
        void handle.remove();
        return;
      }
      void Browser.open({ url: initialized.authUrl }).catch((error) => {
        finish({
          success: false,
          error: error instanceof Error ? error.message : 'GitHub-Browser konnte nicht geöffnet werden.',
        });
      });
    }).catch((error) => {
      finish({
        success: false,
        error: error instanceof Error ? error.message : 'Nativer GitHub-Rückkanal konnte nicht registriert werden.',
      });
    });
  });
}

export async function initiateGitHubOAuth(
  onMessage?: (result: GitHubOAuthResult) => void,
  timeout = 5 * 60 * 1000,
): Promise<GitHubOAuthResult> {
  try {
    const openerOrigin = window.location.origin;
    const initialized = await initializeGitHubOAuth(openerOrigin);
    if (Capacitor.isNativePlatform()) {
      return await initiateNativeGitHubOAuth(initialized, onMessage, timeout);
    }
    const width = 600;
    const height = 700;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    const popup = window.open(
      initialized.authUrl,
      'github-oauth',
      `width=${width},height=${height},left=${left},top=${top},popup=yes`,
    );
    if (!popup) return { success: false, error: 'Popup wurde blockiert. Bitte Popups erlauben und erneut versuchen.' };

    return await new Promise((resolve) => {
      let settled = false;
      const finish = (result: GitHubOAuthResult) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        window.clearInterval(closedPoll);
        window.removeEventListener('message', handleMessage);
        if (!popup.closed) popup.close();
        resolve(result);
        onMessage?.(result);
      };
      const handleMessage = (event: MessageEvent<GitHubOAuthCallbackMessage>) => {
        if (event.origin !== initialized.callbackOrigin || event.source !== popup) return;
        const data = event.data;
        if (data?.type === 'GITHUB_OAUTH_ERROR') {
          finish({ success: false, error: data.error || 'Autorisierung fehlgeschlagen' });
          return;
        }
        if (data?.type !== 'GITHUB_OAUTH_SUCCESS' || !data.code || !data.state) return;
        if (!validateOAuthState(data.state, initialized.state)) {
          finish({ success: false, error: 'GitHub OAuth State stimmt nicht mit der gestarteten Anmeldung überein.' });
          return;
        }
        finish({
          success: true,
          code: data.code,
          state: data.state,
          codeVerifier: initialized.codeVerifier,
        });
      };
      const timeoutId = window.setTimeout(
        () => finish({ success: false, error: 'Zeitüberschreitung. Bitte erneut versuchen.' }),
        timeout,
      );
      const closedPoll = window.setInterval(() => {
        if (popup.closed) {
          finish({
            success: false,
            error: 'GitHub-Fenster wurde geschlossen, bevor der bestätigte Rückkanal eingetroffen ist.',
          });
        }
      }, 500);
      window.addEventListener('message', handleMessage);
    });
  } catch (error) {
    const result = { success: false, error: error instanceof Error ? error.message : String(error) };
    onMessage?.(result);
    return result;
  }
}

export function redirectToGitHubOAuth(): never {
  throw new Error('Direkter OAuth-Redirect ist deaktiviert. State und PKCE müssen über den Backend-Init-Popup-Flow laufen.');
}

export function extractOAuthCodeFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('code');
}

// Backend configuration is the runtime truth. A missing configuration is shown
// by the real init endpoint instead of hiding the button based on APK env data.
export function isGitHubOAuthConfigured(): boolean {
  return true;
}
