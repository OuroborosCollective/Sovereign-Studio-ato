import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Ban, RefreshCw, ShieldCheck } from 'lucide-react';

import type {
  SelfHealingFailureFamily,
  SelfHealingMode,
} from '../api/adminApiClient';
import { useAdminSelfHealing } from '../hooks/useAdminApi';

const FAMILIES: SelfHealingFailureFamily[] = [
  'EXECUTOR_MISMATCH',
  'ENDPOINT_ROUTE_MISMATCH',
  'HANDOFF_TIMEOUT_WITH_READBACK',
  'JOB_STATE_TRANSITION_VIOLATION',
  'BILLING_ROUTE_MISMATCH',
];

const MODE_LABELS: Record<SelfHealingMode, string> = {
  OBSERVE_ONLY: 'Nur beobachten',
  ASK_FIRST: 'Vor jeder Reparatur fragen',
  AUTO_SAFE: 'Nur sichere Readback-Reparaturen',
  AUTO_BOUNDED_CODE_REPAIR: 'Begrenzte Code-Reparaturen automatisch starten',
};

const card: React.CSSProperties = {
  border: '1px solid #2a3544',
  borderRadius: 14,
  padding: 18,
  background: '#151b23',
};

const field: React.CSSProperties = {
  width: '100%',
  border: '1px solid #344154',
  borderRadius: 8,
  background: '#0f141b',
  color: '#d9e2ec',
  padding: '9px 10px',
};

function shortHash(value: string | null | undefined): string {
  return value ? `${value.slice(0, 12)}…` : '—';
}

export function SelfHealingAuthorityCard() {
  const api = useAdminSelfHealing();
  const [mode, setMode] = useState<SelfHealingMode>('ASK_FIRST');
  const [families, setFamilies] = useState<SelfHealingFailureFamily[]>(FAMILIES);
  const [maxRate, setMaxRate] = useState(1);
  const [maxFiles, setMaxFiles] = useState(8);
  const [expiresInSeconds, setExpiresInSeconds] = useState(86_400);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!api.authority?.configured) return;
    setMode(api.authority.mode);
    setFamilies(api.authority.allowedFailureFamilies.length
      ? api.authority.allowedFailureFamilies
      : FAMILIES);
    setMaxRate(Math.max(1, api.authority.maxAutoRepairsPerHour || 1));
    setMaxFiles(Math.max(1, api.authority.maxChangedFiles || 8));
  }, [api.authority]);

  const expiresLabel = useMemo(() => {
    if (!api.authority?.expiresAt) return 'Kein aktiver Grant';
    const value = new Date(api.authority.expiresAt);
    return Number.isNaN(value.getTime()) ? api.authority.expiresAt : value.toLocaleString('de');
  }, [api.authority?.expiresAt]);

  const toggleFamily = (family: SelfHealingFailureFamily) => {
    setFamilies(current => current.includes(family)
      ? current.filter(item => item !== family)
      : [...current, family]);
  };

  const save = async () => {
    if (!families.length) return;
    setSaving(true);
    try {
      await api.saveAuthority({
        mode,
        allowedFailureFamilies: families,
        maxAutoRepairsPerHour: maxRate,
        maxChangedFiles: maxFiles,
        expiresInSeconds,
        paused: false,
      });
    } finally {
      setSaving(false);
    }
  };

  const revoke = async () => {
    setSaving(true);
    try {
      await api.revokeAuthority();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <section style={card} aria-labelledby="self-healing-authority-title">
        <header style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
          <ShieldCheck size={24} aria-hidden="true" />
          <div style={{ flex: 1 }}>
            <h2 id="self-healing-authority-title" style={{ margin: 0 }}>
              CAG Self-Healing · Authority Boundary
            </h2>
            <p style={{ margin: '6px 0 0', color: '#93a4b8', lineHeight: 1.5 }}>
              Wolfram CAG darf nur den formalen Fehler-Maskenvertrag prüfen. Repository-Code darf
              ausschließlich Agent Zero bearbeiten. Merge, Production-Deploy, Secret-Zugriff und
              direkte Credit-Manipulation bleiben außerhalb dieses Grants.
            </p>
          </div>
          <span
            style={{
              border: '1px solid #344154',
              borderRadius: 999,
              padding: '5px 10px',
              whiteSpace: 'nowrap',
            }}
          >
            {api.authority?.active ? 'Aktiv' : 'Nicht aktiv'}
          </span>
        </header>

        {api.error && (
          <div role="alert" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <AlertTriangle size={18} />
            <span>{api.error}</span>
          </div>
        )}

        <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))' }}>
          <label>
            Modus
            <select value={mode} onChange={event => setMode(event.target.value as SelfHealingMode)} style={field}>
              {Object.entries(MODE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label>
            Automatische Aktionen / Stunde
            <input
              type="number"
              min={1}
              max={10}
              value={maxRate}
              onChange={event => setMaxRate(Number(event.target.value))}
              style={field}
            />
          </label>
          <label>
            Max. geänderte Dateien
            <input
              type="number"
              min={1}
              max={50}
              value={maxFiles}
              onChange={event => setMaxFiles(Number(event.target.value))}
              style={field}
            />
          </label>
          <label>
            Grant-Dauer
            <select
              value={expiresInSeconds}
              onChange={event => setExpiresInSeconds(Number(event.target.value))}
              style={field}
            >
              <option value={3600}>1 Stunde</option>
              <option value={86_400}>24 Stunden</option>
              <option value={604_800}>7 Tage</option>
            </select>
          </label>
        </div>

        <fieldset style={{ margin: '16px 0', border: '1px solid #2a3544', borderRadius: 10 }}>
          <legend>Erlaubte Fehlerfamilien</legend>
          <div style={{ display: 'grid', gap: 8 }}>
            {FAMILIES.map(family => (
              <label key={family} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={families.includes(family)}
                  onChange={() => toggleFamily(family)}
                />
                <code>{family}</code>
              </label>
            ))}
          </div>
        </fieldset>

        <div style={{ display: 'grid', gap: 6, color: '#93a4b8', fontSize: 13, marginBottom: 16 }}>
          <span><b>Grant läuft bis:</b> {expiresLabel}</span>
          <span><b>Grant-Receipt:</b> {shortHash(api.authority?.grantSha256)}</span>
          <span><b>Zuletzt benutzt:</b> {api.authority?.lastUsedAt ? new Date(api.authority.lastUsedAt).toLocaleString('de') : '—'}</span>
          <span><b>Datenzugriff:</b> strukturierte Job-/Transition-/Billing-/Endpoint-Evidence; keine Prompts, Tokens oder Repository-Inhalte an CAG.</span>
          <span><b>Aktionen:</b> sicherer Task-Readback oder genau ein Agent-Zero-Reparaturjob; kein Auto-Merge und kein Auto-Deploy.</span>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <button type="button" onClick={() => void save()} disabled={saving || !families.length}>
            {saving ? 'Speichere…' : 'Scoped Grant speichern'}
          </button>
          <button type="button" onClick={() => void revoke()} disabled={saving || !api.authority?.configured}>
            <Ban size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Sofort widerrufen
          </button>
          <button type="button" onClick={api.reload} disabled={api.loading}>
            <RefreshCw size={15} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            Readback
          </button>
        </div>
      </section>

      <section style={card} aria-labelledby="self-healing-incidents-title">
        <header style={{ marginBottom: 12 }}>
          <h2 id="self-healing-incidents-title" style={{ margin: 0 }}>Action Receipts / Incidents</h2>
          <p style={{ color: '#93a4b8', margin: '6px 0 0' }}>
            Jeder erkannte Fehler, CAG-Abgleich und gestartete Repair bleibt hash- und Job-gebunden nachvollziehbar.
          </p>
        </header>
        {api.loading && <p>Lade Self-Healing-Evidence…</p>}
        {!api.loading && api.incidents.length === 0 && <p>Noch keine Incidents.</p>}
        <div style={{ display: 'grid', gap: 10 }}>
          {api.incidents.map(incident => (
            <article key={incident.incidentId} style={{ border: '1px solid #2a3544', borderRadius: 10, padding: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                <strong><code>{incident.failureFamily}</code></strong>
                <span>{incident.status}</span>
              </div>
              <div style={{ display: 'grid', gap: 4, marginTop: 8, color: '#93a4b8', fontSize: 13 }}>
                <span>Source Job: <code>{incident.sourceJobId}</code></span>
                <span>Observation: <code>{shortHash(incident.observationSha256)}</code></span>
                <span>CAG verified: {incident.cagVerified ? 'ja' : 'nein'}</span>
                <span>Repair Contract: <code>{shortHash(incident.repairContractSha256)}</code></span>
                <span>Repair Job: <code>{incident.repairJobId ?? '—'}</code></span>
                {incident.blocker && <span>Blocker: {incident.blocker}</span>}
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
