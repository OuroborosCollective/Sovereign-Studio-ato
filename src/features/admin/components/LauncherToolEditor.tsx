/**
 * LauncherToolEditor — Enable/disable tools, set badge and order via DB override.
 * No code change needed — all overrides go through the admin API.
 * Issue #460
 */

import React, { useState } from 'react';
import { ToggleLeft, ToggleRight, Tag, ArrowUp, ArrowDown } from 'lucide-react';
import type { LauncherToolOverride } from '../api/adminApiClient';
import type { UseAdminLauncherToolsResult } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;
const BADGES = ['', 'NEU', 'BETA', 'PRO'] as const;

function ToolRow({ tool, onUpdate, savingId }: {
  tool: LauncherToolOverride;
  onUpdate: (id: string, c: Partial<Pick<LauncherToolOverride, 'disabled'|'badge'|'sortOrder'>>) => Promise<void>;
  savingId: string | null;
}) {
  const busy = savingId === tool.id;
  return (
    <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 14px', borderBottom:`1px solid ${C.border}` }}>
      <button type="button" onClick={() => void onUpdate(tool.id, { disabled: !tool.disabled })} disabled={busy}
        style={{ background:'transparent', border:'none', cursor:'pointer', color:tool.disabled?C.textSub:C.accent, padding:0, display:'flex' }}
        title={tool.disabled?'Aktivieren':'Deaktivieren'}>
        {tool.disabled ? <ToggleLeft size={22}/> : <ToggleRight size={22}/>}
      </button>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:12, fontWeight:600, color:tool.disabled?C.textSub:C.text, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{tool.label}</div>
        <div style={{ fontSize:10, color:C.textSub, fontFamily:'monospace' }}>{tool.id}</div>
      </div>
      <select value={tool.badge??''} disabled={busy}
        onChange={e => { const v = e.target.value as LauncherToolOverride['badge']|''; void onUpdate(tool.id, { badge: v===''?null:v as LauncherToolOverride['badge'] }); }}
        style={{ background:C.bg, border:`1px solid ${C.border}`, borderRadius:6, padding:'4px 6px', fontSize:10, color:C.text, outline:'none', cursor:'pointer' }}>
        {BADGES.map(b => <option key={b} value={b}>{b===''?'Kein Badge':b}</option>)}
      </select>
      <div style={{ display:'flex', gap:2, alignItems:'center' }}>
        <button type="button" disabled={busy||tool.sortOrder<=0} onClick={() => void onUpdate(tool.id, { sortOrder: Math.max(0, tool.sortOrder-1) })}
          style={{ background:'transparent', border:`1px solid ${C.border}`, borderRadius:4, padding:'3px 5px', cursor:'pointer', color:C.textSub, opacity:tool.sortOrder<=0?0.3:1 }}><ArrowUp size={11}/></button>
        <button type="button" disabled={busy} onClick={() => void onUpdate(tool.id, { sortOrder: tool.sortOrder+1 })}
          style={{ background:'transparent', border:`1px solid ${C.border}`, borderRadius:4, padding:'3px 5px', cursor:'pointer', color:C.textSub }}><ArrowDown size={11}/></button>
        <span style={{ fontSize:10, color:C.textSub, minWidth:16, textAlign:'center' }}>{tool.sortOrder}</span>
      </div>
      {busy && <div style={{ width:12, height:12, borderRadius:'50%', border:`2px solid ${C.accent}`, borderTopColor:'transparent' }} />}
    </div>
  );
}

export function LauncherToolEditor({ api }: { api: UseAdminLauncherToolsResult }) {
  const { tools, loading, error, updateTool } = api;
  const [savingId, setSavingId] = useState<string|null>(null);

  const handle = async (id: string, c: Partial<Pick<LauncherToolOverride,'disabled'|'badge'|'sortOrder'>>) => {
    setSavingId(id);
    try { await updateTool(id, c); } finally { setSavingId(null); }
  };

  if (loading) return <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Lade Tools…</div>;
  if (error)   return <div style={{ padding:16, color:C.danger, fontSize:12 }}>{error}</div>;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:0 }}>
      <div style={{ fontSize:11, color:C.textSub, marginBottom:10 }}>Overrides ohne Code-Änderung — wirken sofort im Launcher.</div>
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden' }}>
        <div style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 14px', borderBottom:`1px solid ${C.border}` }}>
          <Tag size={12} color={C.textSub}/>
          <span style={{ fontSize:10, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>Launcher Tools ({tools.length})</span>
        </div>
        {tools.length===0 && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Tools registriert.</div>}
        {tools.map(t => <ToolRow key={t.id} tool={t} onUpdate={handle} savingId={savingId}/>)}
      </div>
    </div>
  );
}
