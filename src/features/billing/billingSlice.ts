import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';

export type SubscriptionTier = 'free' | 'pro' | 'enterprise' | 'custom';

export interface Subscription {
  id: string;
  status: 'active' | 'canceled' | 'past_due' | 'trialing' | 'incomplete';
  planId: string;
  tier: SubscriptionTier;
  currentPeriodEnd: string;
  cancelAtPeriodEnd: boolean;
}

export interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: string;
  date: string;
  pdfUrl?: string;
}

export interface BillingPackage {
  id: string;
  name: string;
  price: number;
  currency: string;
  interval: 'month' | 'year' | 'once';
  features: string[];
  tier: SubscriptionTier;
  isPopular?: boolean;
  isRecommended?: boolean;
}

export interface BillingState {
  subscription: Subscription | null;
  invoices: Invoice[];
  availablePackages: BillingPackage[];
  packages: BillingPackage[];
  loading: boolean;
  error: string | null;
  // Paywall & Access Logic
  tier: SubscriptionTier;
  isPaywallActive: boolean;
  isSubscribed: boolean;
  isTrialing: boolean;
}

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
};

export const fetchBillingData = createAsyncThunk(
  'billing/fetchBillingData',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch('/api/billing');
      if (!response.ok) {
        throw new Error('Fehler beim Abrufen der Abrechnungsdaten');
      }
      return await response.json();
    } catch (error: any) {
      return rejectWithValue(error.message || 'Serverfehler');
    }
  }
);

export const purchasePackage = createAsyncThunk(
  'billing/purchasePackage',
  async (packageId: string, { rejectWithValue }) => {
    try {
      const response = await fetch('/api/billing/purchase', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ packageId }),
      });
      if (!response.ok) {
        throw new Error('Kauf konnte nicht abgeschlossen werden');
      }
      return await response.json();
    } catch (error: any) {
      return rejectWithValue(error.message || 'Fehler beim Kauf');
    }
  }
);

export const cancelSubscription = createAsyncThunk(
  'billing/cancelSubscription',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch('/api/billing/cancel', {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error('Kündigung konnte nicht verarbeitet werden');
      }
      return await response.json();
    } catch (error: any) {
      return rejectWithValue(error.message || 'Fehler bei der Kündigung');
    }
  }
);

export const restorePurchases = createAsyncThunk(
  'billing/restorePurchases',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch('/api/billing/restore', { method: 'POST' });
      if (!response.ok) {
        throw new Error('Wiederherstellung fehlgeschlagen');
      }
      return await response.json();
    } catch (error: any) {
      return rejectWithValue(error.message || 'Fehler bei der Wiederherstellung');
    }
  }
);

const updateAccessState = (state: BillingState, subscription: Subscription | null) => {
  if (!subscription) {
    state.tier = 'free';
    state.isSubscribed = false;
    state.isPaywallActive = true;
    state.isTrialing = false;
    return;
  }

  state.subscription = subscription;
  state.tier = subscription.tier || 'free';
  state.isSubscribed = ['active', 'trialing'].includes(subscription.status);
  state.isTrialing = subscription.status === 'trialing';
  state.isPaywallActive = !['active', 'trialing'].includes(subscription.status) || subscription.tier === 'free';
};

const billingSlice = createSlice({
  name: 'billing',
  initialState,
  reducers: {
    resetBillingState: (state) => {
      Object.assign(state, initialState);
    },
    setBillingError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
    togglePaywall: (state, action: PayloadAction<boolean>) => {
      state.isPaywallActive = action.payload;
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchBillingData.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchBillingData.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        state.invoices = action.payload.invoices || [];
        state.availablePackages = action.payload.availablePackages || [];
        state.packages = action.payload.packages || action.payload.availablePackages || [];
        updateAccessState(state, action.payload.subscription);
      })
      .addCase(fetchBillingData.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(purchasePackage.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(purchasePackage.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        updateAccessState(state, action.payload.subscription);
      })
      .addCase(purchasePackage.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(cancelSubscription.pending, (state) => {
        state.loading = true;
      })
      .addCase(cancelSubscription.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        updateAccessState(state, action.payload.subscription);
      })
      .addCase(cancelSubscription.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(restorePurchases.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(restorePurchases.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        updateAccessState(state, action.payload.subscription);
      })
      .addCase(restorePurchases.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { resetBillingState, setBillingError, togglePaywall } = billingSlice.actions;

// Selectors
export const selectSubscription = (state: { billing: BillingState }) => state.billing.subscription;
export const selectIsSubscribed = (state: { billing: BillingState }) => state.billing.isSubscribed;
export const selectIsLoading = (state: { billing: BillingState }) => state.billing.loading;
export const selectBillingError = (state: { billing: BillingState }) => state.billing.error;
export const selectAvailablePackages = (state: { billing: BillingState }) => state.billing.availablePackages;
export const selectInvoices = (state: { billing: BillingState }) => state.billing.invoices;
export const selectPackages = (state: { billing: BillingState }) => state.billing.packages;
export const selectSubscriptionTier = (state: { billing: BillingState }) => state.billing.tier;
export const selectIsPaywallActive = (state: { billing: BillingState }) => state.billing.isPaywallActive;

export default billingSlice.reducer;