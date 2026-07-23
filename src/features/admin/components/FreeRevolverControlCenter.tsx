import { useMemo, useState } from 'react';
import {
  KeyRound,
  Lock,
  Power,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
} from 'lucide-react';
import type { FreeRevolverProviderAuthMode } from '../api/adminApiClient';
import type { UseAdminFreeRevolverProvidersResult } from '../hooks/useAdminApi';

const FREELLMAPI_DOCKER_API_BASE = 'http://freellmapi:3001/v1';

const AUTH_LABELS: Record<FreeRevolverProviderAuthMode, string> = {
  bearer: 'Bearer API-Key',
  'x-api-key': 'X-API-Key',
  none: 'Kein Key erforderlich',
  'managed-bearer': 'Owner-managed Docker-Key',
};

function statusLabel(status: string): string {
  switch (status) {
    case 'healthy': return 'gesund';
    case 'probing': return 'wird geprüft';
    case 'awaiting_owner_input': return 'Key fehlt';
    case 'degraded': return 'eingeschränkt';
    case 'disabled': return 'deaktiviert';
    default: return 'blockiert';
  }
}

function isPricingEvidenceFresh(verifiedAt: string | null, ttlHours: number): boolean {
  if (!verifiedAt) return false;
  const verified = new Date(verifiedAt);
  return !Number.isNaN(verified.getTime())
    && verified.getTime() + ttlHours * 60 * 60 * 1000 > Date.now();
}

function pricingEvidenceExpiry(verifiedAt: string | null, ttlHours: number): string {
  if (!verifiedAt) return 'Preis-Evidence fehlt';
  const verified = new Date(verifiedAt);
  if (Number.isNaN(verified.getTime())) return 'Preis-Evidence-Datum ungültig';
  const expires = new Date(verified.getTime() + ttlHours * 60 * 60 * 1000);
  const formatted = new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(expires);
  return expires.getTime() > Date.now()
    ? `Preis-Evidence gültig bis ${formatted}`
    : `Preis-Evidence abgelaufen seit ${formatted}`;
}

export function FreeRevolverControlCenter({
  api,
  pricingEvidenceTtlHours,
}: {
  api: UseAdminFreeRevolverProvidersResult;
  pricingEvidenceTtlHours: number;
}) {
  const [label, setLabel] = useState('');
  const [apiBase, setApiBase] = useState('');
  const [authMode, setAuthMode] = useState<FreeRevolverProviderAuthMode>('bearer');
  const [apiKey, setApiKey] = useState('');
  const [renewalKeys, setRenewalKeys] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const totals = useMemo(() => {
    const models = api.providers.flatMap(provider => provider.models);
    return {
      providers: api.providers.length,
      ready: models.filter(model => (
        model.status === 'ready'
        && model.enabled
        && isPricingEvidenceFresh(model.pricingVerifiedAt, pricingEvidenceTtlHours)
      )).length,
      deferred: models.filter(model => model.status === 'discovered').length,
      blocked: models.filter(model => model.status === 'blocked').length,
      verified: models.filter(model => (
        model.freeVerified
        && isPricingEvidenceFresh(model.pricingVerifiedAt, pricingEvidenceTtlHours)
      )).length,
    };
  }, [api.providers, pricingEvidenceTtlHours]);

  const run = async (id: string, action: () => Promise<void>, success: string) => {
    setBusyId(id);
    setActionError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusyId(null);
    }
  };

  const submitProvider = () => {
    const protectedValue = apiKey;
    setApiKey('');
    void run('new-provider', async () => {
      const parsed = new URL(apiBase);
      const managedDockerTarget = apiBase.trim().replace(/\/$/, '') === FREELLMAPI_DOCKER_API_BASE;
      if (parsed.protocol !== 'https:' && !managedDockerTarget) {
        throw new Error('Nur vollständige HTTPS-URLs oder der verwaltete FreeLLM-API-Docker-Endpunkt sind erlaubt.');
      }
      if (!label.trim()) throw new Error('Bitte einen verständlichen Provider-Namen eintragen.');
      if ((authMode === 'bearer' || authMode === 'x-api-key') && protectedValue.length < 8) {
        throw new Error('Der API-Key muss mindestens 8 Zeichen enthalten.');
      }
      await api.createAndDiscover({
        label: label.trim(),
        apiBase: apiBase.trim(),
        authMode,
        apiKey: protectedValue,
      });
      setLabel('');
      setApiBase('');
    }, 'Provider geprüft. Nur Modelle mit unabhängiger Nullpreis-Evidence und erfolgreicher Completion wurden aktiviert.');
  };

  const renewProvider = (sourceId: string) => {
    const protectedValue = renewalKeys[sourceId] ?? '';
    setRenewalKeys(current => ({ ...current, [sourceId]: '' }));
    void run(`renew-${sourceId}`, async () => {
      await api.renewAndDiscover(sourceId, protectedValue);
    }, 'Key erneuert, Providerpreise neu erkannt und echte Completion-Canaries ausgeführt.');
  };

  return (
    <div className="free-revolver-admin">
      <section className="llm-control-center__hero free-revolver-admin__hero">
        <div>
          <span className="llm-kicker">Free Revolver / Nullkosten-Routen</span>
          <h1>Kostenfreie Provider sicher verbinden</h1>
          <p>
            Der Key wird einmalig über den geschützten Owner-Kanal übertragen und nie in der
            Sovereign-Datenbank gespeichert. Aktiviert werden ausschließlich Modelle mit
            expliziter Nullkosten-Evidence und zwei echten direkten FreeLLM-Completion-Canaries,
            die keinen positiven Kostenwert melden. Fehlende oder abgekühlte Upstreams bleiben
            prüfbar und werden nicht mehr fälschlich als defekte Modelle dargestellt.
          </p>
        </div>
        <button type="button" className="llm-button" disabled={api.loading || busyId !== null} onClick={api.reload}>
          <RefreshCw className={api.loading ? 'llm-spin' : ''} size={18} /> Aktualisieren
        </button>
      </section>

      <div className="llm-stat-grid">
        <div><Server /><span>Provider</span><strong>{totals.providers}</strong></div>
        <div><ShieldCheck /><span>Aktive Free-Routen</span><strong>{totals.ready}</strong></div>
        <div><Search /><span>Nullkosten bestätigt</span><strong>{totals.verified}</strong></div>
        <div><RefreshCw /><span>Wartet auf Upstream</span><strong>{totals.deferred}</strong></div>
        <div><Lock /><span>Hart blockiert</span><strong>{totals.blocked}</strong></div>
      </div>

      <section className="llm-catalog free-revolver-admin__onboarding">
        <div className="llm-section-title">
          <div><KeyRound size={21} /><div>
            <h2>Provider automatisch erkennen</h2>
            <p>Basis-URL genügt; `/v1/models` und `/models` werden sicher geprüft.</p>
          </div></div>
        </div>
        <button type="button" className="llm-button"
          disabled={busyId !== null}
          onClick={() => {
            setLabel('FreeLLM API 0.5.0 · interner Docker');
            setApiBase(FREELLMAPI_DOCKER_API_BASE);
            setAuthMode('managed-bearer');
            setApiKey('');
          }}>
          <Server size={17} /> FreeLLM API 0.5.0 auswählen
        </button>
        <div className="free-revolver-form">
          <label>
            <span>Provider-Name</span>
            <input value={label} maxLength={120} disabled={busyId !== null}
              placeholder="z. B. Mein Free Provider"
              onChange={event => setLabel(event.target.value)} />
          </label>
          <label>
            <span>API-Basis</span>
            <input value={apiBase} disabled={busyId !== null} inputMode="url"
              placeholder="https://api.provider.example oder interner FreeLLM-Docker"
              onChange={event => setApiBase(event.target.value)} />
          </label>
          <label>
            <span>Authentifizierung</span>
            <select value={authMode} disabled={busyId !== null}
              onChange={event => setAuthMode(event.target.value as FreeRevolverProviderAuthMode)}>
              {Object.entries(AUTH_LABELS).map(([value, text]) => (
                <option key={value} value={value}>{text}</option>
              ))}
            </select>
          </label>
          <label>
            <span>{authMode === 'none'
              ? 'API-Key nicht erforderlich'
              : authMode === 'managed-bearer'
                ? 'Interner Schlüssel · owner-managed'
                : 'API-Key · einmalige Übergabe'}</span>
            <input type="password" autoComplete="new-password" spellCheck={false}
              value={apiKey} disabled={busyId !== null || authMode === 'none' || authMode === 'managed-bearer'}
              placeholder={authMode === 'none'
                ? 'Kein Key wird übertragen'
                : authMode === 'managed-bearer'
                  ? 'Wird aus der geschützten Owner-Datei gelesen'
                  : 'Wird nach Übergabe sofort aus dem Formular gelöscht'}
              onChange={event => setApiKey(event.target.value)} />
          </label>
          <button type="button" className="llm-button llm-button--primary"
            disabled={busyId !== null || !label.trim() || !apiBase.trim()
              || ((authMode === 'bearer' || authMode === 'x-api-key') && apiKey.length < 8)}
            onClick={submitProvider}>
            {busyId === 'new-provider' ? <RefreshCw className="llm-spin" size={18} /> : <Search size={18} />}
            Sicher prüfen und Free-Routen anlegen
          </button>
        </div>
        <p className="llm-catalog__evidence">
          Kostenpflichtige, unvollständig bepreiste oder nur dem Namen nach „freie“ Modelle bleiben automatisch blockiert.
        </p>
      </section>

      {(api.error || actionError) && (
        <div className="llm-alert llm-alert--danger">{actionError ?? api.error}</div>
      )}
      {notice && <div className="llm-alert free-revolver-admin__notice">{notice}</div>}

      <section>
        <div className="llm-section-title">
          <div><Server size={21} /><div>
            <h2>Free-Provider und Runtime-Evidence</h2>
            <p>{api.providers.length} persistierte Providerquellen</p>
          </div></div>
        </div>
        <div className="free-revolver-provider-grid">
          {api.providers.map(provider => {
            const readyModels = provider.models.filter(model => (
              model.status === 'ready'
              && model.enabled
              && isPricingEvidenceFresh(model.pricingVerifiedAt, pricingEvidenceTtlHours)
            ));
            const deferredModels = provider.models.filter(model => model.status === 'discovered');
            const blockedModels = provider.models.filter(model => model.status === 'blocked');
            const recheckableModels = provider.models.filter(model => (
              model.freeVerified && Boolean(model.litellmAlias)
            ));
            const renewalKey = renewalKeys[provider.id] ?? '';
            return (
              <article key={provider.id} className={`llm-route-card free-revolver-provider free-revolver-provider--${provider.status}`}>
                <header className="llm-route-card__header">
                  <div className="llm-route-card__identity">
                    <span className={`llm-route-card__status llm-route-card__status--${provider.status === 'healthy' && provider.enabled ? 'on' : 'off'}`} />
                    <div>
                      <h3>{provider.label}</h3>
                      <p>{provider.apiBase}</p>
                    </div>
                  </div>
                  <button type="button" className={`llm-icon-button ${provider.enabled ? 'llm-icon-button--active' : ''}`}
                    disabled={busyId !== null}
                    title={provider.enabled ? 'Provider und alle Routen deaktivieren' : 'Provider wieder freigeben'}
                    aria-label={provider.enabled ? 'Provider deaktivieren' : 'Provider aktivieren'}
                    onClick={() => void run(
                      `toggle-${provider.id}`,
                      () => api.toggle(provider.id, !provider.enabled),
                      provider.enabled
                        ? 'Providerquelle deaktiviert. Alle zugehörigen Routen bleiben gesperrt.'
                        : 'Providerquelle freigegeben. Routen bleiben fail-closed gesperrt, bis Discovery und Completion-Healthcheck erfolgreich sind.',
                    )}>
                    <Power size={19} />
                  </button>
                </header>

                <div className="llm-route-card__badges">
                  <span className={`llm-badge llm-badge--${provider.status === 'healthy' ? 'ok' : provider.status === 'blocked' ? 'danger' : 'warn'}`}>
                    <ShieldCheck size={14} /> {statusLabel(provider.status)}
                  </span>
                  <span className="llm-badge"><KeyRound size={14} /> {provider.keyHint ?? AUTH_LABELS[provider.authMode]}</span>
                  <span className="llm-badge llm-badge--ok">{readyModels.length} aktiv</span>
                  {deferredModels.length > 0 && <span className="llm-badge llm-badge--warn">{deferredModels.length} wartet auf Upstream</span>}
                  {blockedModels.length > 0 && <span className="llm-badge llm-badge--danger">{blockedModels.length} hart blockiert</span>}
                </div>

                <div className="free-revolver-provider__facts">
                  <div><span>Models-Endpunkt</span><strong>{provider.modelsUrl ?? 'noch nicht erkannt'}</strong></div>
                  <div><span>Letzte Preis-Discovery</span><strong>{provider.lastDiscoveredAt ?? 'noch keine'}</strong></div>
                  <div><span>Letzter Completion-Check</span><strong>{provider.lastCheckedAt ?? 'noch keiner'}</strong></div>
                  <div><span>HTTP / Blocker</span><strong>{provider.lastHttpStatus ?? '—'}{provider.lastErrorCode ? ` · ${provider.lastErrorCode}` : ''}</strong></div>
                </div>

                <div className="free-revolver-model-list">
                  {provider.models.map(model => {
                    const pricingFresh = isPricingEvidenceFresh(
                      model.pricingVerifiedAt,
                      pricingEvidenceTtlHours,
                    );
                    const effectiveReady = model.status === 'ready' && model.enabled && pricingFresh;
                    return (
                    <div key={model.id} className="free-revolver-model">
                      <div>
                        <strong>{model.displayName || model.modelId}</strong>
                        <span>{model.modelId}</span>
                        <span>{pricingEvidenceExpiry(model.pricingVerifiedAt, pricingEvidenceTtlHours)}</span>
                      </div>
                      <span className={`llm-badge llm-badge--${effectiveReady ? 'ok' : model.status === 'discovered' ? 'warn' : 'danger'}`}>
                        {!pricingFresh
                          ? 'Preis-Evidence abgelaufen'
                          : model.status === 'discovered'
                            ? `wartet auf verfügbaren Upstream · ${model.lastErrorCode ?? 'noch nicht erfolgreich geprüft'}`
                            : model.status !== 'ready'
                              ? model.lastErrorCode ?? model.pricingSource
                              : model.canaryCostState === 'zero'
                              ? 'Nullpreis + Canary Kosten 0'
                              : 'Nullpreis + Canary ohne Kostenangabe'}
                      </span>
                    </div>
                    );
                  })}
                  {provider.models.length === 0 && (
                    <p className="llm-route-card__evidence">Noch keine Modell-Evidence. Key eintragen und Discovery starten.</p>
                  )}
                </div>

                <footer className="llm-route-card__actions">
                  {(provider.authMode === 'none' || provider.authMode === 'managed-bearer') && (
                    <button type="button" className="llm-button llm-button--primary"
                      disabled={busyId !== null || !provider.enabled}
                      onClick={() => void run(
                        `discover-${provider.id}`,
                        () => api.discover(provider.id),
                        'Discovery abgeschlossen. Erfolgreich doppelt gecanaryte Modelle wurden aktiviert; temporär nicht erreichbare Upstreams bleiben sichtbar und erneut prüfbar, echte Policy-Verstöße bleiben blockiert.',
                      )}>
                      <Search size={17} /> Modelle + Preise neu erkennen
                    </button>
                  )}
                  <button type="button" className="llm-button" disabled={busyId !== null || !provider.enabled || recheckableModels.length === 0}
                    onClick={() => void run(
                      `recheck-${provider.id}`,
                      () => api.recheck(provider.id),
                      'Alle bekannten Free-Routen wurden erneut mit echter Completion geprüft.',
                    )}>
                    <RefreshCw className={busyId === `recheck-${provider.id}` ? 'llm-spin' : ''} size={17} />
                    Completion-Healthcheck
                  </button>
                  {provider.enabled && recheckableModels.length === 0 && (
                    <p className="llm-route-card__evidence">
                      Noch kein Modell ist healthcheckfähig. Zuerst Modelle und Preise neu erkennen.
                    </p>
                  )}
                </footer>

                {(provider.authMode === 'bearer' || provider.authMode === 'x-api-key') && (
                  <div className="free-revolver-provider__renew">
                    <label>
                      <span>Neuen Key eintragen und Modelle neu erkennen</span>
                      <input type="password" autoComplete="new-password" spellCheck={false}
                        value={renewalKey} disabled={busyId !== null}
                        placeholder="Einmalige geschützte Übergabe"
                        onChange={event => setRenewalKeys(current => ({ ...current, [provider.id]: event.target.value }))} />
                    </label>
                    <button type="button" className="llm-button llm-button--primary"
                      disabled={busyId !== null || renewalKey.length < 8}
                      onClick={() => renewProvider(provider.id)}>
                      {busyId === `renew-${provider.id}` ? <RefreshCw className="llm-spin" size={17} /> : <KeyRound size={17} />}
                      Key prüfen + Discovery
                    </button>
                  </div>
                )}
              </article>
            );
          })}
          {api.providers.length === 0 && !api.loading && (
            <div className="llm-empty">Noch kein Free-Provider eingetragen. Oben genügen Name, API-Basis und gegebenenfalls API-Key; FreeLLM API 0.5.0 kann als interner Docker gewählt werden.</div>
          )}
          {api.loading && api.providers.length === 0 && (
            <div className="llm-empty"><RefreshCw className="llm-spin" /> Free-Revolver-Evidence wird geladen…</div>
          )}
        </div>
      </section>
    </div>
  );
}
