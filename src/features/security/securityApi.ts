const API_BASE = (
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined)?.trim()
  || 'https://sovereign-backend.arelorian.de'
).replace(/\/$/, '');

export interface PasskeySummary {
  id: string;
  label: string;
  transports: string[];
  deviceType?: string | null;
  backedUp: boolean;
  createdAt?: string | null;
  lastUsedAt?: string | null;
}

export interface AccountKeySummary {
  id: string;
  keyHint: string;
  label: string;
  scopes: string[];
  createdAt?: string | null;
  lastUsedAt?: string | null;
}

export interface SecurityPolicy {
  requirePurchaseStepUp: boolean;
  purchaseThresholdEur: number;
  requireExpensiveRouteStepUp: boolean;
  routeThresholdCredits: number;
  preferPasskey: boolean;
}

export interface SecurityOverview {
  passkeys: PasskeySummary[];
  accountKeys: AccountKeySummary[];
  policy: SecurityPolicy;
  passkeyAvailable: boolean;
  error?: string;
}

export interface SecurityUser {
  id: string;
  email: string;
  displayName: string;
  role: 'user' | 'admin' | 'superadmin';
  credits: number;
  subscriptionStatus: string;
  isBanned: boolean;
  createdAt: string;
  avatarUrl?: string | null;
  googleId?: string | null;
  githubId?: string | null;
  githubUsername?: string | null;
}

interface PublicKeyOptionsEnvelope extends Record<string, unknown> {
  challengeId: string;
  publicKey?: Record<string, unknown>;
}

function bytesToBase64Url(value: ArrayBuffer | Uint8Array): string {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlToArrayBuffer(value: unknown): ArrayBuffer {
  if (typeof value !== 'string' || !value) throw new Error('Passkey challenge fehlt.');
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized + '='.repeat((4 - normalized.length % 4) % 4);
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  return bytes.buffer;
}

function creationOptions(envelope: PublicKeyOptionsEnvelope): PublicKeyCredentialCreationOptions {
  const root = (envelope.publicKey ?? envelope) as Record<string, unknown>;
  const user = root.user as Record<string, unknown> | undefined;
  const excludeCredentials = Array.isArray(root.excludeCredentials)
    ? root.excludeCredentials.map(value => {
        const item = value as Record<string, unknown>;
        return {
          ...item,
          type: 'public-key',
          id: base64UrlToArrayBuffer(item.id),
        } as unknown as PublicKeyCredentialDescriptor;
      })
    : undefined;
  return {
    ...root,
    challenge: base64UrlToArrayBuffer(root.challenge),
    user: user ? { ...user, id: base64UrlToArrayBuffer(user.id) } : undefined,
    excludeCredentials,
  } as unknown as PublicKeyCredentialCreationOptions;
}

function requestOptions(envelope: PublicKeyOptionsEnvelope): PublicKeyCredentialRequestOptions {
  const root = (envelope.publicKey ?? envelope) as Record<string, unknown>;
  const allowCredentials = Array.isArray(root.allowCredentials)
    ? root.allowCredentials.map(value => {
        const item = value as Record<string, unknown>;
        return {
          ...item,
          type: 'public-key',
          id: base64UrlToArrayBuffer(item.id),
        } as unknown as PublicKeyCredentialDescriptor;
      })
    : undefined;
  return {
    ...root,
    challenge: base64UrlToArrayBuffer(root.challenge),
    allowCredentials,
  } as unknown as PublicKeyCredentialRequestOptions;
}

function serializeCredential(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response;
  const base = {
    id: credential.id,
    rawId: bytesToBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
  if ('attestationObject' in response) {
    const attestation = response as AuthenticatorAttestationResponse;
    return {
      ...base,
      response: {
        clientDataJSON: bytesToBase64Url(attestation.clientDataJSON),
        attestationObject: bytesToBase64Url(attestation.attestationObject),
        transports: typeof attestation.getTransports === 'function' ? attestation.getTransports() : [],
      },
    };
  }
  if ('authenticatorData' in response && 'signature' in response) {
    const assertion = response as AuthenticatorAssertionResponse;
    return {
      ...base,
      response: {
        clientDataJSON: bytesToBase64Url(assertion.clientDataJSON),
        authenticatorData: bytesToBase64Url(assertion.authenticatorData),
        signature: bytesToBase64Url(assertion.signature),
        userHandle: assertion.userHandle ? bytesToBase64Url(assertion.userHandle) : null,
      },
    };
  }
  throw new Error('Unbekannte Passkey-Antwort.');
}

async function jsonRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  });
  const payload = await response.json().catch(() => ({})) as T & { error?: string; blocker?: string };
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`) as Error & {
      status?: number;
      blocker?: string;
      payload?: unknown;
    };
    error.status = response.status;
    error.blocker = payload.blocker;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function requirePasskeyBrowser(): void {
  if (!window.isSecureContext || !('credentials' in navigator) || typeof PublicKeyCredential === 'undefined') {
    throw new Error('Passkeys benötigen HTTPS und einen WebAuthn-fähigen Browser.');
  }
}

export async function getSecurityOverview(): Promise<SecurityOverview> {
  return jsonRequest<SecurityOverview>('/api/security/overview');
}

export async function updateSecurityPolicy(changes: Partial<SecurityPolicy>): Promise<SecurityPolicy> {
  const result = await jsonRequest<{ ok: boolean; policy: SecurityPolicy }>('/api/security/policy', {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
  return result.policy;
}

export async function registerPasskey(label = 'Dieses Gerät'): Promise<void> {
  requirePasskeyBrowser();
  const options = await jsonRequest<PublicKeyOptionsEnvelope>('/api/security/passkeys/register/options', {
    method: 'POST',
    body: '{}',
  });
  const credential = await navigator.credentials.create({ publicKey: creationOptions(options) });
  if (!(credential instanceof PublicKeyCredential)) throw new Error('Passkey-Erstellung wurde abgebrochen.');
  await jsonRequest('/api/security/passkeys/register/verify', {
    method: 'POST',
    body: JSON.stringify({
      challengeId: options.challengeId,
      label,
      credential: serializeCredential(credential),
    }),
  });
}

export async function deletePasskey(id: string): Promise<void> {
  await jsonRequest(`/api/security/passkeys/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function loginWithPasskey(email = ''): Promise<SecurityUser> {
  requirePasskeyBrowser();
  const options = await jsonRequest<PublicKeyOptionsEnvelope>('/api/auth/passkey/options', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
  const credential = await navigator.credentials.get({ publicKey: requestOptions(options) });
  if (!(credential instanceof PublicKeyCredential)) throw new Error('Passkey-Anmeldung wurde abgebrochen.');
  return jsonRequest<SecurityUser>('/api/auth/passkey/verify', {
    method: 'POST',
    body: JSON.stringify({
      challengeId: options.challengeId,
      credential: serializeCredential(credential),
    }),
  });
}

export async function createAccountKey(label = 'Sovereign Account Key'): Promise<{ id: string; key: string; keyHint: string; warning: string }> {
  return jsonRequest('/api/security/account-keys', {
    method: 'POST',
    body: JSON.stringify({ label }),
  });
}

export async function revokeAccountKey(id: string): Promise<void> {
  await jsonRequest(`/api/security/account-keys/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function loginWithAccountKey(key: string): Promise<SecurityUser> {
  return jsonRequest<SecurityUser>('/api/auth/account-key', {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
}

async function passkeyStepUp(action: string, context: Record<string, unknown>): Promise<string> {
  requirePasskeyBrowser();
  const options = await jsonRequest<PublicKeyOptionsEnvelope>('/api/security/step-up/options', {
    method: 'POST',
    body: JSON.stringify({ action, context }),
  });
  const credential = await navigator.credentials.get({ publicKey: requestOptions(options) });
  if (!(credential instanceof PublicKeyCredential)) throw new Error('Sicherheitsbestätigung wurde abgebrochen.');
  const result = await jsonRequest<{ token: string }>('/api/security/step-up/verify', {
    method: 'POST',
    body: JSON.stringify({
      challengeId: options.challengeId,
      credential: serializeCredential(credential),
    }),
  });
  return result.token;
}

async function accountKeyStepUp(action: string, context: Record<string, unknown>, key: string): Promise<string> {
  const result = await jsonRequest<{ token: string }>('/api/security/step-up/account-key', {
    method: 'POST',
    body: JSON.stringify({ action, context, key }),
  });
  return result.token;
}

export async function requestStepUp(
  action: 'credit_purchase' | 'expensive_llm_route',
  context: Record<string, unknown>,
): Promise<string> {
  try {
    return await passkeyStepUp(action, context);
  } catch (error) {
    const typed = error as Error & { status?: number; blocker?: string };
    if (typed.status !== 409 && typed.blocker !== 'passkey_missing') throw error;
    const key = window.prompt('Kein Passkey registriert. Optional Sovereign Account Key eingeben:');
    if (!key) throw new Error('Sicherheitsbestätigung wurde nicht durchgeführt.');
    return accountKeyStepUp(action, context, key.trim());
  }
}

export async function fetchWithStepUp(
  input: RequestInfo | URL,
  init: RequestInit,
  action: 'credit_purchase' | 'expensive_llm_route',
): Promise<Response> {
  const first = await fetch(input, { credentials: 'include', ...init });
  if (first.status !== 428) return first;
  const challenge = await first.clone().json().catch(() => ({})) as { context?: Record<string, unknown> };
  const context = challenge.context ?? {};
  const token = await requestStepUp(action, context);
  return fetch(input, {
    credentials: 'include',
    ...init,
    headers: {
      ...(init.headers ?? {}),
      'X-Step-Up-Token': token,
    },
  });
}
