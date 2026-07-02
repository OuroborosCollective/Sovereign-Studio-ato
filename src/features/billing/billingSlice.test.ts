import { describe, it, expect } from 'vitest';
import reducer, {
  BillingState,
  Subscription,
  fetchBillingData
} from './billingSlice';

describe('billingSlice reducer', () => {
  const initialState: BillingState = {
    subscription: null,
    invoices: [],
    availablePackages: [],
    packages: [],
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
