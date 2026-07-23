import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Database,
  Gauge,
  RefreshCw,
  ServerCog,
  ShieldCheck,
  Sparkles,
  XCircle,
} from 'lucide-react';
import {
  adminApiClient,
  type EnterpriseCanaryResult,
  type EnterpriseEvidenceReceipt,
  type EnterpriseIntegration,
  type EnterprisePlatformOverview,
  type EnterprisePlatformStatus,
} from '../api/adminApiClient';
import './EnterpriseBackendPanel.css';

const STATUS_LABELS: Record<EnterprisePlatformStatus, string> = {
  verified: 'Verifiziert',
  degraded: 'Eingeschränkt',
  blocked: 'Blockiert',
  defined_not_run: 'Definiert · ungeprüft',
  isolated: 'Bewusst isoliert',
};

function StatusIcon({ status, size = 16 }: { status: EnterprisePlatformStatus; size?: number }) {
  if (status === 'verified') return <CheckCircle2 size={size} aria-hidden="true" />;
  if (status === 'blocked') return <XCircle size={size} aria-hidden="true" />;
  if (status === 'degraded') return <AlertTriangle size={size} aria-hidden="true" />;
  return <CircleDashed size={size} aria-hidden="true" />;
}

function StatusBadge({ status }: { status: EnterprisePlatformStatus }) {
  return (
    <span className="sbp-status" data-status={status}>
      <StatusIcon status={status} />
      {STATUS_LABELS[status]}
    </span>
  );
}

function compactIdentity(value: string): string {
  if (!value || value === 'unverified') return 'nicht verifiziert';
  if (value.length <= 22) return value;
  return value.slice(0, 12) + '…' + value.slice(-8);
}

function localDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? '—' : date.toLocaleString('de-DE');
}

function number(value: number | null | undefined, maximumFractionDigits = 0): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('de-DE', { maximumFractionDigits }).format(value);
}

function evidenceValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'ja' : 'nein';
  if (typeof value === 'number') return number(value, 4);
  if (Array.isArray(value)) return value.map(String).join(', ') || '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '[nicht darstellbar]';
    }
  }
  return String(value);
}

function integrationEvidence(integration: EnterpriseIntegration) {
  return Object.entries(integration.evidence).slice(0, 6);
}

export function EnterpriseBackendPanel() {
  const [overview, setOverview] = useState<EnterprisePlatformOverview | null>(null);
  const [evidence, setEvidence] = useState<EnterpriseEvidenceReceipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [runningCanary, setRunningCanary] = useState<'readiness' | null>(null);
  const [lastCanary, setLastCanary] = useState<EnterpriseCanaryResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      const nextOverview = await adminApiClient.getEnterprisePlatformOverview();
      setOverview(nextOverview);
      try {
        const nextEvidence = await adminApiClient.getEnterprisePlatformEvidence(30);
        setEvidence(nextEvidence.evidence);
      } catch (evidenceError) {
        setEvidence([]);
        setError('Runtime-Daten geladen; Evidence-Liste nicht verfügbar: ' + String(evidenceError));
      }
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      if (showSpinner) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const runReadinessCanary = async () => {
    setRunningCanary('readiness');
    setLastCanary(null);
    setError(null);
    try {
      const result = await adminApiClient.runEnterprisePlatformCanary('readiness');
      setLastCanary(result);
    } catch (nextError) {
      setError(String(nextError));
    } finally {
      setRunningCanary(null);
      await refresh(false);
    }
  };

  if (loading && !overview) {
    return (
      <div className="sbp-loading" role="status">
        <RefreshCw className="sbp-spin" size={24} aria-hidden="true" />
        Verifizierte Backend-Daten werden geladen…
      </div>
    );
  }

  if (!overview) {
    return (
      <section className="sbp-shell">
        <div className="sbp-alert" role="alert">
          <AlertTriangle size={20} aria-hidden="true" />
          <div>
            <strong>Backend-Plattform nicht erreichbar</strong>
            <span>{error ?? 'Unbekannter Verbindungsfehler'}</span>
          </div>
        </div>
        <button className="sbp-button sbp-button-primary" type="button" onClick={() => void refresh()}>
          <RefreshCw size={18} aria-hidden="true" />
          Erneut verbinden
        </button>
      </section>
    );
  }

  const stats = overview.statistics;
  const statCards = [
    {
      label: 'Aktive Nutzer · 30 Tage',
      value: number(stats.users?.active30d),
      detail: number(stats.users?.total) + ' gesamt',
      icon: Activity,
    },
    {
      label: 'Agent-Runs',
      value: number(stats.agents?.total),
      detail: number(stats.agents?.completed) + ' abgeschlossen',
      icon: Sparkles,
    },
    {
      label: 'pgvector-Wissensvektoren',
      value: number(stats.knowledge?.pgvectorVectors ?? stats.knowledge?.vectors),
      detail: number(stats.knowledge?.sources) + ' Quellen · kanonisch',
      icon: Database,
    },
    {
      label: 'Milvus-Projektion',
      value: number(stats.knowledge?.milvusIndexed),
      detail:
        number(stats.knowledge?.milvusProjected) + ' gesamt · ' +
        number((stats.knowledge?.milvusPending ?? 0) + (stats.knowledge?.milvusSyncing ?? 0)) + ' offen · ' +
        number(stats.knowledge?.milvusBlocked) + ' blockiert',
      icon: Database,
    },
    {
      label: 'LLM-Anfragen · 24 h',
      value: number(stats.llm24h?.requests),
      detail: number(stats.llm24h?.tokens) + ' Tokens',
      icon: Gauge,
    },
    {
      label: 'Provider-Kosten · 24 h',
      value: stats.llm24h ? '$' + number(stats.llm24h.providerCostUsd, 4) : '—',
      detail: number(stats.llm24h?.activeRoutes) + ' aktive Routen',
      icon: ServerCog,
    },
    {
      label: 'Runtime-Belege',
      value: number(stats.evidence?.total),
      detail: 'Migration ' + number(stats.database?.latestMigration),
      icon: ShieldCheck,
    },
  ];

  const requiredVerified = overview.integrations.filter(
    item => item.required && item.status === 'verified',
  ).length;
  const requiredTotal = overview.integrations.filter(item => item.required).length;

  return (
    <section className="sbp-shell" aria-label="Enterprise Backend Platform">
      <header className="sbp-hero">
        <div className="sbp-hero-copy">
          <div className="sbp-eyebrow">
            <ShieldCheck size={15} aria-hidden="true" />
            Enterprise Backend · {overview.schemaVersion}
          </div>
          <div className="sbp-title-row">
            <h1>Runtime Control Center</h1>
            <StatusBadge status={overview.status} />
          </div>
          <p>{overview.truthNotice}</p>
        </div>
        <button
          className="sbp-icon-button"
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          aria-label="Backend-Daten aktualisieren"
        >
          <RefreshCw className={loading ? 'sbp-spin' : undefined} size={20} aria-hidden="true" />
        </button>
      </header>

      {error && (
        <div className="sbp-alert" role="alert">
          <AlertTriangle size={19} aria-hidden="true" />
          <div>
            <strong>Aktueller Hinweis</strong>
            <span>{error}</span>
          </div>
        </div>
      )}

      {lastCanary && (
        <div className="sbp-canary-result" data-status={lastCanary.status} aria-live="polite">
          <StatusIcon status={lastCanary.status} size={19} />
          <div>
            <strong>Readiness-Canary gespeichert</strong>
            <span>
              Beleg {compactIdentity(lastCanary.receipt.evidenceSha256)} · Readback verifiziert
            </span>
          </div>
        </div>
      )}

      <div className="sbp-runtime-grid">
        <article className="sbp-runtime-card">
          <span>Source Revision</span>
          <strong title={overview.runtime.sourceRevision}>
            {compactIdentity(overview.runtime.sourceRevision)}
          </strong>
          <small data-verified={overview.runtime.sourceRevisionVerified}>
            {overview.runtime.sourceRevisionVerified ? 'Build-Revision verifiziert' : 'Build-Revision fehlt'}
          </small>
        </article>
        <article className="sbp-runtime-card">
          <span>Image Digest</span>
          <strong title={overview.runtime.imageDigest}>
            {compactIdentity(overview.runtime.imageDigest)}
          </strong>
          <small data-verified={overview.runtime.imageDigestVerified}>
            {overview.runtime.imageDigestVerified ? 'Container-Identität verifiziert' : 'Digest nicht injiziert'}
          </small>
        </article>
        <article className="sbp-runtime-card">
          <span>Pflichtintegrationen</span>
          <strong>{requiredVerified} / {requiredTotal}</strong>
          <small data-verified={requiredVerified === requiredTotal}>
            {requiredVerified === requiredTotal ? 'Alle verifiziert' : 'Mindestens eine blockiert'}
          </small>
        </article>
        <article className="sbp-runtime-card">
          <span>Runtime gestartet</span>
          <strong>{localDate(overview.runtime.startedAt)}</strong>
          <small>{overview.runtime.environment}</small>
        </article>
      </div>

      <div className="sbp-section-heading">
        <div>
          <span>Live-Telemetrie</span>
          <h2>Statistiken</h2>
        </div>
        <StatusBadge status={stats.status} />
      </div>
      <div className="sbp-stats-grid">
        {statCards.map(card => {
          const Icon = card.icon;
          return (
            <article className="sbp-stat-card" key={card.label}>
              <Icon size={19} aria-hidden="true" />
              <span>{card.label}</span>
              <strong>{card.value}</strong>
              <small>{card.detail}</small>
            </article>
          );
        })}
      </div>

      <div className="sbp-section-heading">
        <div>
          <span>Beweisgebundene Zustände</span>
          <h2>Integrationen & Architekturen</h2>
        </div>
        <span className="sbp-timestamp">{localDate(overview.generatedAt)}</span>
      </div>
      <div className="sbp-integration-grid">
        {overview.integrations.map(integration => (
          <article className="sbp-integration-card" key={integration.id} data-status={integration.status}>
            <div className="sbp-integration-head">
              <div>
                <h3>{integration.label}</h3>
                <span>{integration.required ? 'Pflichtintegration' : 'Optionale Grenze'}</span>
              </div>
              <StatusBadge status={integration.status} />
            </div>
            <p>{integration.boundary}</p>
            {integration.blocker && (
              <div className="sbp-blocker">
                <AlertTriangle size={14} aria-hidden="true" />
                {integration.blocker}
              </div>
            )}
            <dl>
              {integrationEvidence(integration).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd title={evidenceValue(value)}>{evidenceValue(value)}</dd>
                </div>
              ))}
            </dl>
            <footer>
              <span>{integration.latencyMs === null ? 'lokale Grenze' : number(integration.latencyMs) + ' ms'}</span>
              <span>{localDate(integration.checkedAt)}</span>
            </footer>
          </article>
        ))}
      </div>

      <div className="sbp-section-heading">
        <div>
          <span>Kontrollierte Verifikation</span>
          <h2>Runtime Canaries</h2>
        </div>
      </div>
      <div className="sbp-canary-grid">
        <article className="sbp-action-card">
          <div>
            <h3>Readiness-Beleg</h3>
            <p>Prüft alle erlaubten, privaten Backend-Grenzen und speichert den exakten Befund mit SHA-256-Readback.</p>
          </div>
          <button
            className="sbp-button sbp-button-primary"
            type="button"
            onClick={() => void runReadinessCanary()}
            disabled={runningCanary !== null}
          >
            <RefreshCw className={runningCanary === 'readiness' ? 'sbp-spin' : undefined} size={18} aria-hidden="true" />
            {runningCanary === 'readiness' ? 'Prüfung läuft…' : 'Readiness prüfen'}
          </button>
        </article>
      </div>

      <div className="sbp-section-heading">
        <div>
          <span>Unveränderliche Receipts</span>
          <h2>Runtime Evidence</h2>
        </div>
        <span className="sbp-count">{evidence.length} geladen</span>
      </div>
      <div className="sbp-evidence-list">
        {evidence.length === 0 && (
          <div className="sbp-empty">
            <CircleDashed size={22} aria-hidden="true" />
            Noch keine lesbaren Runtime-Belege vorhanden.
          </div>
        )}
        {evidence.map(receipt => (
          <article className="sbp-evidence-row" key={receipt.id}>
            <StatusBadge status={receipt.status} />
            <div className="sbp-evidence-main">
              <strong>{receipt.scope === 'completion' ? 'Historischer Completion-Beleg' : 'Readiness Canary'}</strong>
              <span>{localDate(receipt.observedAt)} · Revision {compactIdentity(receipt.sourceRevision)}</span>
            </div>
            <code title={receipt.evidenceSha256}>{compactIdentity(receipt.evidenceSha256)}</code>
          </article>
        ))}
      </div>
    </section>
  );
}
