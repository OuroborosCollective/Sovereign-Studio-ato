/**
 * LauncherToolEditor — Manage launcher tools and toolchain tools.
 * Issue #460
 */

import React, { useState, useEffect } from 'react';
import { ToggleLeft, ToggleRight, Tag, ArrowUp, ArrowDown, Wrench, Cpu, Plus, X, Edit2, Trash2 } from 'lucide-react';
import type { LauncherToolOverride } from '../api/adminApiClient';
import type { UseAdminLauncherToolsResult } from '../hooks/useAdminApi';
import { adminApiClient } from '../api/adminApiClient';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171', warn:'#f59e0b' } as const;
const BADGES = ['', 'NEU', 'BETA', 'PRO'] as const;

interface ToolchainTool {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  writeAction: boolean;
  requiresConfirm: boolean;
  sortOrder: number;
}

// ── Toolchain Tools Manager ──────────────────────────────────────────────────

function ToolchainToolsManager() {
  const [tools, setTools] = useState<ToolchainTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formWrite, setFormWrite] = useState(false);
  const [formConfirm, setFormConfirm] = useState(false);
  const [formEnabled, setFormEnabled] = useState(true);

  const loadTools = async () => {
    setLoading(true);
    try {
      const data = await adminApiClient.getToolchainTools();
      setTools(data.tools || []);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadTools(); }, []);

  const resetForm = () => {
    setFormName('');
    setFormDesc('');
    setFormWrite(false);
    setFormConfirm(false);
    setFormEnabled(true);
    setShowAdd(false);
    setEditingId(null);
  };

  const handleSave = async () => {
    if (!formName.trim()) return;
    setSaving(true);
    try {
      if (editingId) {
        await adminApiClient.updateToolchainTool(editingId, {
          name: formName,
          description: formDesc,
          writeAction: formWrite,
          requiresConfirm: formConfirm,
          enabled: formEnabled,
        });
      } else {
        await adminApiClient.createToolchainTool({
          name: formName,
          description: formDesc,
          writeAction: formWrite,
          requiresConfirm: formConfirm,
          enabled: formEnabled,
        });
      }
      resetForm();
      loadTools();
    } catch (e) {
      alert(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tool wirklich löschen?')) return;
    try {
      await adminApiClient.deleteToolchainTool(id);
      loadTools();
    } catch (e) {
      alert(String(e));
    }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await adminApiClient.updateToolchainTool(id, { enabled });
      loadTools();
    } catch (e) {
      alert(String(e));
    }
  };

  const startEdit = (tool: ToolchainTool) => {
    setFormName(tool.name);
    setFormDesc(tool.description || '');
    setFormWrite(tool.writeAction);
    setFormConfirm(tool.requiresConfirm);
    setFormEnabled(tool.enabled);
    setEditingId(tool.id);
    setShowAdd(true);
  };

  if (loading) return <div style={{ padding:16, textAlign:'center', color:C.textSub, fontSize:12 }}>Lade…</div>;
  if (error) return <div style={{ padding:16, color:C.danger, fontSize:11 }}>Fehler: {error}</div>;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: 12, overflow: 'hidden', marginTop: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderBottom: `1px solid ${C.border}`, background: '#0a1628' }}>
        <Cpu size={12} color={C.accent}/>
        <span style={{ fontSize: 10, fontWeight: 700, color: C.accent, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Toolchain-Tools ({tools.length})
        </span>
        <button
          onClick={() => setShowAdd(true)}
          style={{ marginLeft: 'auto', background: C.accent, border: 'none', borderRadius: 4, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, color: '#000', fontSize: 10, fontWeight: 600 }}
        >
          <Plus size={11}/> Hinzufügen
        </button>
      </div>

      {showAdd && (
        <div style={{ padding: 14, borderBottom: `1px solid ${C.border}`, background: '#0d1520' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: C.text, marginBottom: 10 }}>
            {editingId ? 'Tool bearbeiten' : 'Neues Tool hinzufügen'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <input
              type="text"
              placeholder="Tool-Name (z.B. github_apply_patch)"
              value={formName}
              onChange={e => setFormName(e.target.value)}
              disabled={!!editingId}
              style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: '6px 10px', fontSize: 12, color: C.text, outline: 'none' }}
            />
            <input
              type="text"
              placeholder="Beschreibung"
              value={formDesc}
              onChange={e => setFormDesc(e.target.value)}
              style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: '6px 10px', fontSize: 12, color: C.text, outline: 'none' }}
            />
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.textSub }}>
                <input type="checkbox" checked={formWrite} onChange={e => setFormWrite(e.target.checked)}/>
                Write-Action
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.textSub }}>
                <input type="checkbox" checked={formConfirm} onChange={e => setFormConfirm(e.target.checked)}/>
                Require Confirm
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.textSub }}>
                <input type="checkbox" checked={formEnabled} onChange={e => setFormEnabled(e.target.checked)}/>
                Aktiviert
              </label>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button
                onClick={handleSave}
                disabled={saving || !formName.trim()}
                style={{ background: C.accent, border: 'none', borderRadius: 6, padding: '6px 14px', fontSize: 11, fontWeight: 600, color: '#000', cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.5 : 1 }}
              >
                {saving ? 'Speichere…' : 'Speichern'}
              </button>
              <button
                onClick={resetForm}
                style={{ background: 'transparent', border: `1px solid ${C.border}`, borderRadius: 6, padding: '6px 14px', fontSize: 11, color: C.textSub, cursor: 'pointer' }}
              >
                Abbrechen
              </button>
            </div>
          </div>
        </div>
      )}

      {tools.length === 0 && !showAdd && (
        <div style={{ padding: 24, textAlign: 'center', color: C.textSub, fontSize: 12 }}>
          Keine Toolchain-Tools. Klicke "Hinzufügen" um ein neues Tool zu registrieren.
        </div>
      )}

      {tools.map(tool => (
        <div key={tool.id} style={{ padding: '10px 14px', borderBottom: `1px solid ${C.border}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              onClick={() => handleToggle(tool.id, !tool.enabled)}
              style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: tool.enabled ? C.accent : C.textSub, padding: 0 }}
              title={tool.enabled ? 'Deaktivieren' : 'Aktivieren'}
            >
              {tool.enabled ? <ToggleRight size={20}/> : <ToggleLeft size={20}/>}
            </button>
            <Wrench size={14} color={tool.enabled ? C.accent : C.textSub} style={{ opacity: 0.6 }}/>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: tool.enabled ? C.text : C.textSub }}>{tool.name}</div>
              {tool.description && <div style={{ fontSize: 10, color: C.textSub, marginTop: 2 }}>{tool.description}</div>}
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {tool.writeAction && (
                <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: `${C.warn}20`, color: C.warn, border: `1px solid ${C.warn}40` }}>
                  WRITE
                </span>
              )}
              {tool.requiresConfirm && (
                <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: '#3b82f620', color: '#3b82f6', border: '1px solid #3b82f640' }}>
                  CONFIRM
                </span>
              )}
            </div>
            <button onClick={() => startEdit(tool)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: C.textSub, padding: 4 }}>
              <Edit2 size={13}/>
            </button>
            <button onClick={() => handleDelete(tool.id)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: C.danger, padding: 4 }}>
              <Trash2 size={13}/>
            </button>
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
      {/* Toolchain Tools Manager */}
      <ToolchainToolsManager />

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
