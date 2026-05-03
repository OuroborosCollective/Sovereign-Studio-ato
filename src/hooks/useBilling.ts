import { useState, useCallback } from 'react';

interface BillingState {
  isLoading: boolean;
  error: string | null;
}

interface PurchaseResponse {
  success: boolean;
  url?: string;
  orderId?: string;
}

export const useBilling = () => {
  const [state, setState] = useState<BillingState>({
    isLoading: false,
    error: null,
  });

  const purchase = useCallback(async (planId: string): Promise<PurchaseResponse> => {
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    
    try {
      const response = await fetch('/api/billing/purchase', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ planId }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.message || 'Purchase failed');
      }

      const data: PurchaseResponse = await response.json();
      return data;
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      setState((prev) => ({ ...prev, error: errorMessage }));
      throw err;
    } finally {
      setState((prev) => ({ ...prev, isLoading: false }));
    }
  }, []);

  return {
    isLoading: state.isLoading,
    error: state.error,
    purchase,
  };
};