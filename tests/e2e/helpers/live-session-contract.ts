/** Assertions over real HTTP observations; these functions never create a session. */
function record(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error('LIVE_SESSION_RESPONSE_INVALID');
  }
  return value as Record<string, unknown>;
}

export function requireLoginAccountId(status: number, payload: unknown): string {
  if (status !== 200) throw new Error(`LIVE_AUTH_HTTP_${status}`);
  const user = record(payload);
  if (typeof user.id !== 'string' || !user.id.trim()) {
    throw new Error('LIVE_AUTH_ACCOUNT_ID_MISSING');
  }
  return user.id.trim();
}

export function requireSameOrigin(actualUrl: string, appUrl: string): void {
  const actual = new URL(actualUrl);
  const expected = new URL(appUrl);
  if (!['http:', 'https:'].includes(expected.protocol) || actual.origin !== expected.origin) {
    throw new Error('LIVE_AUTH_AGENT_ORIGIN_MISMATCH');
  }
}

export function requireVerifiedSessionIdentity(
  status: number,
  payload: unknown,
  expectedAccountId: string,
): string {
  if (status !== 200) throw new Error(`LIVE_SESSION_HTTP_${status}`);
  const user = record(payload);
  if (!expectedAccountId || user.id !== expectedAccountId) {
    throw new Error('LIVE_SESSION_ACCOUNT_MISMATCH');
  }
  if (user.isGuest !== false || user.isBanned !== false) {
    throw new Error('LIVE_SESSION_AUTHENTICATED_IDENTITY_REQUIRED');
  }
  if (user.creditStateVerified !== true) {
    throw new Error('LIVE_SESSION_CREDIT_READBACK_UNVERIFIED');
  }
  return expectedAccountId;
}
