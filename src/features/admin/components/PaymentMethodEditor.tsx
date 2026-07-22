/**
 * PaymentMethodEditor — Admin UI für Zahlungsmethoden.
 * Konfiguriert PayPal, Skrill, Crypto-Wallets und Google Play IAP.
 * Issue #457, #456
 */

import React, { useState } from 'react';
import { ToggleLeft, ToggleRight, ChevronDown, ChevronUp, RefreshCw, Plus } from 'lucide-react';
import { adminApiClient, type PaymentMethod } from '../api/adminApiClient';

const C = {
  bg: '#0e1116', surface: '#161c24', border: '#232d3a',
  accent: '#00d9b1', text: '#cdd9e5', textSub: '#768390', danger: '#f87171',
} as const;

const METHOD_ICONS: Record<string, string> = {
  paypal:      '🅿️',
  skrill:      '💳',
  crypto_btc:  '₿',
  crypto_eth:  'Ξ',
  crypto_usdt: '₮',
  google_play: '▶',
};

const CONFIG_FIELDS: Record<string, { key: string; label: string; placeholder: string; secret?: boolean }[]> = {
  paypal: [
    { key: 'client_id',     label: 'Client ID',     placeholder: 'AXxx…',   secret: false },
    { key: 'client_secret', label: 'Client Secret', placeholder: 'ELxx…',   secret: true },
    { key: 'mode',          label: 'Mode',           placeholder: 'live oder sandbox', secret: false },
  ],
  skrill: [
    { key: 'merchant_email', label: 'Merchant E-Mail', placeholder: 'shop@example.com', secret: false },
    { key: 'secret_word',    label: 'Secret Word',     placeholder: '••••••••',          secret: true },
  ],
  crypto_btc: [
    { key: 'wallet_address', label: 'BTC Wallet-Adresse', placeholder: 'bc1q…', secret: false },
    { key: 'network',        label: 'Netzwerk',           placeholder: 'mainnet',  secret: false },
  ],
  crypto_eth: [
    { key: 'wallet_address', label: 'ETH Wallet-Adresse', placeholder: '0x…',   secret: false },
    { key: 'network',        label: 'Netzwerk',           placeholder: 'mainnet', secret: false },
  ],
  crypto_usdt: [
    { key: 'wallet_address', label: 'USDT Wallet-Adresse (TRC20)', placeholder: 'T…', secret: false },
    { key: 'network',        label: 'Netzwerk',                    placeholder: 'tron', secret: false },
  ],
  google_play: [
    { key: 'package_name',          label: 'App Package Name',         placeholder: 'de.example.app',  secret: false },
    { key: 'service_account_json',  label: 'Service Account JSON',     placeholder: '{ "type": "service_account", … }', secret: true },
  ],
};

function ConfigForm({
  method,
  onSave,
  saving,
}: {
  method: PaymentMethod;
  onSave: (id: string, config: Record<string, string>) => Promise<void>;
  saving: boolean;
}) {
  const fields = CONFIG_FIELDS[method.type] ?? [];
  const [localConfig, setLocalConfig] = useState<Record<string, string>>(
    () => Object.fromEntries(fields.map(f => [f.key, String((method.config as Record<string, unknown>)[f.key] ?? '')]))
  );

  const handleSave = () => {
    void onSave(method.id, localConfig);
  };

  if (fields.length === 0) return null;

  return (
    <div style={{ paddingLeft: 30, paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {fields.map(f => (
        <div key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          <label style={{ fontSize: 10, color: C.textSub, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            {f.label}
          </label>
          {f.key === 'service_account_json' ? (
            <textarea
              rows={4}
              value={localConfig[f.key] ?? ''}
              onChange={e => setLocalConfig(prev => ({ ...prev, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              style={{
                background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6,
                padding: '10px 12px', fontSize: 12, color: C.text, outline: 'none',
                fontFamily: 'monospace', resize: 'vertical', minHeight: 96,
              }}
            />
          ) : (
            <input
              type={f.secret ? 'password' : 'text'}
              value={localConfig[f.key] ?? ''}
              onChange={e => setLocalConfig(prev => ({ ...prev, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              style={{
                background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6,
                padding: '10px 12px', minHeight: 44, fontSize: 12, color: C.text, outline: 'none',
                fontFamily: f.secret ? 'monospace' : 'inherit',
              }}
            />
          )}
        </div>
      ))}
      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        style={{
          alignSelf: 'flex-start', background: C.accent, border: 'none', borderRadius: 6,
          minHeight: 44, padding: '9px 16px', fontSize: 12, fontWeight: 700, color: '#000',
          cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
        }}
      >
        {saving ? 'Speichern…' : 'Speichern'}
      </button>
    </div>
  );
}

function MethodRow({
  method,
  onToggle,
  onSaveConfig,
  busyId,
}: {
  method: PaymentMethod;
  onToggle: (id: string, enabled: boolean) => Promise<void>;
  onSaveConfig: (id: string, config: Record<string, string>) => Promise<void>;
  busyId: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const busy = busyId === method.id;
  const icon = METHOD_ICONS[method.type] ?? '💰';

  return (
    <div style={{ borderBottom: `1px solid ${C.border}` }}>
      <div style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          type="button"
          onClick={() => void onToggle(method.id, !method.enabled)}
          disabled={busy}
          style={{ width:44, minWidth:44, minHeight:44, alignItems:'center', justifyContent:'center', background: 'transparent', border: 'none', cursor: busy ? 'not-allowed' : 'pointer', color: method.enabled ? C.accent : C.textSub, padding: 0, display: 'flex', flexShrink: 0 }}
          title={method.enabled ? 'Deaktivieren' : 'Aktivieren'}
        >
          {method.enabled ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
        </button>

        <span style={{ fontSize: 16, flexShrink: 0 }}>{icon}</span>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: method.enabled ? C.text : C.textSub }}>
            {method.label}
          </div>
          <div style={{ fontSize: 10, color: C.textSub }}>
            {method.type} · {method.enabled ? 'Aktiv' : 'Inaktiv'}
          </div>
        </div>

        {busy && (
          <div style={{ width: 12, height: 12, borderRadius: '50%', border: `2px solid ${C.accent}`, borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
        )}

        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          style={{ width:44, minWidth:44, minHeight:44, alignItems:'center', justifyContent:'center', background: 'transparent', border: 'none', cursor: 'pointer', color: C.textSub, padding: 2, display: 'flex' }}
          title="Konfigurieren"
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {expanded && (
        <div style={{ padding: '0 14px 14px' }}>
          <ConfigForm method={method} onSave={onSaveConfig} saving={busy} />
        </div>
      )}
    </div>
  );
}

export interface UseAdminPaymentMethodsResult {
  methods: PaymentMethod[];
  legacyIgnoredCount: number;
  loading: boolean;
  error: string | null;
  reload: () => void;
  toggleMethod: (id: string, enabled: boolean) => Promise<void>;
  saveConfig: (id: string, config: Record<string, string>) => Promise<void>;
  initDefaults: () => Promise<void>;
}

export function PaymentMethodEditor({ api }: { api: UseAdminPaymentMethodsResult }) {
  const {
    methods,
    legacyIgnoredCount,
    loading,
    error,
    reload,
    toggleMethod,
    saveConfig,
    initDefaults,
  } = api;
  const [busyId, setBusyId] = useState<string | null>(null);
  const [initBusy, setInitBusy] = useState(false);

  const handleToggle = async (id: string, enabled: boolean) => {
    setBusyId(id);
    try { await toggleMethod(id, enabled); } finally { setBusyId(null); }
  };

  const handleSaveConfig = async (id: string, config: Record<string, string>) => {
    setBusyId(id);
    try { await saveConfig(id, config); } finally { setBusyId(null); }
  };

  const handleInit = async () => {
    setInitBusy(true);
    try { await initDefaults(); } finally { setInitBusy(false); }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontSize: 11, color: C.textSub, lineHeight: 1.5 }}>
        Zahlungsmethoden konfigurieren — aktivieren/deaktivieren und API-Zugangsdaten hinterlegen.
        Kredentialen werden serverseitig in der Datenbank gespeichert.
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <button
          type="button"
          onClick={reload}
          style={{ minHeight:44, display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 8, padding: '9px 12px', fontSize: 11, color: C.textSub, cursor: 'pointer' }}
        >
          <RefreshCw size={11} /> Neu laden
        </button>
        <button
          type="button"
          onClick={() => void handleInit()}
          disabled={initBusy}
          style={{ minHeight:44, display: 'flex', alignItems: 'center', gap: 6, background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 8, padding: '9px 12px', fontSize: 11, color: C.accent, cursor: initBusy ? 'not-allowed' : 'pointer', opacity: initBusy ? 0.6 : 1 }}
        >
          <Plus size={11} /> Standard-Methoden anlegen
        </button>
      </div>

      {loading && <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>Lade Zahlungsmethoden…</div>}
      {error   && <div style={{ padding: 12, color: C.danger, fontSize: 12, background: '#f8717120', borderRadius: 8 }}>{error}</div>}
      {legacyIgnoredCount > 0 && (
        <div style={{ padding: 12, color: '#fbbf24', fontSize: 12, lineHeight: 1.5, background: '#fbbf2414', border: '1px solid #fbbf2438', borderRadius: 8 }}>
          {legacyIgnoredCount} alte Alias-Datensätze werden als historische Evidenz behalten, aber nicht mehr als konfigurierbare Zahlungsmethoden angezeigt.
        </div>
      )}

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '8px 14px', borderBottom: `1px solid ${C.border}`, fontSize: 10, fontWeight: 700, color: C.textSub, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Zahlungsmethoden ({methods.length})
        </div>
        {!loading && methods.length === 0 && (
          <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>
            Noch keine Methoden. Klicke „Standard-Methoden anlegen".
          </div>
        )}
        {methods.map(m => (
          <MethodRow
            key={m.id}
            method={m}
            onToggle={handleToggle}
            onSaveConfig={handleSaveConfig}
            busyId={busyId}
          />
        ))}
      </div>

      <div style={{ padding: '10px 12px', background: '#00d9b110', border: `1px solid #00d9b130`, borderRadius: 8, fontSize: 10, color: C.textSub, lineHeight: 1.6 }}>
        <strong style={{ color: C.accent }}>Hinweis:</strong> Crypto-Zahlungen müssen nach Eingang vom Admin manuell bestätigt werden
        (Tab Billing → Crypto bestätigen). PayPal und Skrill sind vollautomatisch via Webhook.
        Google Play IAP erfordert ein Service-Account-JSON aus der Google Play Console.
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
