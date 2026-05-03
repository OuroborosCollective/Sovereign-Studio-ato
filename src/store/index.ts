import { configureStore } from '@reduxjs/toolkit';
import billingReducer from '../features/billing/billingSlice';
import canvasReducer from '../features/canvas/canvasSlice';

export const store = configureStore({
  reducer: {
    billing: billingReducer,
    canvas: canvasReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export * from '../features/canvas/canvasSlice';