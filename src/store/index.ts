import { configureStore, Middleware } from '@reduxjs/toolkit';
import billingReducer from '../features/billing/billingSlice';
import canvasReducer, { addObject } from '../features/canvas/canvasSlice';

const canvasMiddleware: Middleware = (store) => (next) => (action: any) => {
  if (action.type === 'ai/setGeneratedContent' || action.type === 'ai/responseReceived') {
    if (action.payload) {
      store.dispatch(addObject(action.payload));
    }
  }
  return next(action);
};

export const store = configureStore({
  reducer: {
    billing: billingReducer,
    canvas: canvasReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(canvasMiddleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export * from '../features/canvas/canvasSlice';