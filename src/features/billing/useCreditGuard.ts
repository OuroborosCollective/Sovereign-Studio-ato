/**
 * useCreditGuard — Credit check + deduction hook for Sovereign Studio.
 *
 * Server ledger is authoritative: deduction is requested from the backend
 * with the HTTP-only session cookie, then the local display is updated from
 * the confirmed backend result.
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

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

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
        dispatch(openCreditPaywall({
          required: data.required ?? cost,
          available: data.available ?? credits,
        }));
        return false;
      }

      const data = await response.json().catch(() => ({})) as { deducted?: number };
      dispatch(deductCredits(data.deducted ?? cost));
      return true;
    } catch {
      dispatch(openCreditPaywall({ required: cost, available: credits }));
      return false;
    }
  };

  const refreshCredits = () => {
    dispatch(fetchUserCredits());
  };

  return { credits, chargeCredits, refreshCredits };
}
