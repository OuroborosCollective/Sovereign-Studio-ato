import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  BadgeDollarSign,
  DatabaseZap,
  Plus,
  Power,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
} from 'lucide-react';
import type {
  LlmBillingCategory,
  LlmModelCatalogEntry,
  LlmRoute,
  LlmRouteUpdate,
} from '../api/adminApiClient';
import type { UseAdminLlmRoutesResult } from '../hooks/useAdminApi';
import './LlmRouteControlCenter.css';

const FLOOR: Record<LlmBillingCategory, number> = {
  free: 0,
  standard: 4,
  premium: 8,
};

const CATEGORY_LABEL: Record<LlmBillingCategory, string> = {
  free: 'Free · Revolver',
  standard: 'Standard · mindestens 4×',
  premium: 'Premium · mindestens 8×',
};

function money(value: number | null): string {
  return value === null
    ? 'nicht bestätigt'
    : new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: 'USD',
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
      }).format(value);
}

function RouteCard({
  route,
  busy,
  onUpdate,
  onReset,
}: {
  route: LlmRoute;
  busy: boolean;
  onUpdate: (id: string, changes: LlmRouteUpdate) => Promise<void>;
  onReset: (id: string) => Promise<void>;
}) {
  const [category, setCategory] = useState(route.billingCategory);
  const [multiplier, setMultiplier] = useState(route.markupMultiplier);
  const [priority, setPriority] = useState(route.priority);
  const [quotaScope, setQuotaScope] = useState(route.quotaScope);

  useEffect(() => {
    setCategory(route.billingCategory);
    setMultiplier(route.markupMultiplier);
    setPriority(route.priority);
    setQuotaScope(route.quotaScope);
  }, [route]);

  const categoryChanged = (next: LlmBillingCategory) => {
    setCategory(next);
    setMultiplier(current => Math.max(current, FLOOR[next]));
  };
  const dirty = (
    category !== route.billingCategory
    || multiplier !== route.markupMultiplier
    || priority !== route.priority
    || quotaScope !== route.quotaScope
  );
  const state = route.revolverState;
  const stateLabel = state.status === 'ready'
    ? 'bereit'
    : state.status === 'cooldown'
      ? 'Abkühlung'
      : 'blockiert';

  return (
    <article className={`llm-route-card llm-route-card--${category}`}>
      <header className="llm-route-card__header">
        <div className="llm-route-card__identity">
          <span className={`llm-route-card__status llm-route-card__status--${route.disabled ? 'off' : 'on'}`} />
          <div>
            <h3>{route.modelName || route.modelId}</h3>
            <p>{route.provider} · {route.modelId}</p>
          </div>
        </div>
        <button
          type="button"
          className={`llm-icon-button ${route.disabled ? '' : 'llm-icon-button--active'}`}
          disabled={busy || !route.pricingVerified}
          onClick={() => void onUpdate(route.id, { disabled: !route.disabled })}
          aria-label={route.disabled ? 'Route aktivieren' : 'Route deaktivieren'}
          title={route.pricingVerified
            ? (route.disabled ? 'Route mit Live-Canary aktivieren' : 'Route deaktivieren')
            : 'Ohne verifizierte Preise gesperrt'}
        >
          <Power size={20} />
        </button>
      </header>

      <div className="llm-route-card__badges">
        <span className={route.pricingVerified ? 'llm-badge llm-badge--ok' : 'llm-badge llm-badge--danger'}>
          <ShieldCheck size={14} />
          {route.pricingVerified ? 'Preis verifiziert' : 'Preis gesperrt'}
        </span>
        {route.revolverEligible && (
          <span className={`llm-badge llm-badge--${state.status === 'ready' ? 'ok' : 'warn'}`}>
            <RotateCcw size={14} />
            Revolver {stateLabel}
          </span>
        )}
      </div>

      <div className="llm-route-card__prices" aria-label="Providerpreise pro Million Tokens">
        <div><span>Input</span><strong>{money(route.inputUsdPerMillion)}</strong></div>
        <div><span>Cached</span><strong>{money(route.cachedInputUsdPerMillion)}</strong></div>
        <div><span>Output</span><strong>{money(route.outputUsdPerMillion)}</strong></div>
      </div>

      <div className="llm-form-grid">
        <label>
          <span>Kategorie</span>
          <select
            value={category}
            disabled={busy}
            onChange={event => categoryChanged(event.target.value as LlmBillingCategory)}
          >
            {Object.entries(CATEGORY_LABEL).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Preisfaktor</span>
          <input
            type="number"
            value={multiplier}
            min={FLOOR[category]}
            max={1000}
            disabled={busy || category === 'free'}
            onChange={event => setMultiplier(Math.max(
              FLOOR[category],
              Number.parseInt(event.target.value, 10) || FLOOR[category],
            ))}
          />
        </label>
        <label>
          <span>Priorität</span>
          <input
            type="number"
            value={priority}
            min={-10000}
            max={10000}
            disabled={busy}
            onChange={event => setPriority(Number.parseInt(event.target.value, 10) || 0)}
          />
        </label>
        <label className="llm-form-grid__wide">
          <span>Unabhängiger Quota-Bereich</span>
          <input
            type="text"
            value={quotaScope}
            minLength={8}
            maxLength={128}
            disabled={busy || category !== 'free'}
            onChange={event => setQuotaScope(event.target.value)}
            aria-describedby={`quota-help-${route.id}`}
          />
          <small id={`quota-help-${route.id}`}>
            Routen mit demselben Schlüssel gehören in denselben Bereich und werden nicht doppelt rotiert.
          </small>
        </label>
      </div>

      {route.policyBlocker && <p className="llm-route-card__error">{route.policyBlocker}</p>}
      {state.lastBlocker && (
        <p className="llm-route-card__evidence">
          Letzter Lauf: {state.lastBlocker}
          {state.lastHttpStatus ? ` · HTTP ${state.lastHttpStatus}` : ''}
          {state.consecutiveFailures ? ` · ${state.consecutiveFailures} Fehler` : ''}
        </p>
      )}

      <footer className="llm-route-card__actions">
        <button
          type="button"
          className="llm-button llm-button--primary"
          disabled={busy || !dirty}
          onClick={() => void onUpdate(route.id, {
            billingCategory: category,
            markupMultiplier: multiplier,
            priority,
            quotaScope,
          })}
        >
          {busy ? <RefreshCw className="llm-spin" size={17} /> : <ShieldCheck size={17} />}
          Regeln speichern
        </button>
        {route.revolverEligible && state.status !== 'ready' && (
          <button
            type="button"
            className="llm-button"
            disabled={busy}
            onClick={() => void onReset(route.id)}
          >
            <RotateCcw size={17} />
            Quota-Zustand zurücksetzen
          </button>
        )}
      </footer>
    </article>
  );
}

function CatalogAttach({
  catalog,
  busy,
  onAttach,
}: {
  catalog: LlmModelCatalogEntry[];
  busy: boolean;
  onAttach: (
    modelId: string,
    category: LlmBillingCategory,
    multiplier: number,
    priority: number,
  ) => Promise<void>;
}) {
  const [modelId, setModelId] = useState('');
  const [category, setCategory] = useState<LlmBillingCategory>('standard');
  const [multiplier, setMultiplier] = useState(4);
  const [priority, setPriority] = useState(50);
  const selected = catalog.find(model => model.modelId === modelId);

  const chooseCategory = (next: LlmBillingCategory) => {
    setCategory(next);
    setMultiplier(FLOOR[next]);
  };

  return (
    <section className="llm-catalog">
      <div className="llm-section-title">
        <div><DatabaseZap size={21} /><div><h2>LiteLLM-Modellkatalog</h2><p>Nur live erkannte Modelle mit Providerpreisen.</p></div></div>
      </div>
      <div className="llm-catalog__form">
        <label className="llm-catalog__model">
          <span>Erkanntes Modell</span>
          <select value={modelId} disabled={busy} onChange={event => setModelId(event.target.value)}>
            <option value="">Modell auswählen</option>
            {catalog.map(model => (
              <option key={model.modelId} value={model.modelId}>
                {model.modelId}{model.freeEligible ? ' · Free bestätigt' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Kategorie</span>
          <select
            value={category}
            disabled={busy}
            onChange={event => chooseCategory(event.target.value as LlmBillingCategory)}
          >
            <option value="free" disabled={!selected?.freeEligible}>Free</option>
            <option value="standard">Standard 4×+</option>
            <option value="premium">Premium 8×+</option>
          </select>
        </label>
        <label>
          <span>Faktor</span>
          <input
            type="number"
            min={FLOOR[category]}
            max={1000}
            value={multiplier}
            disabled={busy || category === 'free'}
            onChange={event => setMultiplier(Math.max(
              FLOOR[category],
              Number.parseInt(event.target.value, 10) || FLOOR[category],
            ))}
          />
        </label>
        <label>
          <span>Priorität</span>
          <input type="number" value={priority} min={-10000} max={10000} disabled={busy}
            onChange={event => setPriority(Number.parseInt(event.target.value, 10) || 0)} />
        </label>
        <button
          type="button"
          className="llm-button llm-button--primary"
          disabled={busy || !selected || !selected.pricingVerified || (category === 'free' && !selected.freeEligible)}
          onClick={() => modelId && void onAttach(modelId, category, multiplier, priority)}
        >
          <Plus size={18} /> Mit Canary hinzufügen
        </button>
      </div>
      {selected && (
        <p className="llm-catalog__evidence">
          {selected.provider || 'Provider'} · Input {money(selected.inputUsdPerMillion)} ·
          Output {money(selected.outputUsdPerMillion)} · Quelle {selected.pricingSource}
        </p>
      )}
    </section>
  );
}

export function LlmRouteEditor({ api }: { api: UseAdminLlmRoutesResult }) {
  const {
    routes,
    revolverStats,
    catalog,
    catalogError,
    loading,
    error,
    reload,
    updateRoute,
    resetRevolver,
    attachModel,
  } = api;
  const [busyId, setBusyId] = useState<string | null>(null);
  const activeRoutes = useMemo(() => routes.filter(route => !route.disabled).length, [routes]);

  const run = async (id: string, action: () => Promise<void>) => {
    setBusyId(id);
    try {
      await action();
    } finally {
      setBusyId(null);
    }
  };

  if (loading && routes.length === 0) {
    return <div className="llm-panel-state"><RefreshCw className="llm-spin" />LLM-Laufzeit wird geladen…</div>;
  }

  return (
    <div className="llm-control-center">
      <div className="llm-control-center__hero">
        <div>
          <span className="llm-kicker">LLM Models / Routes</span>
          <h1>Preisgesteuerte Modell-Laufzeit</h1>
          <p>Free rotiert nur über unabhängige, nullpreis-verifizierte Routen. Bezahlte Routen werden nie still gewechselt.</p>
        </div>
        <button type="button" className="llm-button" onClick={reload} disabled={loading || busyId !== null}>
          <RefreshCw className={loading ? 'llm-spin' : ''} size={18} /> Aktualisieren
        </button>
      </div>

      <div className="llm-stat-grid">
        <div><Activity /><span>Aktive Routen</span><strong>{activeRoutes}</strong></div>
        <div><RotateCcw /><span>Rotationen 24 h</span><strong>{revolverStats?.rotations24h ?? 0}</strong></div>
        <div><ShieldCheck /><span>Erfolge 24 h</span><strong>{revolverStats?.successes24h ?? 0}</strong></div>
        <div><BadgeDollarSign /><span>Blockiert / Kühlung</span><strong>{revolverStats?.blockedOrCoolingScopes ?? 0}</strong></div>
      </div>

      {error && <div className="llm-alert llm-alert--danger">{error}</div>}
      {catalogError && <div className="llm-alert">Modellkatalog derzeit nicht verfügbar: {catalogError}</div>}

      <CatalogAttach
        catalog={catalog}
        busy={busyId !== null}
        onAttach={(modelId, category, multiplier, priority) => run(
          'catalog',
          () => attachModel(modelId, category, multiplier, priority),
        )}
      />

      <section>
        <div className="llm-section-title">
          <div><Activity size={21} /><div><h2>Aktive Konfiguration</h2><p>{routes.length} persistierte Routen</p></div></div>
        </div>
        <div className="llm-route-grid">
          {routes.map(route => (
            <RouteCard
              key={route.id}
              route={route}
              busy={busyId === route.id}
              onUpdate={(id, changes) => run(id, () => updateRoute(id, changes))}
              onReset={id => run(id, () => resetRevolver(id))}
            />
          ))}
          {routes.length === 0 && (
            <div className="llm-empty">Noch keine preisverifizierte Route. Wähle oben ein erkanntes Modell.</div>
          )}
        </div>
      </section>
    </div>
  );
}
