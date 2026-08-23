import { configureStore } from '@reduxjs/toolkit';
import { afterEach, describe, it, expect, vi } from 'vitest';
import reducer, {
  BillingState,
  Subscription,
  capturePayPalOrder,
  fetchBillingData,
  fetchEnabledPaymentMethods,
  fetchUserCredits,
} from './billingSlice';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('billingSlice reducer', () => {
  const initialState: BillingState = {
    subscription: null,
    invoices: [],
    availablePackages: [],
    packages: [],
    paymentMethods: [],
    loading: false,
    error: null,
    tier: 'free',
    isPaywallActive: true,
    isSubscribed: false,
    isTrialing: false,
    credits: 0,
    isPaywallOpen: false,
    insufficientFor: null,
  };

  it('should handle fetchBillingData.fulfilled with active subscription', () => {
    const subscription: Subscription = {
      id: 'sub_1',
      status: 'active',
      planId: 'plan_1',
      tier: 'pro',
      currentPeriodEnd: '2025-01-01',
      cancelAtPeriodEnd: false,
    };

    const action = {
      type: fetchBillingData.fulfilled.type,
      payload: { subscription, invoices: [], availablePackages: [] }
    };
    const state = reducer(initialState, action);

    expect(state.tier).toBe('pro');
    expect(state.isSubscribed).toBe(true);
    expect(state.isPaywallActive).toBe(false);
    expect(state.isTrialing).toBe(false);
  });

  it('should handle fetchBillingData.fulfilled with trialing subscription', () => {
    const subscription: Subscription = {
      id: 'sub_1',
      status: 'trialing',
      planId: 'plan_1',
      tier: 'pro',
      currentPeriodEnd: '2025-01-01',
      cancelAtPeriodEnd: false,
    };

    const action = {
      type: fetchBillingData.fulfilled.type,
      payload: { subscription, invoices: [], availablePackages: [] }
    };
    const state = reducer(initialState, action);

    expect(state.tier).toBe('pro');
    expect(state.isSubscribed).toBe(true);
    expect(state.isPaywallActive).toBe(false);
    expect(state.isTrialing).toBe(true);
  });

  it('should handle fetchBillingData.fulfilled with canceled subscription', () => {
    const subscription: Subscription = {
      id: 'sub_1',
      status: 'canceled',
      planId: 'plan_1',
      tier: 'pro',
      currentPeriodEnd: '2025-01-01',
      cancelAtPeriodEnd: false,
    };

    const action = {
      type: fetchBillingData.fulfilled.type,
      payload: { subscription, invoices: [], availablePackages: [] }
    };
    const state = reducer(initialState, action);

    expect(state.isSubscribed).toBe(false);
    expect(state.isPaywallActive).toBe(true);
  });

  it('uses only existing read-only billing endpoints for initial runtime state', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/api/billing')) {
        return new Response(JSON.stringify({
          subscription: null,
          invoices: [],
          availablePackages: [],
          packages: [],
        }), { status: 200, headers: { 'Content-Type': 'application/json' } });
      }
      if (url.endsWith('/api/billing/payment-methods')) {
        return new Response(JSON.stringify({ methods: [] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.endsWith('/api/billing/credits')) {
        return new Response(JSON.stringify({ credits: 17 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({ error: 'unexpected endpoint' }), { status: 404 });
    });
    const store = configureStore({ reducer: { billing: reducer } });

    await store.dispatch(fetchBillingData());
    await store.dispatch(fetchEnabledPaymentMethods());
    await store.dispatch(fetchUserCredits());

    const calls = fetchMock.mock.calls.map(([input]) => String(input));
    expect(calls).toEqual([
      expect.stringMatching(/\/api\/billing$/),
      expect.stringMatching(/\/api\/billing\/payment-methods$/),
      expect.stringMatching(/\/api\/billing\/credits$/),
    ]);
    expect(calls.some(url => url.endsWith('/api/billing/cancel'))).toBe(false);
    expect(calls.some(url => url.endsWith('/api/billing/restore'))).toBe(false);
    expect(store.getState().billing.credits).toBe(17);
  });

  it('captures a confirmed PayPal order through the exact endpoint and trusts only the returned balance', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ok: true,
      orderId: 'order-1',
      creditsAdded: 25,
      newBalance: 41,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    const store = configureStore({ reducer: { billing: reducer } });

    const result = await store.dispatch(capturePayPalOrder('order-1'));

    expect(result.type).toBe(capturePayPalOrder.fulfilled.type);
    expect(fetchMock).toHaveBeenCalledWith(
      'https://sovereign-backend.arelorian.de/api/billing/purchase/paypal/capture',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orderId: 'order-1' }),
      }),
    );
    expect(store.getState().billing.credits).toBe(41);
  });

  it('does not invent a credit balance when PayPal capture is rejected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      error: 'capture_not_confirmed',
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' },
    }));
    const store = configureStore({
      reducer: { billing: reducer },
      preloadedState: { billing: { ...initialState, credits: 7 } },
    });

    const result = await store.dispatch(capturePayPalOrder('order-unconfirmed'));

    expect(result.type).toBe(capturePayPalOrder.rejected.type);
    expect(store.getState().billing.credits).toBe(7);
  });

  it('should handle null subscription', () => {
    const action = {
      type: fetchBillingData.fulfilled.type,
      payload: { subscription: null, invoices: [], availablePackages: [] }
    };
    const state = reducer(initialState, action);

    expect(state.tier).toBe('free');
    expect(state.isSubscribed).toBe(false);
    expect(state.isPaywallActive).toBe(true);
  });
});
