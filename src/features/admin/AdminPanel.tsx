/**
 * AdminPanel — Admin UI with tab navigation.
 *
 * Access flow (until Issue #459 adds real JWT auth):
 *   1. User opens admin tool → API key setup screen shown (no gate yet).
 *   2. Valid API key → ping() succeeds → user set in store as admin.
 *   3. AdminGate unlocks → ReadyContent mounts and all hooks fire.
 *
 * AdminGate wraps ONLY ReadyContent, NOT the key-setup screen.
 * This avoids the deadlock where the gate blocks the only screen that
 * can establish admin state.
 *
 * Issue #460
 */

import React, { useState, useEffect } from 'react';
import './AdminPanel.css';
import {
  Users, CreditCard, Grid, Cpu, FileText,
  Key, CheckCircle, AlertTriangle, Wallet, ServerCog,
} from 'lucide-react';
import { AdminGate } from './AdminGate';
import { UserTable } from './components/UserTable';
import { UserEditModal } from './components/UserEditModal';
import { TransactionTable } from './components/TransactionTable';
import { BillingStats } from './components/BillingStats';
import { LauncherToolEditor } from './components/LauncherToolEditor';
import { LlmRouteEditor } from './components/LlmRouteEditor';
import { PaymentMethodEditor } from './components/PaymentMethodEditor';
import { EnterpriseBackendPanel } from './components/EnterpriseBackendPanel';
import {
  useAdminUsers,
  useAdminTransactions,
  useAdminLauncherTools,
  useAdminLlmRoutes,
  useAdminAuditLog,
  useAdminPaymentMethods,
} from './hooks/useAdminApi';
import {
  type AdminUser,
  clearAdminKey,
  getAdminKey,
  setAdminKey,
  adminApiClient,
} from './api/adminApiClient';
import { useUserStore } from '../user/useUserStore';
import type { LauncherToolProps } from '../launcher/launcherRegistry';

const C = {
  bg: '#0e1116', surface: '#161c24', border: '#232d3a',
  accent: '#00d9b1', text: '#cdd9e5', textSub: '#768390', danger: '#f87171',
} as const;

type Tab = 'platform' | 'users' | 'billing' | 'payments' | 'launcher' | 'llm' | 'audit';

const TABS: { id: Tab; label: string; icon: React.ComponentType<{ size?: number }> }[] = [
  { id: 'platform', label: 'Platform',  icon: ServerCog },
  { id: 'users',    label: 'Nutzer',    icon: Users },
  { id: 'billing',  label: 'Billing',   icon: CreditCard },
  { id: 'payments', label: 'Zahlungen', icon: Wallet },
  { id: 'launcher', label: 'Launcher',  icon: Grid },
  { id: 'llm',      label: 'LLM',       icon: Cpu },
  { id: 'audit',    label: 'Audit',     icon: FileText },
];

// ── API Key Setup ─────────────────────────────────────────────────────────────
// Renders WITHOUT AdminGate — this IS the entry point for first-time admins.

function applyConfirmedAdminSession(result: AdminUser): void {
  const createdAt = Date.parse(result.createdAt);
  if (!Number.isFinite(createdAt)) {
    throw new Error('Admin-Ping lieferte keinen gültigen Erstellzeitpunkt.');
  }
  useUserStore.getState().setUser({
    id: result.id,
    email: result.email,
    displayName: result.displayName,
    role: result.role,
    credits: result.credits,
    subscriptionStatus: result.subscriptionStatus,
    isBanned: result.isBanned,
    createdAt,
  });
}

function ApiKeySetup({ onReady }: { onReady: () => void }) {
  const [input,   setInput]   = useState('');
  const [testing, setTesting] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const handleSave = async () => {
    if (!input.trim()) return;
    setAdminKey(input.trim());
    setTesting(true);
    setError(null);
    try {
      const result = await adminApiClient.ping();
      applyConfirmedAdminSession(result);
      onReady();
    } catch (e) {
      clearAdminKey();
      setError(`Verbindungsfehler: ${String(e)}`);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="admin-auth-shell">
      <section className="admin-auth-card" aria-labelledby="admin-auth-title">
        <div className="admin-auth-card__mark" aria-hidden="true">
          <Key size={28} />
        </div>
        <div className="admin-auth-card__copy">
          <span className="admin-auth-card__eyebrow">Sovereign Control Plane</span>
          <h1 id="admin-auth-title">Admin-Verbindung</h1>
          <p>
            Verwende denselben bestehenden Admin-Key wie bisher. Der Schlüssel bleibt nur in
            dieser geöffneten App-Sitzung im Arbeitsspeicher und wird serverseitig geprüft.
          </p>
        </div>
        <div className="admin-auth-form">
          <label>
            Bestehender Admin-Key
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Admin-Key eingeben"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && void handleSave()}
            />
          </label>
          {error && (
            <div className="admin-auth-form__error" role="alert">
              <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1 }} />
              {error}
            </div>
          )}
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={testing || !input.trim()}
            className="admin-auth-form__button"
          >
            {testing ? 'Verbinde…' : 'Verbinden & speichern'}
          </button>
        </div>
      </section>
    </div>
  );
}

// ── Audit log view ────────────────────────────────────────────────────────────

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

// ── Ready content ─────────────────────────────────────────────────────────────
// Only mounts after key validated AND user set in store.
// AdminGate lives here — NOT around the whole panel.

function ReadyContent() {
  const [tab, setTab]           = useState<Tab>('platform');
  const [editUser, setEditUser] = useState<AdminUser | null>(null);

  const usersApi      = useAdminUsers();
  const txApi         = useAdminTransactions();
  const launcherApi   = useAdminLauncherTools();
  const llmApi        = useAdminLlmRoutes();
  const paymentsApi   = useAdminPaymentMethods();

  return (
    <AdminGate>
      <div className="admin-shell">
        {/* Tab bar */}
        <nav className="admin-shell__tabs" aria-label="Admin-Bereiche">
          {TABS.map(t => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={`admin-shell__tab${active ? ' admin-shell__tab--active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <Icon size={14} />
                <span style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{t.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Content */}
        <main className={`admin-shell__content${tab === 'platform' ? ' admin-shell__content--platform' : ''}`}>
          {tab === 'platform' && <EnterpriseBackendPanel />}
          {tab === 'users'    && <UserTable api={usersApi} onEdit={setEditUser} />}
          {tab === 'billing'  && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <BillingStats />
              <TransactionTable api={txApi} />
            </div>
          )}
          {tab === 'payments' && <PaymentMethodEditor api={paymentsApi} />}
          {tab === 'launcher' && <LauncherToolEditor api={launcherApi} />}
          {tab === 'llm'      && <LlmRouteEditor api={llmApi} />}
          {tab === 'audit'    && <AuditLogView />}
        </main>

        {editUser && (
          <UserEditModal
            user={editUser}
            api={usersApi}
            onClose={() => { setEditUser(null); usersApi.reload(); }}
          />
        )}
      </div>
    </AdminGate>
  );
}

// ── Root panel ────────────────────────────────────────────────────────────────

export function AdminPanel(_props?: LauncherToolProps) {
  const [ready, setReady] = useState(false);

  // On mount: if a key exists and user not yet in store, re-validate the key.
  useEffect(() => {
    const key = getAdminKey();
    if (!key) return;
    adminApiClient.ping()
      .then(result => {
        applyConfirmedAdminSession(result);
        setReady(true);
      })
      .catch(() => {
        clearAdminKey();
        useUserStore.getState().clearUser();
        setReady(false);
      });
  }, []);

  if (!ready) {
    // API key setup renders WITHOUT AdminGate — this is intentional.
    // The gate only wraps ReadyContent (below), after key is validated.
    return <ApiKeySetup onReady={() => setReady(true)} />;
  }

  return <ReadyContent />;
}
