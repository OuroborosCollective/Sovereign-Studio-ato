/**
 * useCreditGuard — Credit check + deduction hook for Sovereign Studio.
 *
 * Uses optimistic client-side deduction (via Redux) and fires a background
 * backend sync so the server ledger stays consistent.  If the backend is
 * unreachable the deduction is kept locally and reconciled on next login.
 *
 * Usage:
 *   const { credits, chargeCredits, refreshCredits } = useCreditGuard();
 *   const ok = await chargeCredits('gemini-2.0-flash', estimatedTokens);
 *   if (!ok) return; // paywall was opened automatically
 *
 * Issue #458
 */

import { useAppDispatch, useAppSelector } from '../../store/hooks';
import {
  deductCredits,
  openCreditPaywall,
  fetchUserCredits,
} from './billingSlice';
import { calculateCredits } from './costConfig';

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
  const credits = useAppSelector((s) => s.billing.credits);
  const dispatch = useAppDispatch();

  const chargeCredits = async (costId: string, tokenCount = 0): Promise<boolean> => {
    const cost = calculateCredits(costId, tokenCount);

    // Free operations (unknown cost id or 0-cost) always proceed
    if (cost === 0) return true;

    if (credits < cost) {
      dispatch(openCreditPaywall({ required: cost, available: credits }));
      return false;
    }

    // Optimistic deduction — UI updates immediately
    dispatch(deductCredits(cost));

    // Background sync to backend — fire and forget
    const userId = (localStorage.getItem('sovereign-user-id') ?? '').trim();
    fetch('/api/billing/deduct', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(userId ? { 'X-User-Id': userId } : {}),
      },
      body: JSON.stringify({ costId, amount: cost, tokenCount }),
    }).catch(() => {
      // Backend unreachable — deduction stays local.
      // Server balance will be reconciled on next successful login/sync.
    });

    return true;
  };

  const refreshCredits = () => {
    dispatch(fetchUserCredits());
  };

  return { credits, chargeCredits, refreshCredits };
}
