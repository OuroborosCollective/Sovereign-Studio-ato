import { configureStore } from '@reduxjs/toolkit';

export const store = configureStore({
  reducer: {
    // Hier können Reducer hinzugefügt werden
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;