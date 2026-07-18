// sovereign-endpoint-surface: disabled-launcher
/**
 * useVpsConnection — Hook für VPS SSH-Session-Verwaltung.
 *
 * Kommuniziert mit einem Backend-Proxy (POST /api/vps/*).
 * SSH-Verbindungen laufen NICHT direkt im Browser.
 *
 * Backend-Setup (außerhalb dieses Issues):
 *   pnpm add ssh2 express
 *   → Backend mountet die Routen aus src/server/vpsRoutes.ts
 *
 * Issue #454
 */

import { useState, useCallback } from 'react';

// ── Typen ────────────────────────────────────────────────────────────────────

export interface VpsCredentials {
  host: string;
  port: number;
  username: string;
  authMethod: 'password' | 'key';
  password?: string;
  privateKey?: string;
}

export interface DirEntry {
  name: string;
  type: 'file' | 'directory' | 'symlink';
  size?: number;
  permissions?: string;
}

export interface ExecResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export type ConnectionPhase = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface VpsConnectionState {
  phase: ConnectionPhase;
  sessionId: string | null;
  host: string;
  username: string;
  error: string | null;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useVpsConnection() {
  const [state, setState] = useState<VpsConnectionState>({
    phase: 'disconnected',
    sessionId: null,
    host: '',
    username: '',
    error: null,
  });

  /** SSH-Verbindung herstellen — gibt sessionId zurück oder wirft */
  const connect = useCallback(async (creds: VpsCredentials): Promise<void> => {
    setState((s) => ({ ...s, phase: 'connecting', error: null }));
    try {
      const res = await fetch('/api/vps/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // Credentials NICHT in State-Store — nur hier im Request-Body
        body: JSON.stringify({
          host: creds.host,
          port: creds.port,
          username: creds.username,
          authMethod: creds.authMethod,
          password: creds.authMethod === 'password' ? creds.password : undefined,
          privateKey: creds.authMethod === 'key' ? creds.privateKey : undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: 'Verbindung fehlgeschlagen' }));
        throw new Error(err.error ?? 'Verbindung fehlgeschlagen');
      }
      const { sessionId } = await res.json() as { sessionId: string };
      setState({
        phase: 'connected',
        sessionId,
        host: creds.host,
        username: creds.username,
        error: null,
      });
    } catch (err) {
      setState((s) => ({
        ...s,
        phase: 'error',
        error: err instanceof Error ? err.message : 'Unbekannter Fehler',
      }));
    }
  }, []);

  /** Shell-Befehl ausführen (nach expliziter User-Bestätigung) */
  const execCommand = useCallback(async (command: string): Promise<ExecResult> => {
    if (!state.sessionId) throw new Error('Keine aktive Verbindung');
    const res = await fetch('/api/vps/exec', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sessionId: state.sessionId, command }),
    });
    if (!res.ok) throw new Error('Befehl fehlgeschlagen');
    return res.json() as Promise<ExecResult>;
  }, [state.sessionId]);

  /** Verzeichnis-Listing holen */
  const getTree = useCallback(async (path: string): Promise<DirEntry[]> => {
    if (!state.sessionId) return [];
    const url = `/api/vps/tree?sessionId=${encodeURIComponent(state.sessionId)}&path=${encodeURIComponent(path)}`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json() as { entries: DirEntry[] };
    return data.entries ?? [];
  }, [state.sessionId]);

  /** Session beenden */
  const disconnect = useCallback(async (): Promise<void> => {
    if (state.sessionId) {
      await fetch('/api/vps/disconnect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: state.sessionId }),
      }).catch(() => { /* ignorieren — Session läuft ab */ });
    }
    setState({ phase: 'disconnected', sessionId: null, host: '', username: '', error: null });
  }, [state.sessionId]);

  return { state, connect, execCommand, getTree, disconnect };
}
