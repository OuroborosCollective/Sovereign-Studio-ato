import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import {
  analyzeSourceDependency,
  executeArenaRoute,
  extractArenaExecution,
  loadArenaLeaderboard,
  loadArenaRequest,
  loadAtlas,
  loadLlmRoutes,
  scoreArenaRun,
  submitCommunityEvidence,
} from './evidenceObservatoryApi';
import {
  evidenceDensity,
  independentOriginCount,
  mapPoint,
  verdictTone,
  type ArenaLeaderboardEntry,
  type EvidenceCase,
  type SourceDependencyAnalysis,
} from './evidenceObservatoryModel';
import './EvidenceObservatoryAtlas.css';

type RouteChoice = { id: string; modelId: string; provider: string; label: string };

function normalizeRoutes(payload: { routes?: Array<Record<string, unknown>>; data?: Array<Record<string, unknown>> }): RouteChoice[] {
  const rows = payload.routes || payload.data || [];
  return rows.map((row) => {
    const id = String(row.id || row.routeId || row.route_id || '');
    const modelId = String(row.defaultModelId || row.modelId || row.model_id || row.model || '');
    const provider = String(row.provider || 'sovereign');
    return { id, modelId, provider, label: `${provider} · ${modelId || id}` };
  }).filter((row) => row.id && row.modelId);
}

function shortHash(value?: string) {
  if (!value) return '—';
  return `${value.slice(0, 10)}…${value.slice(-6)}`;
}

function EvidenceMap({ cases }: { cases: EvidenceCase[] }) {
  const points = cases.flatMap((item) => (item.materialGeoEvidence || []).map((point) => ({ ...point, caseId: item.caseId, verdict: item.verdict })));
  if (!points.length) return null;
  const width = 900;
  const height = 410;
  const verticals = [-120, -60, 0, 60, 120];
  const horizontals = [-60, -30, 0, 30, 60];
  return (
    <section className="eo-panel eo-map-panel" aria-label="Weltkarte materieller Geo-Evidenz">
      <div className="eo-panel-heading">
        <div><span className="eo-kicker">Geo evidence</span><h2>Weltkarte</h2></div>
        <span className="eo-muted">Nur Quellen mit evidenceRole=material erscheinen hier.</span>
      </div>
      <svg className="eo-world-map" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${points.length} materielle geografische Evidence-Punkte`}>
        <rect x="0" y="0" width={width} height={height} rx="20" className="eo-map-ocean" />
        {verticals.map((lon) => {
          const x = mapPoint({ sourceId: '', lat: 0, lon }, width, height).x;
          return <line key={`v-${lon}`} x1={x} x2={x} y1={0} y2={height} className="eo-map-grid" />;
        })}
        {horizontals.map((lat) => {
          const y = mapPoint({ sourceId: '', lat, lon: 0 }, width, height).y;
          return <line key={`h-${lat}`} x1={0} x2={width} y1={y} y2={y} className="eo-map-grid" />;
        })}
        <path className="eo-map-land" d="M79 111l56-43 74 7 46 35-26 38-46 7-28 49-52-15-25-35zm207 10 46-26 79 6 41 26-16 31-66 4-31 26-39-22zm95 100 38-17 43 18 20 59-24 71-36-13-25-72zm104-93 55-35 83-8 67 21 31 31-29 29-68-4-40 27-54-14zm122 91 41-19 67 9 44 40-17 35-58-5-46-29zm134 76 32-9 39 18 8 30-49 18-36-23z" />
        {points.map((point, index) => {
          const { x, y } = mapPoint(point, width, height);
          return (
            <g key={`${point.caseId}-${point.sourceId}-${index}`} transform={`translate(${x} ${y})`}>
              <circle r="12" className={`eo-map-pulse eo-${verdictTone(point.verdict)}`} />
              <circle r="4.5" className="eo-map-pin" />
              <title>{`${point.label || point.sourceId} · ${point.verdict}`}</title>
            </g>
          );
        })}
      </svg>
    </section>
  );
}

function DensityPanel({ cases }: { cases: EvidenceCase[] }) {
  const buckets = evidenceDensity(cases).slice(-32);
  const max = Math.max(1, ...buckets.map((row) => row.sourceCount + row.contradictionCount));
  return (
    <section className="eo-panel">
      <div className="eo-panel-heading">
        <div><span className="eo-kicker">Timeline heatmap</span><h2>Evidence Density</h2></div>
        <span className="eo-muted">Quelle ≠ unabhängiger Ursprung. Die Lineage steht separat.</span>
      </div>
      {!buckets.length ? <p className="eo-empty">Noch keine datierte öffentliche Evidence.</p> : (
        <div className="eo-density" aria-label="Evidence-Density nach Datum">
          {buckets.map((bucket) => (
            <div key={bucket.at} className="eo-density-column" title={`${bucket.at}: ${bucket.sourceCount} Quellen, ${bucket.contradictionCount} Widersprüche`}>
              <div className="eo-density-bar-wrap">
                <div className="eo-density-bar" style={{ height: `${Math.max(8, ((bucket.sourceCount + bucket.contradictionCount) / max) * 100)}%` }} />
                {bucket.contradictionCount > 0 && <div className="eo-density-contradiction" style={{ height: `${Math.max(5, (bucket.contradictionCount / max) * 100)}%` }} />}
              </div>
              <span>{bucket.at.slice(5)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function EvidenceObservatoryAtlas() {
  const [cases, setCases] = useState<EvidenceCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [asOf, setAsOf] = useState('');
  const [projectId, setProjectId] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [pinned, setPinned] = useState<string[]>([]);
  const [submissionState, setSubmissionState] = useState('');
  const [routes, setRoutes] = useState<RouteChoice[]>([]);
  const [routeId, setRouteId] = useState('');
  const [arenaState, setArenaState] = useState('');
  const [leaderboard, setLeaderboard] = useState<ArenaLeaderboardEntry[]>([]);
  const [dependency, setDependency] = useState<SourceDependencyAnalysis | null>(null);
  const [dependencyState, setDependencyState] = useState('');

  const selected = useMemo(() => cases.find((item) => item.caseId === selectedId) || cases[0], [cases, selectedId]);
  const pinnedCases = useMemo(() => cases.filter((item) => pinned.includes(item.caseId)), [cases, pinned]);
  const projects = useMemo(() => [...new Set(cases.map((item) => item.projectId).filter(Boolean) as string[])].sort(), [cases]);

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await loadAtlas({ projectId: projectId || undefined, asOf: asOf ? new Date(asOf).toISOString() : undefined });
      setCases(response.cases || []);
      if (!selectedId && response.cases?.[0]) setSelectedId(response.cases[0].caseId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Atlas konnte nicht geladen werden.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    void loadArenaLeaderboard().then((value) => setLeaderboard(value.entries || [])).catch(() => setLeaderboard([]));
    void loadLlmRoutes().then((value) => {
      const next = normalizeRoutes(value);
      setRoutes(next);
      if (next[0]) setRouteId(next[0].id);
    }).catch(() => setRoutes([]));
  }, []);

  const togglePin = (caseId: string) => {
    setPinned((current) => current.includes(caseId) ? current.filter((id) => id !== caseId) : [...current, caseId]);
  };

  const submitEvidence = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSubmissionState('Wird als privater Evidence-Candidate eingereicht …');
    try {
      const result = await submitCommunityEvidence({
        projectId: String(form.get('projectId') || ''),
        title: String(form.get('title') || ''),
        claim: String(form.get('claim') || ''),
        sourceUrl: String(form.get('sourceUrl') || ''),
        note: String(form.get('note') || ''),
      });
      setSubmissionState(`Candidate ${result.candidate.id.slice(0, 8)}… ist ${result.candidate.workflow_state}. Keine Truth-Promotion.`);
      event.currentTarget.reset();
    } catch (err) {
      setSubmissionState(err instanceof Error ? `Blockiert: ${err.message}` : 'Einreichung blockiert.');
    }
  };

  const testSourceDependency = async (sourceId: string) => {
    if (!selected) return;
    setDependency(null);
    setDependencyState(`Quelle ${sourceId} wird nur als Abhängigkeitssimulation entfernt …`);
    try {
      const result = await analyzeSourceDependency(selected.caseId, sourceId);
      setDependency(result.analysis);
      setDependencyState('Simulation abgeschlossen. Der gespeicherte Verdict wurde nicht verändert.');
    } catch (err) {
      setDependencyState(err instanceof Error ? `Simulation blockiert: ${err.message}` : 'Simulation blockiert.');
    }
  };

  const runArena = async () => {
    if (!selected || !routeId) return;
    const route = routes.find((item) => item.id === routeId);
    if (!route) return;
    setArenaState(`Evidence-Run über ${route.label} läuft …`);
    try {
      const contract = await loadArenaRequest(selected.caseId);
      const execution = await executeArenaRoute({ routeId: route.id, modelId: route.modelId, messages: contract.messages });
      const evidence = extractArenaExecution(execution);
      const scored = await scoreArenaRun({
        caseId: selected.caseId,
        routeId: route.id,
        modelId: route.modelId,
        modelResponse: evidence.modelResponse,
        llmRequestId: evidence.llmRequestId,
      });
      setArenaState(`Run ${scored.runId.slice(0, 8)}… verifiziert · Score ${String(scored.metrics.overallScore ?? '—')} · ${shortHash(scored.runSha256)}`);
      const board = await loadArenaLeaderboard();
      setLeaderboard(board.entries || []);
    } catch (err) {
      setArenaState(err instanceof Error ? `Arena blockiert: ${err.message}` : 'Arena blockiert.');
    }
  };

  return (
    <main className="eo-shell" data-testid="evidence-observatory-atlas">
      <header className="eo-hero">
        <div>
          <span className="eo-kicker">Sovereign Evidence Observatory</span>
          <h1>Evidence Time Machine</h1>
          <p>Behauptung → Ursprung → Timeline → Widerspruch → Proof Route → reproduzierbarer Evidenzzustand.</p>
        </div>
        <a className="eo-chat-link" href="/">Sovereign Chat</a>
      </header>

      <section className="eo-toolbar" aria-label="Atlas Filter">
        <label>Projekt<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Alle öffentlichen Projekte</option>{projects.map((project) => <option key={project} value={project}>{project}</option>)}</select></label>
        <label>Evidence verfügbar bis<input type="datetime-local" value={asOf} onChange={(event) => setAsOf(event.target.value)} /></label>
        <button type="button" onClick={() => void refresh()}>Zeitpunkt anwenden</button>
        <span className="eo-truth-boundary">Engagement ≠ Wahrheit · UNPROVEN ist zulässig</span>
      </section>

      {error && <div className="eo-error">{error}</div>}
      {loading ? <div className="eo-loading">Evidence wird aus dem öffentlichen Gate-Readback geladen …</div> : (
        <>
          <section className="eo-stat-grid">
            <div><strong>{cases.length}</strong><span>sichtbare Cases</span></div>
            <div><strong>{cases.reduce((total, item) => total + item.sources.length, 0)}</strong><span>Quelleneinträge</span></div>
            <div><strong>{cases.reduce((total, item) => total + independentOriginCount(item), 0)}</strong><span>Origin-Familien</span></div>
            <div><strong>{cases.reduce((total, item) => total + (item.evidenceNeeded?.length || 0), 0)}</strong><span>offene Evidence-Bedarfe</span></div>
          </section>

          <DensityPanel cases={cases} />
          <EvidenceMap cases={cases} />

          <div className="eo-workbench">
            <section className="eo-panel eo-case-list">
              <div className="eo-panel-heading"><div><span className="eo-kicker">Cases</span><h2>Beweisketten</h2></div><span className="eo-muted">{cases.length} sichtbar</span></div>
              {!cases.length && <p className="eo-empty">Noch keine Case-Evidence hat alle Publish-Gates bestanden.</p>}
              {cases.map((item) => (
                <button type="button" className={`eo-case-row ${selected?.caseId === item.caseId ? 'is-selected' : ''}`} key={item.caseId} onClick={() => setSelectedId(item.caseId)}>
                  <span className={`eo-verdict eo-${verdictTone(item.verdict)}`}>{item.verdict}</span>
                  <span className="eo-case-copy"><strong>{item.title || item.claim}</strong><small>{item.projectId || 'Evidence'} · {independentOriginCount(item)} unabhängige Origin-Familien</small></span>
                  <span onClick={(event) => { event.stopPropagation(); togglePin(item.caseId); }} className={`eo-pin ${pinned.includes(item.caseId) ? 'is-pinned' : ''}`} role="button" tabIndex={0}>⌖</span>
                </button>
              ))}
            </section>

            <section className="eo-panel eo-case-detail">
              {!selected ? <p className="eo-empty">Case auswählen.</p> : <>
                <div className="eo-panel-heading"><div><span className="eo-kicker">Selected evidence chain</span><h2>{selected.title || selected.claim}</h2></div><span className={`eo-verdict eo-${verdictTone(selected.verdict)}`}>{selected.verdict}</span></div>
                <blockquote>{selected.claim}</blockquote>
                <div className="eo-hash-grid"><span>Claim <code>{shortHash(selected.claimSha256)}</code></span><span>Case <code>{shortHash(selected.caseSha256)}</code></span><span>Passport <code>{shortHash(selected.passportSha256)}</code></span></div>
                <h3>Timeline</h3>
                <div className="eo-timeline">
                  {(selected.timeline || []).map((event, index) => <article key={event.id || `${event.at}-${index}`}><time>{new Date(event.at).toLocaleString()}</time><strong>{event.title || 'Evidence event'}</strong><p>{event.summary}</p><small>Sources: {(event.sourceIds || []).join(', ') || '—'}</small></article>)}
                  {!selected.timeline?.length && <p className="eo-empty">Noch keine publizierbaren Timeline-Ereignisse.</p>}
                </div>
                <h3>Source Lineage</h3>
                <div className="eo-lineage">{Object.entries(selected.sourceLineage || {}).map(([origin, sourceIds]) => <div key={origin}><strong>{origin}</strong><span>{sourceIds.length} Eintrag/Einträge</span><small>{sourceIds.join(' · ')}</small></div>)}</div>
                <h3>Quellen-Robustheit</h3>
                <div className="eo-source-dependency-list">
                  {(selected.sources || []).map((source) => <article key={source.id}>
                    <div><strong>{source.label || source.id}</strong><small>{source.sourceType || 'source'} · {source.provenance?.originFamily || 'origin unknown'} · {shortHash(source.contentSha256)}</small></div>
                    <button type="button" onClick={() => void testSourceDependency(source.id)}>Testweise entfernen</button>
                  </article>)}
                </div>
                {dependencyState && <p className="eo-status-line">{dependencyState}</p>}
                {dependency && <div className="eo-dependency-result">
                  <strong>Dependency simulation · {shortHash(dependency.analysisSha256)}</strong>
                  <span>Verdict-Basisquelle entfernt: {dependency.verdictBasisSourceRemoved ? 'JA' : 'nein'}</span>
                  <span>Receipt-Abhängigkeit gebrochen: {dependency.verdictBasisReceiptDependencyBroken ? 'JA' : 'nein'}</span>
                  <span>Verbleibende unabhängige Ursprünge: {dependency.remainingIndependentOriginCount}</span>
                  <span>Betroffene Timeline-Ereignisse: {dependency.timelineEventsAffected}</span>
                  <small>{dependency.truthNotice}</small>
                </div>}
                {!!selected.claimGenealogy?.length && <><h3>Claim Genealogy · Information DNA</h3><div className="eo-genealogy">{selected.claimGenealogy.map((edge, index) => <article key={edge.id || `${edge.fromSourceId}-${edge.toSourceId}-${index}`}><strong>{edge.fromSourceId || 'origin'} → {edge.toSourceId || 'derived'}</strong><p>{edge.mutation || 'Transformation ist dokumentiert, aber nicht als Schlussfolgerung interpretiert.'}</p></article>)}</div></>}
                {!!selected.informationFlow?.length && <><h3>Informationsfluss</h3><div className="eo-flow">{selected.informationFlow.map((edge, index) => <span key={edge.id || `${edge.fromSourceId}-${edge.toSourceId}-${index}`}>{edge.fromSourceId || '?'} → {edge.toSourceId || '?'} · {edge.relation || 'derived'}</span>)}</div></>}
                {!!selected.evidenceNeeded?.length && <div className="eo-needed"><strong>Was würde den Evidenzzustand ändern?</strong><ul>{selected.evidenceNeeded.map((item) => <li key={item}>{item}</li>)}</ul></div>}
              </>}
            </section>
          </div>

          {!!pinnedCases.length && <section className="eo-panel"><div className="eo-panel-heading"><div><span className="eo-kicker">Pinboard</span><h2>Angeheftete Informationen</h2></div></div><div className="eo-pinboard">{pinnedCases.map((item) => <article key={item.caseId}><span className={`eo-verdict eo-${verdictTone(item.verdict)}`}>{item.verdict}</span><strong>{item.title || item.claim}</strong><p>{item.claim}</p><button type="button" onClick={() => togglePin(item.caseId)}>Lösen</button></article>)}</div></section>}

          <section className="eo-panel eo-community">
            <div className="eo-panel-heading"><div><span className="eo-kicker">Community evidence intake</span><h2>Hinweis einreichen</h2></div><span className="eo-muted">Jeder Eingang bleibt zunächst privat + QUARANTINED.</span></div>
            <form onSubmit={submitEvidence}>
              <input name="projectId" placeholder="Projekt / Universe" />
              <input name="title" placeholder="Kurztitel" />
              <textarea name="claim" required placeholder="Welche konkrete Behauptung soll dieser Hinweis prüfen?" />
              <input name="sourceUrl" required type="url" pattern="https://.*" placeholder="https://… Primär- oder Ausgangsquelle" />
              <textarea name="note" placeholder="Warum ist dieser Hinweis relevant? Keine Schlussfolgerung erzwingen." />
              <button type="submit">Als Evidence-Candidate einreichen</button>
            </form>
            {submissionState && <p className="eo-status-line">{submissionState}</p>}
          </section>

          <section className="eo-panel eo-arena">
            <div className="eo-panel-heading"><div><span className="eo-kicker">Evidence Arena</span><h2>Modelle auf Belegdisziplin prüfen</h2></div><span className="eo-muted">Kein „truthful model“-Ranking. Nur versionierte Evidence-Metriken.</span></div>
            <div className="eo-arena-controls">
              <select value={routeId} onChange={(event) => setRouteId(event.target.value)} disabled={!routes.length}>{!routes.length && <option>Keine authentifizierte Sovereign-Route verfügbar</option>}{routes.map((route) => <option key={route.id} value={route.id}>{route.label}</option>)}</select>
              <button type="button" disabled={!selected || !routeId} onClick={() => void runArena()}>Ausgewählten Case prüfen</button>
            </div>
            {arenaState && <p className="eo-status-line">{arenaState}</p>}
            <div className="eo-leaderboard">{leaderboard.map((entry, index) => <article key={`${entry.provider}-${entry.modelId}`}><span>#{index + 1}</span><strong>{entry.modelId}</strong><small>{entry.provider} · {entry.runs} Runs</small><b>{Number(entry.overallScore).toFixed(3)}</b><small>Evidence {Number(entry.evidenceAdherence).toFixed(3)} · Unsupported {Number(entry.unsupportedClaimRate).toFixed(3)}</small></article>)}</div>
          </section>
        </>
      )}
    </main>
  );
}
