import { useState, useEffect, useCallback, useMemo } from 'react';

interface Subscription {
  id: string;
  plan: 'free' | 'pro' | 'enterprise';
  status: 'active' | 'canceled' | 'past_due' | 'trialing';
  currentPeriodEnd: string;
  cancelAtPeriodEnd: boolean;
}

interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: 'paid' | 'open' | 'void';
  date: string;
  pdfUrl: string;
}

interface BillingState {
  subscription: Subscription | null;
  invoices: Invoice[];
  loading: boolean;
  error: string | null;
}

export const useBilling = () => {
  const [state, setState] = useState<BillingState>({
    subscription: null,
    invoices: [],
    loading: true,
    error: null,
  });

  const fetchBillingData = useCallback(async () => {
    try {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      
      const mockSubscription: Subscription = {
        id: 'sub_123',
        plan: 'pro',
        status: 'active',
        currentPeriodEnd: new Date(Date.now() + 2592000000).toISOString(),
        cancelAtPeriodEnd: false,
      };

      const mockInvoices: Invoice[] = [
        {
          id: 'inv_001',
          amount: 2900,
          currency: 'eur',
          status: 'paid',
          date: new Date().toISOString(),
          pdfUrl: '#',
        },
      ];

      setState({
        subscription: mockSubscription,
        invoices: mockInvoices,
        loading: false,
        error: null,
      });
    } catch (err) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: err instanceof Error ? err.message : 'Fehler beim Laden der Abrechnungsdaten',
      }));
    }
  }, []);

  const purchase = async (planId: string) => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await fetchBillingData();
    } catch (err) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: 'Fehler beim Abschließen des Kaufs',
      }));
    }
  };

  const updateSubscription = async (planId: string) => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await fetchBillingData();
    } catch (err) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: 'Fehler beim Aktualisieren des Plans',
      }));
    }
  };

  const cancelSubscription = async () => {
    setState((prev) => ({ ...prev, loading: true }));
    try {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await fetchBillingData();
    } catch (err) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: 'Fehler beim Kündigen des Abonnements',
      }));
    }
  };

  useEffect(() => {
    fetchBillingData();
  }, [fetchBillingData]);

  const currentPlanId = useMemo(() => state.subscription?.plan ?? null, [state.subscription]);
  const isProcessing = state.loading;

  return {
    ...state,
    isProcessing,
    currentPlanId,
    refresh: fetchBillingData,
    purchase,
    updateSubscription,
    cancelSubscription,
  };
};