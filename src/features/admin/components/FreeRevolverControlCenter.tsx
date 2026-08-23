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
import { FreellmProviderSelectionRequiredError } from '../api/adminApiClient';
import type {
  FreeRevolverProviderAuthMode,
  FreeRevolverProviderModel,
  FreellmProviderChoice,
} from '../api/adminApiClient';
import type { UseAdminFreeRevolverProvidersResult } from '../hooks/useAdminApi';

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

function isEligibilityEvidenceFresh(verifiedAt: string | null, ttlHours: number): boolean {
  if (!verifiedAt) return false;
  const verified = new Date(verifiedAt);
  return !Number.isNaN(verified.getTime())
    && verified.getTime() + ttlHours * 60 * 60 * 1000 > Date.now();
}

function eligibilityEvidenceExpiry(verifiedAt: string | null, ttlHours: number): string {
  if (!verifiedAt) return 'Eligibility-Evidence fehlt';
  const verified = new Date(verifiedAt);
  if (Number.isNaN(verified.getTime())) return 'Eligibility-Evidence-Datum ungültig';
  const expires = new Date(verified.getTime() + ttlHours * 60 * 60 * 1000);
  const formatted = new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(expires);
  return expires.getTime() > Date.now()
    ? `Eligibility-Evidence gültig bis ${formatted}`
    : `Eligibility-Evidence abgelaufen seit ${formatted}`;
}

function hasRevisionBoundReceipt(model: FreeRevolverProviderModel): boolean {
  return model.runtimeIdentity.sourceRevisionVerified === true
    && model.runtimeIdentity.imageDigestVerified === true
    && model.canaryReceipt.schemaVersion === 'sovereign.freellm-route-receipt.v3'
    && model.canaryReceipt.generalChatEvidenceVerified === true
    && typeof model.canaryReceipt.receiptSha256 === 'string'
    && /^[0-9a-f]{64}$/.test(model.canaryReceipt.receiptSha256);
}

export function FreeRevolverControlCenter({
  api,
  eligibilityEvidenceTtlHours,
}: {
  api: UseAdminFreeRevolverProvidersResult;
  eligibilityEvidenceTtlHours: number;
}) {
  const [apiKey, setApiKey] = useState('');
  const [providerChoices, setProviderChoices] = useState<FreellmProviderChoice[]>([]);
  const [selectedProviderId, setSelectedProviderId] = useState('');
  const [renewalKeys, setRenewalKeys] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const genericProviders = useMemo(
    () => api.providers.filter(provider => (
      provider.lifecycle === 'active'
      && provider.canonicalAction === 'revolver-discover'
    )),
    [api.providers],
  );
  const retiredProviders = useMemo(
    () => api.providers.filter(provider => provider.lifecycle === 'historical'),
    [api.providers],
  );

  const totals = useMemo(() => {
    const models = genericProviders.flatMap(provider => provider.models);
    return {
      providers: genericProviders.length + (api.omniRoute ? 1 : 0),
      ready: models.filter(model => (
        model.status === 'ready'
        && model.enabled
        && hasRevisionBoundReceipt(model)
        && isEligibilityEvidenceFresh(model.eligibilityVerifiedAt, eligibilityEvidenceTtlHours)
      )).length,
      deferred: models.filter(model => model.status === 'discovered').length,
      blocked: models.filter(model => model.status === 'blocked').length,
      verified: models.filter(model => (
        model.freeEligible
        && isEligibilityEvidenceFresh(model.eligibilityVerifiedAt, eligibilityEvidenceTtlHours)
      )).length,
    };
  }, [api.omniRoute, genericProviders, eligibilityEvidenceTtlHours]);

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

  const submitAutoProviderKey = () => {
    const protectedValue = apiKey;
    const explicitProviderId = selectedProviderId || undefined;
    setBusyId('auto-provider');
    setActionError(null);
    setNotice(null);
    void api.autoConfigureKey(protectedValue, explicitProviderId)
      .then(result => {
        setApiKey('');
        setProviderChoices([]);
        setSelectedProviderId('');
        setNotice(`${result.label} erkannt und sicher gespeichert · ${result.keyCount} Key${result.keyCount === 1 ? '' : 's'} im Provider-Pool. FreeLLM übernimmt den Pool automatisch.`);
      })
      .catch(error => {
        if (error instanceof FreellmProviderSelectionRequiredError) {
          setProviderChoices(error.providers);
          setSelectedProviderId(error.providers[0]?.providerId ?? '');
          setActionError('Der Key hat keine eindeutige Signatur. Bitte den Provider einmalig auswählen und erneut speichern.');
          return;
        }
        setActionError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => setBusyId(null));
  };

  const renewProvider = (sourceId: string) => {
    const protectedValue = renewalKeys[sourceId] ?? '';
    setRenewalKeys(current => ({ ...current, [sourceId]: '' }));
    void run(`renew-${sourceId}`, async () => {
      await api.renewAndDiscover(sourceId, protectedValue);
    }, 'Key erneuert, Free-Quota-Katalog neu erkannt und echte Completion-Canaries ausgeführt.');
  };

  return (
    <div className="free-revolver-admin">
      <section className="llm-control-center__hero free-revolver-admin__hero">
        <div>
          <span className="llm-kicker">Free Revolver / Quoten-Routen</span>
          <h1>Kostenfreie Provider sicher verbinden</h1>
          <p>
            Der Key wird einmalig über den geschützten Owner-Kanal übertragen und nie in der
            Sovereign-Datenbank gespeichert. Aktiviert werden ausschließlich Modelle mit
            bestätigtem Free-Quota-Vertrag und zwei echten direkten FreeLLM-Completion-Canaries.
            Ein ausdrücklich positiver Kostenwert blockiert weiterhin hart. Fehlende oder abgekühlte Upstreams bleiben
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
        <div><Search /><span>Free-Quota bestätigt</span><strong>{totals.verified}</strong></div>
        <div><RefreshCw /><span>Wartet auf Upstream</span><strong>{totals.deferred}</strong></div>
        <div><Lock /><span>Hart blockiert</span><strong>{totals.blocked}</strong></div>
      </div>

      <section className="llm-catalog free-revolver-admin__onboarding">
        <div className="llm-section-title">
          <div><KeyRound size={21} /><div>
            <h2>API-Key eintragen</h2>
            <p>Key einfügen – Provider, sichere Ablage und FreeLLM-Zuordnung erledigt das Backend automatisch.</p>
          </div></div>
        </div>
        <div className="free-revolver-form">
          <label>
            <span>API-Key</span>
            <input type="password" autoComplete="new-password" spellCheck={false}
              value={apiKey} disabled={busyId !== null}
              placeholder="API-Key einfügen"
              onChange={event => {
                setApiKey(event.target.value);
                if (providerChoices.length > 0) {
                  setProviderChoices([]);
                  setSelectedProviderId('');
                }
              }} />
          </label>
          {providerChoices.length > 0 && (
            <label>
              <span>Provider auswählen</span>
              <select value={selectedProviderId} disabled={busyId !== null}
                onChange={event => setSelectedProviderId(event.target.value)}>
                {providerChoices.map(provider => (
                  <option key={provider.providerId} value={provider.providerId}>{provider.label}</option>
                ))}
              </select>
            </label>
          )}
          <button type="button" className="llm-button llm-button--primary"
            disabled={busyId !== null || apiKey.length < 8 || (providerChoices.length > 0 && !selectedProviderId)}
            onClick={submitAutoProviderKey}>
            {busyId === 'auto-provider' ? <RefreshCw className="llm-spin" size={18} /> : <Search size={18} />}
            {providerChoices.length > 0 ? 'Ausgewählten Provider speichern' : 'Provider erkennen + speichern'}
          </button>
        </div>
        <p className="llm-catalog__evidence">
          Der Roh-Key wird nicht in PostgreSQL gespeichert. Eindeutige Signaturen werden automatisch erkannt; unbekannte Schlüssel bleiben bis zur expliziten Provider-Auswahl fail-closed.
        </p>
      </section>

      {(api.error || actionError) && (
        <div className="llm-alert llm-alert--danger">{actionError ?? api.error}</div>
      )}
      {notice && <div className="llm-alert free-revolver-admin__notice">{notice}</div>}

      {api.openRouterFree && (
        <section className="llm-catalog" data-testid="provider-surface-openrouter-free">
          <div className="llm-section-title">
            <div><ShieldCheck size={21} /><div>
              <h2>OpenRouter Free</h2>
              <p>Eigenständiger Free-Pfad mit accountweiter Quota und ohne Paid-Fallback.</p>
            </div></div>
          </div>
          <div className="free-revolver-provider__facts">
            <div><span>Provider-Modell</span><strong>{api.openRouterFree.routingPolicy.providerModel}</strong></div>
            <div><span>Fallback nach Quota</span><strong>{api.openRouterFree.routingPolicy.fallbackAfterQuota}</strong></div>
            <div><span>Paid-Fallback</span><strong>{api.openRouterFree.routingPolicy.paidFallbackAllowed ? 'erlaubt' : 'gesperrt'}</strong></div>
            <div><span>Management-Evidence</span><strong>{api.openRouterFree.managementTableAvailable ? 'verfügbar' : api.openRouterFree.managementTableBlocker ?? 'nicht verfügbar'}</strong></div>
          </div>
        </section>
      )}

      {api.omniRoute && (
        <section
          className="llm-catalog"
          data-testid="provider-surface-omniroute"
          aria-label="OmniRoute Auto Runtime"
        >
          <div className="llm-section-title">
            <div><Server size={21} /><div>
              <h2>OmniRoute Auto</h2>
              <p>Eigene keyless Laufzeit: nur der kanonische Doppel-Canary darf die Auto-Route ändern.</p>
            </div></div>
          </div>
          <div className="free-revolver-provider__facts">
            <div><span>Aktivierung</span><strong>{api.omniRoute.activationState}</strong></div>
            <div><span>Bestätigungen</span><strong>{api.omniRoute.confirmationCount}/2</strong></div>
            <div><span>Route</span><strong>{api.omniRoute.modelId}</strong></div>
            <div><span>Blocker</span><strong>{api.omniRoute.blocker ?? '—'}</strong></div>
          </div>
          <p className="llm-catalog__evidence">
            Die Kataloggröße ist kein Bereitstellungsversprechen einzelner Modelle: produktiv ist ausschließlich
            <code> auto </code> auswählbar, und nur nach zwei erfolgreichen Completion-Canaries.
          </p>
          <div className="llm-route-card__actions">
            <button
              type="button"
              className="llm-button llm-button--primary"
              data-testid="provider-action-omniroute-refresh"
              disabled={busyId !== null}
              onClick={() => void run(
                'omniroute-refresh',
                () => api.refreshOmniRoute(),
                'OmniRoute-Doppel-Canary wurde angefordert; die Ansicht übernimmt ausschließlich den Runtime-Readback.',
              )}
            >
              <RefreshCw className={busyId === 'omniroute-refresh' ? 'llm-spin' : ''} size={17} />
              OmniRoute-Doppel-Canary ausführen
            </button>
          </div>
        </section>
      )}

      <section>
        <div className="llm-section-title">
          <div><Server size={21} /><div>
            <h2>Free-Provider und Runtime-Evidence</h2>
            <p>{genericProviders.length} ausführbare Free-Revolver-Quellen · {retiredProviders.length} historische Referenz{retiredProviders.length === 1 ? '' : 'en'}</p>
          </div></div>
        </div>
        <div className="free-revolver-provider-grid">
          {genericProviders.map(provider => {
            const readyModels = provider.models.filter(model => (
              model.status === 'ready'
              && model.enabled
              && hasRevisionBoundReceipt(model)
              && isEligibilityEvidenceFresh(model.eligibilityVerifiedAt, eligibilityEvidenceTtlHours)
            ));
            const deferredModels = provider.models.filter(model => model.status === 'discovered');
            const blockedModels = provider.models.filter(model => model.status === 'blocked');
            const recheckableModels = provider.models.filter(model => (
              model.freeEligible
              || model.eligibilitySource === 'managed-freellm-chat-canary-required'
            ));
            const renewalKey = renewalKeys[provider.id] ?? '';
            return (
              <article
                key={provider.id}
                data-testid={provider.sourceType === 'freellmapi-direct'
                  ? 'provider-surface-freellm-api'
                  : 'provider-surface-free-revolver'}
                className={`llm-route-card free-revolver-provider free-revolver-provider--${provider.status}`}
              >
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
                  <div><span>Letzte Quota-Discovery</span><strong>{provider.lastDiscoveredAt ?? 'noch keine'}</strong></div>
                  <div><span>Letzter Completion-Check</span><strong>{provider.lastCheckedAt ?? 'noch keiner'}</strong></div>
                  <div><span>HTTP / Blocker</span><strong>{provider.lastHttpStatus ?? '—'}{provider.lastErrorCode ? ` · ${provider.lastErrorCode}` : ''}</strong></div>
                </div>

                <div className="free-revolver-model-list">
                  {provider.models.map(model => {
                    const eligibilityFresh = isEligibilityEvidenceFresh(
                      model.eligibilityVerifiedAt,
                      eligibilityEvidenceTtlHours,
                    );
                    const receiptVerified = hasRevisionBoundReceipt(model);
                    const missingFromCatalog = model.lastErrorCode === 'model_missing_from_provider_catalog';
                    const effectiveReady = model.status === 'ready'
                      && model.enabled
                      && eligibilityFresh
                      && receiptVerified;
                    return (
                    <div key={model.id} className="free-revolver-model">
                      <div>
                        <strong>{model.displayName || model.modelId}</strong>
                        <span>{model.modelId}</span>
                        <span>
                          {missingFromCatalog
                            ? 'Nicht mehr im aktuellen Provider-Katalog'
                            : eligibilityEvidenceExpiry(model.eligibilityVerifiedAt, eligibilityEvidenceTtlHours)}
                        </span>
                        <span>
                          {missingFromCatalog
                            ? 'Kein aktuelles Modell – kein neues Receipt erwartet'
                            : model.canaryReceipt.receiptSha256
                            ? `Receipt ${model.canaryReceipt.receiptSha256.slice(0, 16)}…`
                            : 'Revision-Receipt fehlt'}
                        </span>
                      </div>
                      <span className={`llm-badge llm-badge--${effectiveReady ? 'ok' : model.status === 'discovered' ? 'warn' : 'danger'}`}>
                        {missingFromCatalog
                          ? 'nicht mehr im Provider-Katalog'
                          : model.generalChatBlockVerified
                          ? model.generalChatBlocker ?? model.eligibilitySource
                          : !eligibilityFresh
                            ? 'Eligibility-Evidence abgelaufen'
                            : !receiptVerified
                              ? 'Revision, Image-Digest oder v3-Chat-Canary-Receipt fehlt'
                              : model.status === 'discovered'
                            ? `wartet auf verfügbaren Upstream · ${model.lastErrorCode ?? 'noch nicht erfolgreich geprüft'}`
                            : model.status !== 'ready'
                              ? model.lastErrorCode ?? model.eligibilitySource
                              : model.providerCostState === 'zero'
                              ? 'Free-Quota + Canary meldet Kosten 0'
                              : 'Free-Quota + Canary ohne Kostenangabe'}
                      </span>
                    </div>
                    );
                  })}
                  {provider.models.length === 0 && (
                    <p className="llm-route-card__evidence">Noch keine Modell-Evidence. Key eintragen und Discovery starten.</p>
                  )}
                </div>

                <footer className="llm-route-card__actions">
                  {provider.canonicalAction === 'revolver-discover' && (
                    <button type="button" className="llm-button llm-button--primary"
                      disabled={busyId !== null || !provider.enabled}
                      onClick={() => void run(
                        `discover-${provider.id}`,
                        () => api.discover(provider.id),
                        'Discovery abgeschlossen. Erfolgreich doppelt gecanaryte Modelle wurden aktiviert; temporär nicht erreichbare Upstreams bleiben sichtbar und erneut prüfbar, echte Policy-Verstöße bleiben blockiert.',
                      )}>
                      <Search size={17} /> Modelle + Quoten neu erkennen
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
                      Noch kein Modell ist healthcheckfähig. Zuerst Modelle und Quoten neu erkennen.
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
          {genericProviders.length === 0 && !api.omniRoute && !api.loading && (
            <div className="llm-empty">Noch keine ausführbare Free-Revolver-Quelle verfügbar. Provider und sichere Zuordnung übernimmt das Backend.</div>
          )}
          {api.loading && genericProviders.length === 0 && !api.omniRoute && (
            <div className="llm-empty"><RefreshCw className="llm-spin" /> Free-Revolver-Evidence wird geladen…</div>
          )}
        </div>
      </section>

      {retiredProviders.length > 0 && (
        <section className="llm-catalog" aria-label="Historische Provider-Referenzen">
          <div className="llm-section-title">
            <div><Lock size={21} /><div>
              <h2>Historische Referenzen</h2>
              <p>Diese Einträge bleiben nur als Migrations- und Audit-Evidence sichtbar; sie sind nicht ausführbar.</p>
            </div></div>
          </div>
          <div className="free-revolver-provider-grid">
            {retiredProviders.map(provider => (
              <article
                key={provider.id}
                className="llm-route-card free-revolver-provider free-revolver-provider--disabled"
                data-testid={provider.lastErrorCode === 'freellmpool_replaced_by_omniroute'
                  ? 'provider-surface-retired-freellmpool'
                  : 'provider-surface-retired-reference'}
              >
                <header className="llm-route-card__header">
                  <div className="llm-route-card__identity">
                    <span className="llm-route-card__status llm-route-card__status--off" />
                    <div>
                      <h3>{provider.label}</h3>
                      <p>{provider.apiBase}</p>
                    </div>
                  </div>
                </header>
                <div className="llm-route-card__badges">
                  <span className="llm-badge llm-badge--warn"><Lock size={14} /> Historische Referenz</span>
                  <span className="llm-badge">{provider.lastErrorCode ?? 'nicht ausführbar'}</span>
                </div>
                <p className="llm-route-card__evidence">
                  Durch OmniRoute ersetzt. Keine Discovery, kein Healthcheck und keine Aktivierung sind über diese Referenz zulässig.
                </p>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
