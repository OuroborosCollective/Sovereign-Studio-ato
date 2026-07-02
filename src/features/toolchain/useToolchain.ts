/**
 * useToolchain — React-Hook für den Sovereign Universal Toolchain Server.
 *
 * Lädt das Tool-Manifest beim ersten Mount und hält den Aufrufstatus.
 */

import { useState, useEffect, useCallback } from 'react';
import { toolchainClient, type ToolDefinition, type ToolResult } from './toolchainClient';

export interface UseToolchainResult {
  tools: ToolDefinition[];
  loading: boolean;
  error: string | null;
  serverOnline: boolean;
  invoke: (name: string, args: Record<string, unknown>) => Promise<ToolResult>;
  lastResult: ToolResult | null;
  invoking: boolean;
  reload: () => void;
}

export function useToolchain(): UseToolchainResult {
  const [tools,        setTools]       = useState<ToolDefinition[]>([]);
  const [loading,      setLoading]     = useState(true);
  const [error,        setError]       = useState<string | null>(null);
  const [serverOnline, setOnline]      = useState(false);
  const [lastResult,   setLastResult]  = useState<ToolResult | null>(null);
  const [invoking,     setInvoking]    = useState(false);
  const [rev,          setRev]         = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    toolchainClient.manifest()
      .then(m => {
        if (cancelled) return;
        setTools(m.tools ?? []);
        setOnline(true);
        setLoading(false);
      })
      .catch(err => {
        if (cancelled) return;
        setError(String(err));
        setOnline(false);
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [rev]);

  const invoke = useCallback(async (name: string, args: Record<string, unknown>): Promise<ToolResult> => {
    setInvoking(true);
    try {
      const result = await toolchainClient.invoke(name, args);
      setLastResult(result);
      return result;
    } catch (err) {
      const r: ToolResult = { ok: false, tool: name, error: String(err) };
      setLastResult(r);
      return r;
    } finally {
      setInvoking(false);
    }
  }, []);

  return {
    tools,
    loading,
    error,
    serverOnline,
    invoke,
    lastResult,
    invoking,
    reload: () => setRev(v => v + 1),
  };
}
