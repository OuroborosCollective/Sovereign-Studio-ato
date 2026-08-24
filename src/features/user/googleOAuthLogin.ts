import { Capacitor } from '@capacitor/core';

const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

const PUBLIC_GOOGLE_WEB_CLIENT_ID = '511695074775-s08le2ju1k4nl2vv3i150i6tn084b682.apps.googleusercontent.com';
const GOOGLE_CLIENT_ID_RE = /^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/;

type GoogleAuthApi = {
  initialize: (options?: {
    clientId?: string;
    scopes?: string[];
    grantOfflineAccess?: boolean;
  }) => void | Promise<void>;
  signIn: () => Promise<{
    authentication?: { idToken?: string };
  }>;
};

type GoogleConfiguredResponse = {
  configured?: boolean;
  clientIdFingerprint?: string | null;
  audienceVerificationRequired?: boolean;
  issuerVerificationRequired?: boolean;
  emailVerificationRequired?: boolean;
  rawCredentialReturned?: boolean;
};

function frontendAudienceClientId(): string {
  const configured = (import.meta.env['VITE_GOOGLE_SERVER_CLIENT_ID'] as string | undefined)?.trim()
    || (import.meta.env['VITE_GOOGLE_CLIENT_ID'] as string | undefined)?.trim()
    || PUBLIC_GOOGLE_WEB_CLIENT_ID;
  if (!GOOGLE_CLIENT_ID_RE.test(configured)) {
    throw new Error('Google-Login ist in diesem Build nicht korrekt konfiguriert.');
  }
  return configured;
}

async function sha256Hex(value: string): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Google-Login kann die Backend-Audience in dieser Umgebung nicht sicher prüfen.');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

async function verifyBackendGoogleAudience(audienceClientId: string): Promise<void> {
  const boundFetch = globalThis.fetch.bind(globalThis);
  const response = await boundFetch(`${API_BASE}/api/auth/google/configured`, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
  });
  const payload = await response.json().catch(() => ({})) as GoogleConfiguredResponse;
  if (
    !response.ok
    || payload.configured !== true
    || payload.audienceVerificationRequired !== true
    || payload.issuerVerificationRequired !== true
    || payload.emailVerificationRequired !== true
    || payload.rawCredentialReturned !== false
    || !payload.clientIdFingerprint
  ) {
    throw new Error('Google-Login ist serverseitig nicht vollständig konfiguriert.');
  }
  const frontendFingerprint = await sha256Hex(audienceClientId);
  if (frontendFingerprint !== payload.clientIdFingerprint) {
    throw new Error('Google-Login-Build und Backend verwenden nicht dieselbe sichere Audience.');
  }
}

export async function initiateGoogleOAuth(): Promise<string> {
  const audienceClientId = frontendAudienceClientId();
  await verifyBackendGoogleAudience(audienceClientId);

  const module = await import('@codetrix-studio/capacitor-google-auth');
  const GoogleAuth = module.GoogleAuth as GoogleAuthApi;

  // On Capacitor/Android, passing the Web client ID into initialize() overrides
  // the native androidClientId from capacitor.config. Leave clientId unset so
  // the native plugin consumes androidClientId + serverClientId from the synced
  // Capacitor configuration. Web still requires the Web/Server client ID.
  if (Capacitor.isNativePlatform()) {
    await GoogleAuth.initialize({
      scopes: ['profile', 'email'],
      grantOfflineAccess: false,
    });
  } else {
    await GoogleAuth.initialize({
      clientId: audienceClientId,
      scopes: ['profile', 'email'],
      grantOfflineAccess: false,
    });
  }

  const googleUser = await GoogleAuth.signIn();
  const idToken = googleUser.authentication?.idToken?.trim() || '';
  if (!idToken) {
    throw new Error('Google hat keinen verifizierbaren ID-Token geliefert.');
  }
  return idToken;
}

export function googleOAuthErrorMessage(reason: unknown): string {
  const record = typeof reason === 'object' && reason !== null ? reason as Record<string, unknown> : null;
  const code = String(record?.code ?? '').trim();
  const message = String(record?.message ?? (reason instanceof Error ? reason.message : '')).trim();
  const normalized = `${code} ${message}`.toLowerCase();

  if (code === '10' || normalized.includes('developer_error') || normalized.includes('developer error')) {
    return 'Google-Login-Konfiguration dieses Android-Builds wurde von Google abgelehnt. Bitte die aktuelle Play-Version verwenden.';
  }
  if (normalized.includes('cancel') || normalized.includes('abgebrochen')) {
    return 'Google-Login wurde abgebrochen.';
  }
  if (message.startsWith('Google-Login')) return message;
  return 'Google-Login fehlgeschlagen. Bitte erneut versuchen.';
}
