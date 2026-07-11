import React, { useEffect, useState } from 'react';
import {
  createAccountKey,
  deletePasskey,
  getSecurityOverview,
  registerPasskey,
  revokeAccountKey,
  updateSecurityPolicy,
  type SecurityOverview,
  type SecurityPolicy,
} from './securityApi';

const C = { bg:'#0e1116', surface:'#161c25', surface2:'#1c2333', border:'#263042', accent:'#58a6ff', amber:'#d29922', danger:'#f85149', text:'#e6edf3', sub:'#8b949e' } as const;
const button: React.CSSProperties = { minHeight:44, borderRadius:8, border:`1px solid ${C.border}`, background:C.surface2, color:C.text, padding:'0 12px', cursor:'pointer', fontFamily:'inherit' };

export function SecuritySettingsPanel({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<SecurityOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [newKey, setNewKey] = useState('');

  const load = async () => {
    setBusy(true);
    try { setData(await getSecurityOverview()); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  useEffect(() => { void load(); }, []);

  const patchPolicy = async (changes: Partial<SecurityPolicy>) => {
    setBusy(true);
    try {
      const policy = await updateSecurityPolicy(changes);
      setData(current => current ? { ...current, policy } : current);
      setError('');
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };

  const runMutation = async (task: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await task();
      setData(await getSecurityOverview());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };

  const addPasskey = async () => {
    await runMutation(() => registerPasskey('Dieses Gerät'));
  };

  const addKey = async () => {
    setBusy(true);
    try { const result = await createAccountKey('Persönlicher Sicherheits-Key'); setNewKey(result.key); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); setBusy(false); }
  };

  return (
    <div style={{ position:'fixed', inset:0, zIndex:9800, background:'rgba(0,0,0,.72)', display:'flex', justifyContent:'flex-end' }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <section style={{ width:'min(100%,520px)', maxHeight:'100dvh', overflowY:'auto', background:C.bg, borderLeft:`1px solid ${C.border}`, padding:18, color:C.text }}>
        <header style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
          <div><small style={{ color:C.accent, fontWeight:800 }}>KONTOSICHERHEIT</small><h2 style={{ margin:'4px 0 0', fontSize:20 }}>Passkeys &amp; Bestätigungen</h2></div>
          <button type="button" onClick={onClose} style={{ ...button, width:44, fontSize:22 }}>×</button>
        </header>
        {error && <div style={{ color:C.danger, border:`1px solid ${C.danger}55`, borderRadius:8, padding:10, marginBottom:12 }}>{error}</div>}
        {newKey && <OneTimeKey value={newKey} onDone={() => setNewKey('')} />}

        <Card title="Passkeys" text="Anmeldung und Bestätigung per Fingerabdruck, PIN oder Gerätesperre.">
          {(data?.passkeys ?? []).map(item => <Row key={item.id} title={item.label} sub={`${item.deviceType || 'WebAuthn-Gerät'}${item.backedUp ? ' · synchronisiert' : ''}`} action="Entfernen" onAction={() => void runMutation(() => deletePasskey(item.id))} />)}
          {!busy && !(data?.passkeys.length) && <p style={{ color:C.sub, fontSize:12 }}>Noch kein Passkey registriert.</p>}
          <button type="button" disabled={busy} onClick={() => void addPasskey()} style={{ ...button, width:'100%', background:C.accent, color:C.bg, fontWeight:800 }}>Passkey einrichten</button>
        </Card>

        <Card title="Sovereign Account Keys" text="Optionaler Notfallzugang und Ersatz für eine Step-up-Bestätigung.">
          {(data?.accountKeys ?? []).map(item => <Row key={item.id} title={item.label} sub={item.keyHint} action="Widerrufen" onAction={() => void runMutation(() => revokeAccountKey(item.id))} />)}
          <button type="button" disabled={busy} onClick={() => void addKey()} style={{ ...button, width:'100%' }}>Neuen Account Key erzeugen</button>
        </Card>

        {data?.policy && <PolicyCard policy={data.policy} busy={busy} patch={patchPolicy} />}
        <button type="button" onClick={onClose} style={{ ...button, width:'100%' }}>Fertig</button>
      </section>
    </div>
  );
}

function Card({ title, text, children }: React.PropsWithChildren<{ title:string; text:string }>) {
  return <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:14, marginBottom:12 }}><h3 style={{ margin:0, fontSize:14 }}>{title}</h3><p style={{ color:C.sub, fontSize:12, lineHeight:1.45 }}>{text}</p>{children}</div>;
}

function Row({ title, sub, action, onAction }: { title:string; sub:string; action:string; onAction:()=>void }) {
  return <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, background:C.surface2, border:`1px solid ${C.border}`, borderRadius:8, padding:10, marginBottom:8 }}><div style={{ minWidth:0 }}><div style={{ fontSize:13, fontWeight:700 }}>{title}</div><code style={{ color:C.sub, fontSize:10 }}>{sub}</code></div><button type="button" onClick={onAction} style={{ ...button, minHeight:36, color:C.danger }}>{action}</button></div>;
}

function OneTimeKey({ value, onDone }: { value:string; onDone:()=>void }) {
  return <div style={{ border:`1px solid ${C.amber}66`, borderRadius:10, padding:12, marginBottom:12 }}><strong style={{ color:C.amber }}>Nur jetzt sichtbar</strong><code style={{ display:'block', padding:10, margin:'8px 0', background:'#080b10', overflowWrap:'anywhere', userSelect:'all' }}>{value}</code><div style={{ display:'flex', gap:8 }}><button type="button" onClick={() => void navigator.clipboard.writeText(value)} style={button}>Kopieren</button><button type="button" onClick={onDone} style={button}>Sicher gespeichert</button></div></div>;
}

function PolicyCard({ policy, busy, patch }: { policy:SecurityPolicy; busy:boolean; patch:(changes:Partial<SecurityPolicy>)=>Promise<void> }) {
  return <Card title="Optionale Sicherheitsbarrieren" text="Standardmäßig deaktiviert. Freigaben sind aktionsgebunden, kurz gültig und nur einmal verwendbar.">
    <Toggle label="Credit-Käufe bestätigen" checked={policy.requirePurchaseStepUp} disabled={busy} onChange={value => void patch({ requirePurchaseStepUp:value })} />
    <NumberField label="Ab Euro" value={policy.purchaseThresholdEur} disabled={busy || !policy.requirePurchaseStepUp} onCommit={value => void patch({ purchaseThresholdEur:value })} />
    <Toggle label="Teure LLM-Routen bestätigen" checked={policy.requireExpensiveRouteStepUp} disabled={busy} onChange={value => void patch({ requireExpensiveRouteStepUp:value })} />
    <NumberField label="Ab Credits" value={policy.routeThresholdCredits} disabled={busy || !policy.requireExpensiveRouteStepUp} onCommit={value => void patch({ routeThresholdCredits:Math.round(value) })} />
  </Card>;
}

function Toggle({ label, checked, disabled, onChange }: { label:string; checked:boolean; disabled:boolean; onChange:(value:boolean)=>void }) {
  return <label style={{ display:'flex', alignItems:'center', justifyContent:'space-between', minHeight:44, borderTop:`1px solid ${C.border}`, fontSize:12 }}><span>{label}</span><input type="checkbox" checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)} /></label>;
}

function NumberField({ label, value, disabled, onCommit }: { label:string; value:number; disabled:boolean; onCommit:(value:number)=>void }) {
  const [draft,setDraft] = useState(String(value)); useEffect(() => setDraft(String(value)),[value]);
  return <label style={{ display:'flex', alignItems:'center', justifyContent:'space-between', minHeight:44, borderTop:`1px solid ${C.border}`, fontSize:12 }}><span>{label}</span><input type="number" min={0} value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)} onBlur={() => { const n=Number(draft); Number.isFinite(n) && n>=0 ? onCommit(n) : setDraft(String(value)); }} style={{ width:100, background:C.bg, color:C.text, border:`1px solid ${C.border}`, borderRadius:7, padding:8 }} /></label>;
}
