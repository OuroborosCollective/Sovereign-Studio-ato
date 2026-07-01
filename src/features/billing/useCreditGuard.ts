/**
 * useCreditGuard — Credit check + deduction hook for Sovereign Studio.
 *
 * Server ledger is authoritative: deduction is requested from the backend
 * with the HTTP-only session cookie, then the local display is updated from
 * the confirmed backend result.
 *
 * This hook subscribes to the Sovereign Redux runtime store directly instead
 * of requiring a react-redux <Provider>. BuilderContainer is a product shell
 * used by both the live app and contract/smoke tests; the credit guard must
 * not make the visible shell depend on a UI wrapper to render.
 *
 * Authenticated users are charged against the server ledger. Anonymous chat
 * previews do not have a server-side user ledger yet, so this guard must not
 * emit a fake X-User-Id or consume the billing endpoint before a real session
 * exists.
 *
 * Usage:
 *   const { credits, chargeCredits, refreshCredits } = useCreditGuard();
 *   const ok = await chargeCredits('gemini-2.0-flash', estimatedTokens);
 *   if (!ok) return; // paywall was opened automatically
 *
 * Issue #458
 */

import { useCallback, useSyncExternalStore } from 'react';
import { store } from '../../store';
import { useUserStore } from '../../user/useUserStore';
import {
  deductCredits,
  openCreditPaywall,
  fetchUserCredits,
} from './billingSlice';
import { calculateCredits } from './costConfig';

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

function getCreditsSnapshot(): number {
  return store.getState().billing.credits;
}

export interface UseCreditGuardResult {
  credits: number;
  /**
   * Charges credits for the given cost entry.
   * Returns true when there were enough credits (deduction applied).
   * Returns false when insufficient — the credit paywall is opened automatically.
   */
  chargeCredits(costId: string, tokenCount?: number): Promise<boolean>;
  /** Re-fetches the credit balance from the backend. */
  refreshCredits(): void;
}

export function useCreditGuard(): UseCreditGuardResult {
  const credits = useSyncExternalStore(
    store.subscribe,
    getCreditsSnapshot,
    getCreditsSnapshot,
  );

  const chargeCredits = useCallback(async (costId: string, tokenCount = 0): Promise<boolean> => {
    const cost = calculateCredits(costId, tokenCount);

    // Free operations (unknown cost id or 0-cost) always proceed.
    if (cost === 0) return true;

    const sessionUser = useUserStore.getState().user;
    if (!sessionUser) {
      // No authenticated ledger exists yet. Let the chat/worker route proceed as
      // an anonymous preview instead of inventing a client-side billing identity.
      return true;
    }

    try {
      const response = await fetch(`${API_BASE}/api/billing/deduct`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ costId, amount: cost, tokenCount }),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => ({})) as {
          available?: number;
          required?: number;
        };
        store.dispatch(openCreditPaywall({
          required: data.required ?? cost,
          available: data.available ?? credits,
        }));
        return false;
      }

      const data = await response.json().catch(() => ({})) as { deducted?: number };
      store.dispatch(deductCredits(data.deducted ?? cost));
      return true;
    } catch {
      store.dispatch(openCreditPaywall({ required: cost, available: credits }));
      return false;
    }
  }, [credits]);

  const refreshCredits = useCallback(() => {
    void store.dispatch(fetchUserCredits());
  }, []);

  return { credits, chargeCredits, refreshCredits };
}
