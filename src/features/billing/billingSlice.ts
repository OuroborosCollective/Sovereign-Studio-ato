import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';

interface BillingState {
  subscription: any | null;
  invoices: any[];
  availablePackages: any[];
  loading: boolean;
  error: string | null;
}

const initialState: BillingState = {
  subscription: null,
  invoices: [],
  availablePackages: [],
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

export const purchasePackageAction = createAsyncThunk(
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

export const restorePurchasesAction = createAsyncThunk(
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
      })
      .addCase(fetchBillingData.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(purchasePackageAction.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(purchasePackageAction.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        state.subscription = action.payload.subscription;
      })
      .addCase(purchasePackageAction.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      })
      .addCase(restorePurchasesAction.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(restorePurchasesAction.fulfilled, (state, action: PayloadAction<any>) => {
        state.loading = false;
        state.subscription = action.payload.subscription;
      })
      .addCase(restorePurchasesAction.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { resetBillingState, setBillingError } = billingSlice.actions;

export const selectIsSubscribed = (state: { billing: BillingState }) => !!state.billing.subscription;
export const selectIsLoading = (state: { billing: BillingState }) => state.billing.loading;
export const selectBillingError = (state: { billing: BillingState }) => state.billing.error;
export const selectAvailablePackages = (state: { billing: BillingState }) => state.billing.availablePackages;

export const selectBillingPackages = selectAvailablePackages;
export const purchasePackage = purchasePackageAction;
export const restorePurchases = restorePurchasesAction;

export default billingSlice.reducer;