import { configureStore, Middleware, AnyAction } from '@reduxjs/toolkit';
import { Preferences } from '@capacitor/preferences';
import billingReducer from '../features/billing/billingSlice';
import canvasReducer, { addObject } from '../features/canvas/canvasSlice';
import ouroborosReducer from '../features/ouroboros/ouroborosSlice';

const PERSISTENCE_KEY = 'sovereign_canvas_state_mirror';

const canvasMiddleware: Middleware = (store) => (next) => (action: AnyAction) => {
  if (action.type === 'ai/setGeneratedContent' || action.type === 'ai/responseReceived') {
    if (action.payload) {
      store.dispatch(addObject(action.payload));
    }
  }
  return next(action);
};

const persistenceMiddleware: Middleware = (store) => (next) => (action: AnyAction) => {
  const result = next(action);
  const state = store.getState();
  
  if (action.type.startsWith('canvas/')) {
    const persistData = async () => {
      try {
        await Preferences.set({
          key: PERSISTENCE_KEY,
          value: JSON.stringify(state.canvas),
        });
      } catch (error) {
        console.error('Failed to mirror canvas state to native storage', error);
      }
    };
    persistData();
  }
  
  return result;
};

export const store = configureStore({
  reducer: {
    billing: billingReducer,
    canvas: canvasReducer,
    ouroboros: ouroborosReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(canvasMiddleware, persistenceMiddleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export * from '../features/canvas/canvasSlice';
export * from '../features/ouroboros/ouroborosSlice';
