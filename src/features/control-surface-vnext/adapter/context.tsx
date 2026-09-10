import React, { createContext, useContext, type ReactNode } from 'react';
import type { SovereignBackendAdapter } from './interface';
import { SovereignProductionAdapter } from './production-adapter';

const defaultAdapter = new SovereignProductionAdapter();
const SovereignAdapterContext = createContext<SovereignBackendAdapter>(defaultAdapter);

export function SovereignAdapterProvider({ children, adapter }: { children: ReactNode; adapter?: SovereignBackendAdapter }) {
  return <SovereignAdapterContext.Provider value={adapter ?? defaultAdapter}>{children}</SovereignAdapterContext.Provider>;
}
export function useSovereignAdapter(): SovereignBackendAdapter { return useContext(SovereignAdapterContext); }
