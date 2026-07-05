/**
 * LauncherToolEditor — Enable/disable tools, set badge and order via DB override.
 * Also displays available Toolchain tools from the sovereign-universal-toolchain service.
 * Issue #460
 */

import React, { useState, useEffect } from 'react';
import { ToggleLeft, ToggleRight, Tag, ArrowUp, ArrowDown, Wrench, Cpu, Info } from 'lucide-react';
import type { LauncherToolOverride } from '../api/adminApiClient';
import type { UseAdminLauncherToolsResult } from '../hooks/useAdminApi';
import { adminApiClient } from '../api/adminApiClient';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;
const BADGES = ['', 'NEU', 'BETA', 'PRO'] as const;

interface ToolchainTool {
  name: string;
  description: string;
  write_action: boolean;
  requires_confirm?: boolean;
}

// ── Toolchain Tools Section ───────────────────────────────────────────────────

function ToolchainToolsSection() {
  const [tools, setTools] = useState<ToolchainTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApiClient.toolchainManifest()
      .then(data => {
        setTools(data.tools || []);
        setLoading(false);
      })
      .catch(err => {
        setError(String(err));
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 16, textAlign: 'center', color: C.textSub, fontSize: 12 }}>
        Lade Toolchain-Tools…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 16, color: C.danger, fontSize: 11 }}>
        ⚠️ Toolchain nicht erreichbar: {error}
      </div>
    );
  }

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden', marginTop: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderBottom: `1px solid ${C.border}`, background: '#0a1628' }}>
        <Cpu size={12} color={C.accent}/>
        <span style={{ fontSize: 10, fontWeight: 700, color: C.accent, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Verfügbare Toolchain-Tools ({tools.length})
        </span>
        <a
          href="#"
          onClick={(e) => { e.preventDefault(); alert('Toolchain-Tools werden vom sovereign-universal-toolchain Service bereitgestellt. Diese können im Tool verwendet aber nicht direkt im Admin deaktiviert werden.'); }}
          style={{ marginLeft: 'auto', color: C.textSub, cursor: 'help' }}
          title="Info"
        >
          <Info size={12}/>
        </a>
      </div>
      {tools.length === 0 && (
        <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>
          Keine Toolchain-Tools verfügbar.
        </div>
      )}
      {tools.map(tool => (
        <div key={tool.name} style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Wrench size={14} color={C.accent} style={{ opacity: 0.6 }}/>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>{tool.name}</div>
              <div style={{ fontSize: 10, color: C.textSub, marginTop: 2 }}>{tool.description}</div>
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {tool.write_action && (
                <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: '#f59e0b20', color: '#f59e0b', border: '1px solid #f59e0b40' }}>
                  WRITE
                </span>
              )}
              {tool.requires_confirm && (
                <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: '#3b82f620', color: '#3b82f6', border: '1px solid #3b82f640' }}>
                  CONFIRM
                </span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Launcher Tool Row ─────────────────────────────────────────────────────────

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
      {/* Toolchain Tools Section */}
      <ToolchainToolsSection />

      {/* Launcher Tools Section */}
      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden', marginTop: 12 }}>
        <div style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 14px', borderBottom:`1px solid ${C.border}` }}>
          <Tag size={12} color={C.textSub}/>
          <span style={{ fontSize:10, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>Launcher Tools ({tools.length})</span>
        </div>
        <div style={{ fontSize:11, color:C.textSub, padding:'8px 14px', borderBottom:`1px solid ${C.border}` }}>
          Overrides ohne Code-Änderung — wirken sofort im Launcher.
        </div>
        {tools.length===0 && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Tools registriert.</div>}
        {tools.map(t => <ToolRow key={t.id} tool={t} onUpdate={handle} savingId={savingId}/>)}
      </div>
    </div>
  );
}
