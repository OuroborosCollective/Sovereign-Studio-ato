import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';

export interface Subscription {
  id: string;
  status: string;
  planId: string;
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
}

export interface BillingState {
  subscription: Subscription | null;
  invoices: Invoice[];
  availablePackages: BillingPackage[];
  packages: BillingPackage[];
  loading: boolean;
  error: string | null;
}

const initialState: BillingState = {
  subscription: null,
  invoices: [],
  availablePackages: [],
  packages: [],
  loading: false,
  error: null,
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

const billingSlice = createSlice({
  name: 'billing',
  initialState,
  reducers: {
    resetBillingState: (state) => {
      state.subscription = null;
      state.invoices = [];
      state.availablePackages = [];
      state.packages = [];
      state.loading = false;
      state.error = null;
    },
    setBillingError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
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
        state.subscription = action.payload.subscription;
        state.invoices = action.payload.invoices || [];
        state.availablePackages = action.payload.availablePackages || [];
        state.packages = action.payload.packages || action.payload.availablePackages || [];
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
        state.subscription = action.payload.subscription;
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
        state.subscription = action.payload.subscription;
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
        state.subscription = action.payload.subscription;
      })
      .addCase(restorePurchases.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { resetBillingState, setBillingError } = billingSlice.actions;

export const selectSubscription = (state: { billing: BillingState }) => state.billing.subscription;
export const selectIsSubscribed = (state: { billing: BillingState }) => !!state.billing.subscription;
export const selectIsLoading = (state: { billing: BillingState }) => state.billing.loading;
export const selectBillingError = (state: { billing: BillingState }) => state.billing.error;
export const selectAvailablePackages = (state: { billing: BillingState }) => state.billing.availablePackages;
export const selectInvoices = (state: { billing: BillingState }) => state.billing.invoices;
export const selectPackages = (state: { billing: BillingState }) => state.billing.packages;

export default billingSlice.reducer;