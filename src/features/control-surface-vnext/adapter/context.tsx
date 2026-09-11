import React, { createContext, useContext, type ReactNode } from 'react';
import type { SovereignBackendAdapter } from './interface';
import { RepositoryBoundSovereignProductionAdapter } from './repository-bound-adapter';

const defaultAdapter = new RepositoryBoundSovereignProductionAdapter();
const SovereignAdapterContext = createContext<SovereignBackendAdapter>(defaultAdapter);

export function SovereignAdapterProvider({ children, adapter }: { children: ReactNode; adapter?: SovereignBackendAdapter }) {
  return <SovereignAdapterContext.Provider value={adapter ?? defaultAdapter}>{children}</SovereignAdapterContext.Provider>;
}
export function useSovereignAdapter(): SovereignBackendAdapter { return useContext(SovereignAdapterContext); }
