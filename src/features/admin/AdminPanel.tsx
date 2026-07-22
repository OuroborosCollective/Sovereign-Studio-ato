/**
 * AdminPanel — Admin UI with tab navigation.
 *
 * Access flow (until Issue #459 adds real JWT auth):
 *   1. User opens admin tool → API key setup screen shown (no gate yet).
 *   2. Valid API key → ping() succeeds → user set in store as admin.
 *   3. AdminGate unlocks → ReadyContent mounts; only the active tab loads its API.
 *
 * AdminGate wraps ONLY ReadyContent, NOT the key-setup screen.
 * This avoids the deadlock where the gate blocks the only screen that
 * can establish admin state.
 *
 * Issue #460
 */

import React, { useEffect, useMemo, useState } from 'react';
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

// ── Per-section recovery boundary ─────────────────────────────────────────────

type AdminSectionErrorBoundaryProps = {
  section: string;
  children: React.ReactNode;
};

type AdminSectionErrorBoundaryState = {
  failed: boolean;
  message: string;
};

class AdminSectionErrorBoundary extends React.Component<
  AdminSectionErrorBoundaryProps,
  AdminSectionErrorBoundaryState
> {
  state: AdminSectionErrorBoundaryState = { failed: false, message: '' };

  static getDerivedStateFromError(error: unknown): AdminSectionErrorBoundaryState {
    return {
      failed: true,
      message: error instanceof Error ? error.message : String(error),
    };
  }

  componentDidCatch(error: unknown): void {
    console.error('[admin-section-error]', {
      section: this.props.section,
      message: error instanceof Error ? error.message : String(error),
    });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="admin-section-error" role="alert">
        <AlertTriangle size={24} />
        <div>
          <strong>{this.props.section} konnte nicht dargestellt werden.</strong>
          <p>{this.state.message || 'Unbekannter Darstellungsfehler'}</p>
          <p>Die Admin-Sitzung bleibt aktiv. Andere Bereiche können weiterhin geöffnet werden.</p>
        </div>
        <button
          type="button"
          onClick={() => this.setState({ failed: false, message: '' })}
        >
          Bereich erneut versuchen
        </button>
      </section>
    );
  }
}

// ── Audit log view ────────────────────────────────────────────────────────────

function safeAuditChanges(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function AuditLogView() {
  const { entries, total, loading, error, reload } = useAdminAuditLog();
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return entries;
    return entries.filter(entry => [
      entry.action,
      entry.adminEmail,
      entry.targetId ?? '',
      JSON.stringify(safeAuditChanges(entry.changes)),
    ].some(value => value.toLowerCase().includes(needle)));
  }, [entries, search]);

  return (
    <div className="admin-audit">
      <div className="admin-audit__toolbar">
        <div>
          <strong>{total} Einträge</strong>
          <span>{filtered.length} auf dieser Seite sichtbar</span>
        </div>
        <button type="button" onClick={reload}>Neu laden</button>
      </div>
      <input
        className="admin-audit__search"
        type="search"
        value={search}
        onChange={event => setSearch(event.target.value)}
        placeholder="Aktion, Admin, Ziel oder Änderung filtern…"
      />
      {loading && <div className="admin-audit__state">Lade Audit-Evidence…</div>}
      {error && <div className="admin-audit__state admin-audit__state--error">{error}</div>}
      <div className="admin-audit__list">
        {filtered.length === 0 && !loading && (
          <div className="admin-audit__state">Keine passenden Einträge.</div>
        )}
        {filtered.map(entry => {
          const changes = safeAuditChanges(entry.changes);
          const changeCount = Object.keys(changes).length;
          return (
            <article key={entry.id} className="admin-audit__entry">
              <header>
                <CheckCircle size={16} color={C.accent} />
                <div>
                  <strong>{entry.action.replaceAll('_', ' ')}</strong>
                  <span>{entry.adminEmail} · {new Date(entry.createdAt).toLocaleString('de')}</span>
                </div>
              </header>
              {entry.targetId && <p><b>Ziel:</b> {entry.targetId}</p>}
              {changeCount > 0 && (
                <details>
                  <summary>{changeCount} Änderungsfeld{changeCount === 1 ? '' : 'er'} anzeigen</summary>
                  <pre>{JSON.stringify(changes, null, 2)}</pre>
                </details>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

// ── Lazy tab content ──────────────────────────────────────────────────────────
// Each data hook lives inside its tab component. Hidden tabs therefore do not
// produce API traffic or allow an unrelated response to crash the active view.

function UsersTab() {
  const api = useAdminUsers();
  const [editUser, setEditUser] = useState<AdminUser | null>(null);
  return (
    <>
      <UserTable api={api} onEdit={setEditUser} />
      {editUser && (
        <UserEditModal
          user={editUser}
          api={api}
          onClose={() => { setEditUser(null); api.reload(); }}
        />
      )}
    </>
  );
}

function BillingTab() {
  const api = useAdminTransactions();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <BillingStats />
      <TransactionTable api={api} />
    </div>
  );
}

function PaymentsTab() {
  const api = useAdminPaymentMethods();
  return <PaymentMethodEditor api={api} />;
}

function LauncherTab() {
  const api = useAdminLauncherTools();
  return <LauncherToolEditor api={api} />;
}

function LlmTab() {
  const api = useAdminLlmRoutes();
  return <LlmRouteEditor api={api} />;
}

function ActiveTab({ tab }: { tab: Tab }) {
  switch (tab) {
    case 'platform': return <EnterpriseBackendPanel />;
    case 'users': return <UsersTab />;
    case 'billing': return <BillingTab />;
    case 'payments': return <PaymentsTab />;
    case 'launcher': return <LauncherTab />;
    case 'llm': return <LlmTab />;
    case 'audit': return <AuditLogView />;
  }
}

// ── Ready content ─────────────────────────────────────────────────────────────
// Only mounts after key validated AND user set in store.
// AdminGate lives here — NOT around the whole panel.

function ReadyContent() {
  const [tab, setTab] = useState<Tab>('platform');
  const activeLabel = TABS.find(item => item.id === tab)?.label ?? tab;

  return (
    <AdminGate>
      <div className="admin-shell">
        <nav className="admin-shell__tabs" aria-label="Admin-Bereiche">
          {TABS.map(item => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`admin-shell__tab${active ? ' admin-shell__tab--active' : ''}`}
                aria-current={active ? 'page' : undefined}
              >
                <Icon size={17} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <main className={`admin-shell__content${tab === 'platform' ? ' admin-shell__content--platform' : ''}`}>
          <AdminSectionErrorBoundary key={tab} section={activeLabel}>
            <ActiveTab tab={tab} />
          </AdminSectionErrorBoundary>
        </main>
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
