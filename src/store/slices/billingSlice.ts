import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface Invoice {
  id: string;
  amount: number;
  currency: string;
  status: 'paid' | 'pending' | 'failed' | 'refunded';
  date: string;
  pdfUrl?: string;
}

export interface Subscription {
  id: string;
  planId: string;
  status: 'active' | 'canceled' | 'past_due' | 'incomplete';
  currentPeriodEnd: string;
  cancelAtPeriodEnd: boolean;
}

interface BillingState {
  invoices: Invoice[];
  subscription: Subscription | null;
  isLoading: boolean;
  error: string | null;
}

const initialState: BillingState = {
  invoices: [],
  subscription: null,
  isLoading: false,
  error: null,
};

export const billingSlice = createSlice({
  name: 'billing',
  initialState,
  reducers: {
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
    setInvoices: (state, action: PayloadAction<Invoice[]>) => {
      state.invoices = action.payload;
      state.isLoading = false;
      state.error = null;
    },
    setSubscription: (state, action: PayloadAction<Subscription | null>) => {
      state.subscription = action.payload;
      state.isLoading = false;
      state.error = null;
    },
    updateSubscriptionStatus: (state, action: PayloadAction<Subscription['status']>) => {
      if (state.subscription) {
        state.subscription.status = action.payload;
      }
    },
    resetBillingState: (state) => {
      state.invoices = [];
      state.subscription = null;
      state.isLoading = false;
      state.error = null;
    },
  },
});

export const {
  setLoading,
  setError,
  setInvoices,
  setSubscription,
  updateSubscriptionStatus,
  resetBillingState,
} = billingSlice.actions;

export default billingSlice.reducer;