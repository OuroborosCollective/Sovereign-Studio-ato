/**
 * LlmRouteEditor — Configure LLM models, routes and credit costs.
 * Full implementation for Issue #461 (LLM Routing).
 * Issue #460
 */

import React, { useState } from 'react';
import { ToggleLeft, ToggleRight, Zap } from 'lucide-react';
import type { LlmRoute } from '../api/adminApiClient';
import type { UseAdminLlmRoutesResult } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;

function RouteRow({ route, onUpdate, savingId }: {
  route: LlmRoute;
  onUpdate: (id:string, c:Partial<Pick<LlmRoute,'creditsPerUnit'|'disabled'|'priority'>>) => Promise<void>;
  savingId: string|null;
}) {
  const busy = savingId === route.id;
  const [localCredits, setLocalCredits] = useState(String(route.creditsPerUnit));

  const commitCredits = () => {
    const n = parseFloat(localCredits);
    if (!isNaN(n) && n !== route.creditsPerUnit) void onUpdate(route.id, { creditsPerUnit: n });
  };

  return (
    <div style={{ padding:'12px 14px', borderBottom:`1px solid ${C.border}`, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={{ display:'flex', alignItems:'center', gap:10 }}>
        <button type="button" onClick={() => void onUpdate(route.id, { disabled: !route.disabled })} disabled={busy}
          style={{ background:'transparent', border:'none', cursor:'pointer', color:route.disabled?C.textSub:C.accent, padding:0, display:'flex' }}
          title={route.disabled?'Aktivieren':'Deaktivieren'}>
          {route.disabled ? <ToggleLeft size={20}/> : <ToggleRight size={20}/>}
        </button>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:12, fontWeight:600, color:route.disabled?C.textSub:C.text }}>{route.modelName}</div>
          <div style={{ fontSize:10, color:C.textSub }}>{route.provider} · {route.modelId}</div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:4 }}>
          <span style={{ fontSize:10, color:C.textSub }}>Prio:</span>
          <input type="number" min={1} max={99} value={route.priority}
            onChange={e => void onUpdate(route.id, { priority: parseInt(e.target.value)||1 })}
            style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:'3px 6px', fontSize:11, color:C.text, width:44, textAlign:'center', outline:'none' }} />
        </div>
        {busy && <div style={{ width:12, height:12, borderRadius:'50%', border:`2px solid ${C.accent}`, borderTopColor:'transparent' }} />}
      </div>

      <div style={{ display:'flex', alignItems:'center', gap:8, paddingLeft:30 }}>
        <Zap size={11} color={C.textSub}/>
        <span style={{ fontSize:10, color:C.textSub }}>Credits / Einheit:</span>
        <input type="number" min={0} step={0.0001} value={localCredits}
          onChange={e => setLocalCredits(e.target.value)}
          onBlur={commitCredits}
          onKeyDown={e => e.key==='Enter' && commitCredits()}
          style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:4, padding:'3px 8px', fontSize:11, color:C.text, width:80, outline:'none' }} />
        <span style={{ fontSize:10, color:C.textSub }}>≈ € {(route.creditsPerUnit * 0.0001).toFixed(4)}</span>
      </div>
    </div>
  );
}

export function LlmRouteEditor({ api }: { api: UseAdminLlmRoutesResult }) {
  const { routes, loading, error, updateRoute } = api;
  const [savingId, setSavingId] = useState<string|null>(null);

  const handle = async (id:string, c:Partial<Pick<LlmRoute,'creditsPerUnit'|'disabled'|'priority'>>) => {
    setSavingId(id);
    try { await updateRoute(id,c); } finally { setSavingId(null); }
  };

  if (loading) return <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Lade LLM-Routen…</div>;
  if (error)   return <div style={{ padding:16, color:C.danger, fontSize:12 }}>{error}</div>;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
      <div style={{ fontSize:11, color:C.textSub, marginBottom:10 }}>
        Kosten: 1 Credit = € 0,0001. Routen mit Priorität 1 werden bevorzugt.
      </div>
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden' }}>
        <div style={{ padding:'8px 14px', borderBottom:`1px solid ${C.border}`, fontSize:10, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>
          LLM Routen ({routes.length})
        </div>
        {routes.length===0 && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Routen konfiguriert.</div>}
        {routes.map(r => <RouteRow key={r.id} route={r} onUpdate={handle} savingId={savingId}/>)}
      </div>
    </div>
  );
}
