import { createSlice, PayloadAction, createAsyncThunk } from '@reduxjs/toolkit';

interface BillingState {
  subscription: any | null;
  invoices: any[];
  loading: boolean;
  error: string | null;
}

const initialState: BillingState = {
  subscription: null,
  invoices: [],
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

const billingSlice = createSlice({
  name: 'billing',
  initialState,
  reducers: {
    resetBillingState: (state) => {
      state.subscription = null;
      state.invoices = [];
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
      })
      .addCase(fetchBillingData.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
      });
  },
});

export const { resetBillingState, setBillingError } = billingSlice.actions;
export default billingSlice.reducer;