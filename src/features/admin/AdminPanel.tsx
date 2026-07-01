/**
 * AdminPanel — Admin UI with tab navigation.
 *
 * Hooks only fire AFTER API key validation (ready === true).
 * All hook-using components live in ReadyContent which only mounts when ready.
 * API key stored in localStorage; replaced by JWT auth in Issue #459.
 *
 * Issue #460
 */

import React, { useState, useEffect } from 'react';
import { Users, CreditCard, Grid, Cpu, FileText, Key, CheckCircle, AlertTriangle } from 'lucide-react';
import { AdminGate } from './AdminGate';
import { UserTable } from './components/UserTable';
import { UserEditModal } from './components/UserEditModal';
import { TransactionTable } from './components/TransactionTable';
import { BillingStats } from './components/BillingStats';
import { LauncherToolEditor } from './components/LauncherToolEditor';
import { LlmRouteEditor } from './components/LlmRouteEditor';
import {
  useAdminUsers,
  useAdminTransactions,
  useAdminLauncherTools,
  useAdminLlmRoutes,
  useAdminAuditLog,
} from './hooks/useAdminApi';
import { type AdminUser, getAdminKey, setAdminKey, adminApiClient } from './api/adminApiClient';
import { useUserStore, type UserRole } from '../user/useUserStore';
import type { LauncherToolProps } from '../launcher/launcherRegistry';

const C = {
  bg: '#0e1116', surface: '#161c24', border: '#232d3a',
  accent: '#00d9b1', text: '#cdd9e5', textSub: '#768390', danger: '#f87171',
} as const;

type Tab = 'users' | 'billing' | 'launcher' | 'llm' | 'audit';

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { id: 'users',    label: 'Nutzer',   icon: Users },
  { id: 'billing',  label: 'Billing',  icon: CreditCard },
  { id: 'launcher', label: 'Launcher', icon: Grid },
  { id: 'llm',      label: 'LLM',      icon: Cpu },
  { id: 'audit',    label: 'Audit',    icon: FileText },
];

// ── API Key Setup ─────────────────────────────────────────────────────────────

function ApiKeySetup({ onReady }: { onReady: () => void }) {
  const [input,   setInput]   = useState('');
  const [testing, setTesting] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const handleSave = async () => {
    if (!input.trim()) return;
    setAdminKey(input.trim());
    setTesting(true); setError(null);
    try {
      const result = await adminApiClient.ping();
      // Provision a store user so AdminGate unlocks.
      // Issue #459 will replace this with a real JWT session.
      useUserStore.getState().setUser({
        id:                 'admin-api-key-session',
        email:              'admin@sovereign-studio',
        displayName:        'Admin',
        role:               (result.role as UserRole) ?? 'admin',
        credits:            0,
        subscriptionStatus: 'active',
        isBanned:           false,
        createdAt:          Date.now(),
      });
      onReady();
    } catch (e) {
      setError(`Verbindungsfehler: ${String(e)}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 20, padding: 24, background: C.bg }}>
      <Key size={32} color={C.accent} style={{ opacity: 0.8 }} />
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: C.text, marginBottom: 6 }}>Admin API-Key</div>
        <div style={{ fontSize: 11, color: C.textSub, maxWidth: 260 }}>
          Einmalig eingeben — wird in localStorage gespeichert.<br />
          Wird durch JWT-Auth in Issue #459 ersetzt.
        </div>
      </div>

      <div style={{ width: '100%', maxWidth: 280, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <input
          type="password"
          placeholder="8516ae6b…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && void handleSave()}
          style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px', fontSize: 12, color: C.text, outline: 'none', width: '100%', boxSizing: 'border-box', fontFamily: 'monospace' }}
        />
        {error && (
          <div style={{ background: '#f8717120', border: '1px solid #f8717140', borderRadius: 8, padding: '8px 12px', fontSize: 11, color: C.danger, display: 'flex', gap: 6 }}>
            <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />{error}
          </div>
        )}
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={testing || !input.trim()}
          style={{ background: C.accent, border: 'none', borderRadius: 8, padding: '10px 0', fontSize: 12, fontWeight: 700, color: '#000', cursor: (testing || !input.trim()) ? 'not-allowed' : 'pointer', opacity: (testing || !input.trim()) ? 0.6 : 1 }}
        >
          {testing ? 'Verbinde…' : 'Verbinden & speichern'}
        </button>
      </div>
    </div>
  );
}

// ── Audit log (inline) ────────────────────────────────────────────────────────

function AuditLogView() {
  const { entries, total, loading, error, reload } = useAdminAuditLog();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 10, color: C.textSub }}>{total} Einträge</span>
        <button type="button" onClick={reload} style={{ background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 6, padding: '4px 10px', fontSize: 10, color: C.textSub, cursor: 'pointer' }}>Neu laden</button>
      </div>
      {loading && <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>Lade…</div>}
      {error   && <div style={{ padding: 16, color: C.danger, fontSize: 12 }}>{error}</div>}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
        {entries.length === 0 && !loading && <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>Noch keine Einträge.</div>}
        {entries.map(e => (
          <div key={e.id} style={{ padding: '8px 14px', borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <CheckCircle size={11} color={C.accent} />
              <span style={{ fontSize: 11, fontWeight: 600, color: C.text }}>{e.action}</span>
              <span style={{ fontSize: 10, color: C.textSub, marginLeft: 'auto' }}>{new Date(e.createdAt).toLocaleString('de')}</span>
            </div>
            {e.targetId && <div style={{ fontSize: 10, color: C.textSub, marginTop: 2, paddingLeft: 19 }}>target: {e.targetId}</div>}
            {Object.keys(e.changes).length > 0 && (
              <div style={{ fontSize: 9, color: C.textSub, marginTop: 2, paddingLeft: 19, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {JSON.stringify(e.changes)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Ready content — only mounts after API key validated ───────────────────────
// All hooks live here so they never fire before key is ready.

function ReadyContent() {
  const [tab, setTab]           = useState<Tab>('users');
  const [editUser, setEditUser] = useState<AdminUser | null>(null);

  const usersApi    = useAdminUsers();
  const txApi       = useAdminTransactions();
  const launcherApi = useAdminLauncherTools();
  const llmApi      = useAdminLlmRoutes();

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: C.bg }}>
      {/* Tab bar */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${C.border}`, overflowX: 'auto', flexShrink: 0 }}>
        {TABS.map(t => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, padding: '8px 12px', background: 'transparent', border: 'none', cursor: 'pointer', borderBottom: `2px solid ${active ? C.accent : 'transparent'}`, color: active ? C.accent : C.textSub, flexShrink: 0, minWidth: 56 }}
            >
              <Icon size={14} />
              <span style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: 14 }}>
        {tab === 'users'    && <UserTable api={usersApi} onEdit={setEditUser} />}
        {tab === 'billing'  && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <BillingStats />
            <TransactionTable api={txApi} />
          </div>
        )}
        {tab === 'launcher' && <LauncherToolEditor api={launcherApi} />}
        {tab === 'llm'      && <LlmRouteEditor api={llmApi} />}
        {tab === 'audit'    && <AuditLogView />}
      </div>

      {editUser && (
        <UserEditModal
          user={editUser}
          api={usersApi}
          onClose={() => { setEditUser(null); usersApi.reload(); }}
        />
      )}
    </div>
  );
}

// ── Root panel ────────────────────────────────────────────────────────────────

function PanelContent(_props: LauncherToolProps) {
  const [ready, setReady] = useState(false);

  // Restore key from localStorage and verify it on mount
  useEffect(() => {
    const key = getAdminKey();
    if (!key) return;
    adminApiClient.ping()
      .then(() => setReady(true))
      .catch(() => setReady(false)); // Key present but invalid → show setup screen
  }, []);

  if (!ready) return <ApiKeySetup onReady={() => setReady(true)} />;

  // ReadyContent mounts only here — all hooks are gated behind this point
  return <ReadyContent />;
}

export function AdminPanel({ onClose, onMinimize }: LauncherToolProps) {
  return (
    <AdminGate>
      <PanelContent onClose={onClose} onMinimize={onMinimize} />
    </AdminGate>
  );
}
