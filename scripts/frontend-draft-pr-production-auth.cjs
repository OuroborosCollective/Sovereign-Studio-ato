'use strict';

// Pure preflight for the explicitly dispatched production browser canary.
// This module cannot create sessions, credits, purchases, jobs, or pull requests.
function requireCanaryAccountKey(accountKey) {
  if (typeof accountKey !== 'string' || !accountKey.trim()) {
    throw new Error('CANARY_AUTH_REQUIRED_NO_GUEST_FALLBACK');
  }
}

function assertCanarySession(session, expectedUserId) {
  if (!session || typeof session !== 'object' || Array.isArray(session)) throw new Error('CANARY_SESSION_INVALID');
  if (typeof session.id !== 'string' || !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(session.id)) {
    throw new Error('CANARY_SESSION_ID_INVALID');
  }
  if (session.id !== expectedUserId) throw new Error('CANARY_SESSION_ID_CHANGED');
  if (session.isGuest !== false) throw new Error('CANARY_GUEST_SESSION_REJECTED');
  if (session.isBanned !== false) throw new Error('CANARY_BANNED_OR_UNKNOWN_SESSION');
  if (session.creditStateVerified !== true) throw new Error('CANARY_CREDIT_LEDGER_NOT_VERIFIED');
  if (!Number.isSafeInteger(session.credits) || session.credits < 0) throw new Error('CANARY_CREDIT_BALANCE_INVALID');
  if (session.credits <= 0) throw new Error('CANARY_POSITIVE_PERSISTED_CREDITS_REQUIRED');
}

module.exports = { requireCanaryAccountKey, assertCanarySession };
