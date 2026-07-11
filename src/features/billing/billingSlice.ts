import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';
import type { RootState } from '../../store';
import { fetchWithStepUp } from '../security/securityApi';

const API_BASE: string =
  (import.meta.env['VITE_ADMIN_API_BASE'] as string | undefined) ||
  'https://sovereign-backend.arelorian.de';

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
  credits?: number;  // Credits included in this package (from backend)
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
  // Credits system — Issue #458
  credits: number;
  isPaywallOpen: boolean;
  insufficientFor: { required: number; available: number } | null;
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
  // Credits — Issue #458. Server ledger is the source of truth; default must not fake a balance.
  credits: 0,
  isPaywallOpen: false,
  insufficientFor: null,
};

export const fetchBillingData = createAsyncThunk(
  'billing/fetchBillingData',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch(`${API_BASE}/api/billing`, { credentials: 'include' });
      if (!response.ok) {
        throw new Error('Fehler beim Abrufen der Abrechnungsdaten');
      }
      return await response.json();
    } catch (error: any) {
      return rejectWithValue(error.message || 'Serverfehler');
    }
  }
);

export interface PurchaseArgs {
  packageId: string;
  paymentMethod?: string;
  [key: string]: unknown;
}

export interface PurchaseResult {
  ok?: boolean;
  orderId?: string;
  approvalUrl?: string;
  redirectUrl?: string;
  walletAddress?: string;
  coinType?: string;
  amountEur?: number;
  credits?: number;
  packageName?: string;
  note?: string;
  creditsAdded?: number;
  newBalance?: number;
  subscription?: Subscription | null;
}

export const purchasePackage = createAsyncThunk(
  'billing/purchasePackage',
  async (args: string | PurchaseArgs, { rejectWithValue }) => {
    const payload: PurchaseArgs =
      typeof args === 'string' ? { packageId: args } : args;
    try {
      const response = await fetchWithStepUp(`${API_BASE}/api/billing/purchase`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }, 'credit_purchase');
      if (!response.ok) {
        const err = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(err.error || 'Kauf konnte nicht abgeschlossen werden');
      }
      return (await response.json()) as PurchaseResult;
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Fehler beim Kauf';
      return rejectWithValue(msg);
    }
  }
);

export const capturePayPalOrder = createAsyncThunk(
  'billing/capturePayPalOrder',
  async (orderId: string, { rejectWithValue }) => {
    try {
      const response = await fetch(`${API_BASE}/api/billing/purchase/paypal/capture`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ orderId }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(err.error || 'PayPal Capture fehlgeschlagen');
      }
      return (await response.json()) as PurchaseResult;
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Fehler beim Capture';
      return rejectWithValue(msg);
    }
  }
);

export const fetchEnabledPaymentMethods = createAsyncThunk(
  'billing/fetchEnabledPaymentMethods',
  async (_, { rejectWithValue }) => {
    try {
      const res = await fetch(`${API_BASE}/api/billing/payment-methods`, { credentials: 'include' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return (await res.json()) as { methods: { type: string; label: string }[] };
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Fehler';
      return rejectWithValue(msg);
    }
  }
);

export const cancelSubscription = createAsyncThunk(
  'billing/cancelSubscription',
  async (_, { rejectWithValue }) => {
    try {
      const response = await fetch(`${API_BASE}/api/billing/cancel`, {
        method: 'POST',
        credentials: 'include',
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
      const response = await fetch(`${API_BASE}/api/billing/restore`, {
        method: 'POST',
        credentials: 'include',
      });
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
  const isSubscribed = subscription.status === 'active' || subscription.status === 'trialing';
  state.isSubscribed = isSubscribed;
  state.isTrialing = subscription.status === 'trialing';
  state.isPaywallActive = !isSubscribed || subscription.tier === 'free';
};

// Thunk: fetch user credit balance from backend — Issue #458
export const fetchUserCredits = createAsyncThunk(
  'billing/fetchUserCredits',
  async (_, { rejectWithValue }) => {
    try {
      const res = await fetch(`${API_BASE}/api/billing/credits`, {
        credentials: 'include',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json() as { credits: number };
      return data.credits;
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : 'Fehler beim Laden der Credits';
      return rejectWithValue(msg);
    }
  }
);


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
    },
    // Credits — Issue #458
    deductCredits: (state, action: PayloadAction<number>) => {
      state.credits = Math.max(0, state.credits - action.payload);
    },
    addCredits: (state, action: PayloadAction<number>) => {
      state.credits += action.payload;
    },
    openCreditPaywall: (state, action: PayloadAction<{ required: number; available: number }>) => {
      state.isPaywallOpen = true;
      state.insufficientFor = action.payload;
    },
    closeCreditPaywall: (state) => {
      state.isPaywallOpen = false;
      state.insufficientFor = null;
    },
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
      })
      // Credits — Issue #458
      .addCase(fetchUserCredits.fulfilled, (state, action: PayloadAction<number>) => {
        state.credits = action.payload;
      });
  },
});

export const {
  resetBillingState,
  setBillingError,
  togglePaywall,
  deductCredits,
  addCredits,
  openCreditPaywall,
  closeCreditPaywall,
} = billingSlice.actions;

// Selectors
export const selectCredits = (state: RootState) => state.billing.credits;
export const selectIsPaywallOpen = (state: RootState) => state.billing.isPaywallOpen;
export const selectInsufficientFor = (state: RootState) => state.billing.insufficientFor;
export const selectSubscription = (state: RootState) => state.billing.subscription;
export const selectIsSubscribed = (state: RootState) => state.billing.isSubscribed;
export const selectIsLoading = (state: RootState) => state.billing.loading;
export const selectBillingError = (state: RootState) => state.billing.error;
export const selectAvailablePackages = (state: RootState) => state.billing.availablePackages;
export const selectInvoices = (state: RootState) => state.billing.invoices;
export const selectPackages = (state: RootState) => state.billing.packages;
export const selectSubscriptionTier = (state: RootState) => state.billing.tier;
export const selectIsPaywallActive = (state: RootState) => state.billing.isPaywallActive;

export default billingSlice.reducer;
