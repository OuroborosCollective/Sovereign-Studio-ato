'use strict';

// Pure preflight for the explicitly dispatched production browser canary.
// This module cannot create sessions, credits, purchases, jobs, or pull requests.
function resolveCanaryAuthMode({ accountKey, registerCanaryAccount, runId, runAttempt }) {
  if (!/^[0-9]+$/.test(runId || '')) throw new Error('CANARY_RUN_ID_REQUIRED');
  const hasKey = typeof accountKey === 'string' && accountKey.trim().length > 0;
  if (hasKey && registerCanaryAccount) throw new Error('CANARY_AUTH_MODE_AMBIGUOUS');
  if (hasKey) return 'account-key';
  if (registerCanaryAccount !== true) throw new Error('CANARY_AUTH_REQUIRED_NO_GUEST_FALLBACK');
  // A rerun must not mint another signup balance or lose a previous account.
  if (runAttempt !== '1') throw new Error('CANARY_SIGNUP_REQUIRES_FIRST_ATTEMPT');
  return 'regular-signup';
}

function assertCanarySession(session, expectedUserId, requireSignupCredits = false) {
  if (!session || typeof session !== 'object' || Array.isArray(session)) throw new Error('CANARY_SESSION_INVALID');
  if (typeof session.id !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(session.id)) {
    throw new Error('CANARY_SESSION_ID_INVALID');
  }
  if (session.id !== expectedUserId) throw new Error('CANARY_SESSION_ID_CHANGED');
  if (session.isGuest !== false) throw new Error('CANARY_GUEST_SESSION_REJECTED');
  if (session.isBanned !== false) throw new Error('CANARY_BANNED_OR_UNKNOWN_SESSION');
  if (session.creditStateVerified !== true) throw new Error('CANARY_CREDIT_LEDGER_NOT_VERIFIED');
  if (!Number.isSafeInteger(session.credits) || session.credits < 0) throw new Error('CANARY_CREDIT_BALANCE_INVALID');
  if (requireSignupCredits && session.credits <= 0) throw new Error('CANARY_SIGNUP_CREDITS_MISSING');
}

module.exports = { resolveCanaryAuthMode, assertCanarySession };
