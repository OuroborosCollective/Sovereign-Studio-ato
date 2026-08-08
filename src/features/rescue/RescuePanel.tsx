import React, { useEffect, useMemo, useRef, useState } from 'react';
import { PaywallModal } from '../billing/PaywallModal';
import {
  createSovereignRescueClient,
  type RescueCapsuleDownload,
  type RescueDiagnosis,
  type RescueEntitlement,
  type RescueFailureFamily,
  type RescueProofPack,
  type RescueRepair,
} from './rescueClient';

const FAMILY_OPTIONS: Array<{ value: '' | RescueFailureFamily; label: string }> = [
  { value: '', label: 'Automatisch erkennen' },
  { value: 'github_actions_ci', label: 'GitHub Actions / CI' },
  { value: 'docker_compose_container', label: 'Docker Compose / Container' },
  { value: 'postgresql_migration_schema', label: 'PostgreSQL Migration / Schema' },
];

const panel: React.CSSProperties = {
  position: 'fixed',
  inset: 12,
  zIndex: 90,
  maxWidth: 760,
  margin: '0 auto',
  overflowY: 'auto',
  borderRadius: 18,
  border: '1px solid #334155',
  background: '#0f172a',
  color: '#e2e8f0',
  boxShadow: '0 24px 80px rgba(0,0,0,.55)',
  padding: 18,
};

const input: React.CSSProperties = {
  width: '100%',
  minHeight: 44,
  borderRadius: 10,
  border: '1px solid #475569',
  background: '#111827',
  color: '#f8fafc',
  padding: '10px 12px',
  boxSizing: 'border-box',
};

const button: React.CSSProperties = {
  minHeight: 44,
  borderRadius: 10,
  border: '1px solid #38bdf8',
  background: '#0c4a6e',
  color: '#f0f9ff',
  padding: '9px 14px',
  fontWeight: 700,
  cursor: 'pointer',
};

export interface RescuePanelProps {
  readonly open: boolean;
  readonly apiBaseUrl: string;
  readonly currentJobId?: string;
  readonly draftPrUrl?: string;
  readonly onClose: () => void;
  readonly onJobReady: (jobId: string) => void | Promise<void>;
  readonly onPublishDraftPr: () => void | Promise<void>;
  readonly onCapsuleReady?: (download: RescueCapsuleDownload) => void | Promise<void>;
}

export function RescuePanel({
  open,
  apiBaseUrl,
  currentJobId,
  draftPrUrl,
  onClose,
  onJobReady,
  onPublishDraftPr,
  onCapsuleReady,
}: RescuePanelProps) {
  const client = useMemo(() => createSovereignRescueClient(apiBaseUrl), [apiBaseUrl]);
  const [repository, setRepository] = useState('');
  const [branch, setBranch] = useState('main');
  const [evidence, setEvidence] = useState('');
  const [family, setFamily] = useState<'' | RescueFailureFamily>('');
  const [diagnosis, setDiagnosis] = useState<RescueDiagnosis>();
  const [entitlement, setEntitlement] = useState<RescueEntitlement>();
  const [repair, setRepair] = useState<RescueRepair>();
  const [proofPack, setProofPack] = useState<RescueProofPack>();
  const [capsule, setCapsule] = useState<RescueCapsuleDownload>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [showPaywall, setShowPaywall] = useState(false);
  const idempotency = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!open) return;
    void client.entitlement().then(setEntitlement).catch(() => setEntitlement(undefined));
  }, [client, open]);

  if (!open) return null;

  const request = {
    repository: repository.trim(),
    baseBranch: branch.trim() || 'main',
    evidenceText: evidence,
    ...(family ? { failureFamily: family } : {}),
  };

  const diagnose = async () => {
    idempotency.current = undefined;
    setBusy(true);
    setMessage('Revision und Fehlerfamilie werden geprüft …');
    setRepair(undefined);
    setProofPack(undefined);
    setCapsule(undefined);
    try {
      const result = await client.diagnose(request);
      setDiagnosis(result);
      setMessage('Kostenlose Diagnose abgeschlossen. Das Repository wurde nicht verändert.');
    } catch (error) {
      setDiagnosis(undefined);
      setMessage(error instanceof Error ? error.message : 'Diagnose fehlgeschlagen.');
    } finally {
      setBusy(false);
    }
  };

  const startRepair = async () => {
    if (!diagnosis) return;
    setBusy(true);
    setCapsule(undefined);
    setMessage('Repair Pack wird serverseitig autorisiert und gestartet …');
    const key = idempotency.current || crypto.randomUUID();
    idempotency.current = key;
    try {
      const result = await client.repair({
        ...request,
        failureFamily: diagnosis.failureFamily,
        expectedBaseSha: diagnosis.baseSha,
      }, key);
      setRepair(result);
      await onJobReady(result.jobId);
      setMessage('Repair Pack läuft im isolierten Workspace. Änderungen bleiben bis zum Draft PR getrennt.');
      setEntitlement(await client.entitlement());
    } catch (error) {
      const status = (error as Error & { status?: number }).status;
      setMessage(status === 402
        ? 'Für den Repair Pack ist ein serverseitig bestätigter Kauf erforderlich.'
        : error instanceof Error ? error.message : 'Repair Pack konnte nicht starten.');
    } finally {
      setBusy(false);
    }
  };

  const publishDraftPr = async () => {
    setBusy(true);
    setMessage('Draft-PR-Anfrage wird revisionsgebunden übergeben …');
    try {
      await onPublishDraftPr();
      setMessage('Draft-PR-Anfrage übergeben. GitHub-Readback und CI-Evidence entscheiden den Status.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Draft-PR-Anfrage konnte nicht übergeben werden.');
    } finally {
      setBusy(false);
    }
  };

  const downloadCapsule = async () => {
    if (!repair) return;
    setBusy(true);
    setMessage('Zero-Trust Capsule wird aus aktuellem Workspace-Evidence erzeugt …');
    try {
      const download = await client.capsule(repair.repairId);
      if (onCapsuleReady) {
        await onCapsuleReady(download);
      } else {
        const objectUrl = URL.createObjectURL(download.archive);
        try {
          const anchor = document.createElement('a');
          anchor.href = objectUrl;
          anchor.download = download.filename;
          anchor.rel = 'noopener';
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
        } finally {
          URL.revokeObjectURL(objectUrl);
        }
      }
      setCapsule(download);
      setMessage(
        'Capsule heruntergeladen. Der Patch wurde weder angewendet noch an GitHub übertragen.',
      );
    } catch (error) {
      const payload = (error as Error & { payload?: Record<string, unknown> }).payload;
      const blocker = typeof payload?.blocker === 'string' ? payload.blocker : undefined;
      setMessage(blocker || (error instanceof Error ? error.message : 'Capsule konnte nicht erzeugt werden.'));
    } finally {
      setBusy(false);
    }
  };

  const loadProofPack = async () => {
    if (!repair) return;
    setBusy(true);
    setMessage('Draft-PR-Head und CI werden revisionsgenau geprüft …');
    try {
      const pack = await client.proofPack(repair.repairId);
      setProofPack(pack);
      setMessage(pack.ready ? 'ProofPack vollständig und verifiziert.' : 'ProofPack enthält noch offene Evidence.');
    } catch (error) {
      const payload = (error as Error & { payload?: Record<string, unknown> }).payload;
      const pack = payload?.proofPack as RescueProofPack | undefined;
      if (pack) setProofPack(pack);
      setMessage(error instanceof Error ? error.message : 'ProofPack konnte nicht geprüft werden.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section role="dialog" aria-modal="true" aria-labelledby="rescue-title" style={panel}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'start' }}>
        <div>
          <h1 id="rescue-title" style={{ margin: 0, fontSize: 22 }}>Sovereign Rescue</h1>
          <p style={{ margin: '6px 0 18px', color: '#94a3b8' }}>
            Deine App ist kaputt. Sovereign findet die Ursache, repariert sie sicher und beweist,
            dass sie wieder funktioniert.
          </p>
        </div>
        <button type="button" onClick={onClose} aria-label="Rescue schließen" style={button}>×</button>
      </div>

      <ol style={{ paddingLeft: 22, lineHeight: 1.5 }}>
        <li>Repository und exakte Revision verbinden</li>
        <li>Kostenlose Diagnose ohne Repository-Änderung</li>
        <li>Begrenzten Repair Pack autorisieren</li>
        <li>Draft PR oder Zero-Trust Capsule ausdrücklich wählen und Evidence prüfen</li>
      </ol>

      <div style={{ display: 'grid', gap: 10 }}>
        <label>
          GitHub-Repository
          <input
            style={input}
            value={repository}
            onChange={(event) => setRepository(event.target.value)}
            placeholder="https://github.com/owner/repository"
            autoComplete="url"
          />
        </label>
        <label>
          Basis-Branch
          <input style={input} value={branch} onChange={(event) => setBranch(event.target.value)} />
        </label>
        <label>
          Fehlerfamilie
          <select style={input} value={family} onChange={(event) => setFamily(event.target.value as '' | RescueFailureFamily)}>
            {FAMILY_OPTIONS.map((option) => <option key={option.value || 'auto'} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label>
          Fehlerausgabe oder Logs
          <textarea
            style={{ ...input, minHeight: 130, resize: 'vertical' }}
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            placeholder="Fehlerausgabe hier einfügen. Secret-ähnliche Werte werden serverseitig redigiert."
          />
        </label>
        <div style={{ ...input, minHeight: 'auto', borderColor: '#0ea5e9', color: '#bae6fd' }}>
          GitHub-Zugriffe laufen ausschließlich über die authentifizierte Sovereign-Backend-Session.
          Es wird kein PAT im Browser entgegengenommen, gespeichert oder an Rescue-Aufrufe weitergereicht.
        </div>
        <button type="button" style={button} disabled={busy || !repository.trim() || !evidence.trim()} onClick={() => { void diagnose(); }}>
          Kostenlos diagnostizieren
        </button>
      </div>

      <p role="status" aria-live="polite" style={{ minHeight: 24, color: '#bae6fd' }}>{message}</p>

      {diagnosis && (
        <section style={{ border: '1px solid #334155', borderRadius: 12, padding: 14 }}>
          <h2 style={{ marginTop: 0 }}>Diagnose</h2>
          <p><strong>{diagnosis.failureFamilyTitle}</strong> · Risiko {diagnosis.riskClass}</p>
          <p><code>{diagnosis.baseSha}</code></p>
          <p>{diagnosis.repairProposal}</p>
          <p>Betroffene Pfade: {diagnosis.affectedFiles.join(', ')}</p>
          <p>
            Repair Pack: {diagnosis.outcomeContract.repairPack.credits} Credits,
            höchstens {diagnosis.outcomeContract.repairPack.maxChangedFiles} Dateien,
            keine direkte Anwendung und kein Auto-Merge.
          </p>
          {entitlement && (
            <p>
              Entitlement: {entitlement.entitled ? 'serverseitig bestätigt' : 'Kauf erforderlich'} ·
              Guthaben {entitlement.availableCredits}
            </p>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <button type="button" style={button} disabled={busy} onClick={() => { void startRepair(); }}>
              Repair Pack starten
            </button>
            {entitlement && !entitlement.entitled && (
              <button type="button" style={button} onClick={() => setShowPaywall(true)}>
                Credits kaufen
              </button>
            )}
          </div>
        </section>
      )}

      {repair && (
        <section style={{ border: '1px solid #334155', borderRadius: 12, padding: 14, marginTop: 12 }}>
          <h2 style={{ marginTop: 0 }}>Reparaturstatus</h2>
          <p>Repair {repair.repairId} · Job {repair.jobId} · {repair.state}</p>
          <h3 id="rescue-delivery-choice">Ausgabe ausdrücklich wählen</h3>
          <p>
            Draft PR und Zero-Trust Capsule sind getrennte Wege. Die Capsule schreibt nichts nach
            GitHub und wendet den Patch nicht an.
          </p>
          <div role="group" aria-labelledby="rescue-delivery-choice" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            <button type="button" style={button} disabled={busy || currentJobId !== repair.jobId} onClick={() => { void publishDraftPr(); }}>
              Draft PR aus geprüfter Evidence erstellen
            </button>
            <button type="button" style={button} disabled={busy || currentJobId !== repair.jobId} onClick={() => { void downloadCapsule(); }}>
              Zero-Trust Capsule herunterladen
            </button>
            <button type="button" style={button} disabled={busy || !draftPrUrl} onClick={() => { void loadProofPack(); }}>
              ProofPack prüfen
            </button>
          </div>
        </section>
      )}

      {capsule && (
        <section aria-label="Zero-Trust Capsule Evidence" style={{ border: '1px solid #334155', borderRadius: 12, padding: 14, marginTop: 12 }}>
          <h2 style={{ marginTop: 0 }}>Zero-Trust Capsule</h2>
          <p>Basis-SHA: <code>{capsule.baseSha}</code></p>
          <p>Manifest-Evidence: <code>{capsule.capsuleSha256}</code></p>
          <p>Nur heruntergeladen — nicht angewendet, nicht gepusht und nicht deployed.</p>
        </section>
      )}

      {proofPack && (
        <section style={{ border: '1px solid #334155', borderRadius: 12, padding: 14, marginTop: 12 }}>
          <h2 style={{ marginTop: 0 }}>ProofPack</h2>
          <p>{proofPack.ready ? 'Vollständig' : 'Unvollständig'} · <code>{proofPack.proofSha256}</code></p>
          {proofPack.blockers.length > 0 && <p>Offen: {proofPack.blockers.join(', ')}</p>}
          <p>Rollback: Draft PR schließen oder den isolierten Commit revertieren.</p>
        </section>
      )}
      <PaywallModal isOpen={showPaywall} onClose={() => setShowPaywall(false)} />
    </section>
  );
}
