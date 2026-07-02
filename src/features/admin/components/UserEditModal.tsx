/**
 * UserEditModal — Credits anpassen, Rolle ändern, Account sperren.
 * User confirms all write actions — no auto-execute.
 * Issue #460
 */

import React, { useState } from 'react';
import { X, Save, AlertTriangle } from 'lucide-react';
import type { AdminUser } from '../api/adminApiClient';
import type { UseAdminUsersResult } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;

interface Props { user: AdminUser; api: Pick<UseAdminUsersResult,'updateUser'|'adjustCredits'>; onClose: () => void; }

export function UserEditModal({ user, api, onClose }: Props) {
  const [role, setRole]   = useState<AdminUser['role']>(user.role);
  const [sub,  setSub]    = useState<AdminUser['subscriptionStatus']>(user.subscriptionStatus);
  const [banned, setBanned] = useState(user.isBanned);
  const [delta, setDelta] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error,  setError]  = useState<string | null>(null);
  const [ok,     setOk]     = useState<string | null>(null);

  const field: React.CSSProperties = { background:C.bg, border:`1px solid ${C.border}`, borderRadius:8, padding:'7px 10px', fontSize:12, color:C.text, outline:'none', width:'100%', boxSizing:'border-box' };
  const lbl:   React.CSSProperties = { fontSize:10, color:C.textSub, marginBottom:4, display:'block', textTransform:'uppercase', letterSpacing:'0.06em' };

  const handleProfile = async () => {
    setSaving(true); setError(null); setOk(null);
    try { await api.updateUser(user.id, { role, subscriptionStatus: sub, isBanned: banned }); setOk('Profil gespeichert.'); }
    catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  const handleCredits = async () => {
    const n = parseInt(delta, 10);
    if (isNaN(n) || n === 0) { setError('Gültigen Betrag eingeben.'); return; }
    if (!reason.trim()) { setError('Grund fehlt.'); return; }
    setSaving(true); setError(null); setOk(null);
    try { await api.adjustCredits(user.id, n, reason.trim()); setOk(`${n>0?'+':''}${n} Credits angepasst.`); setDelta(''); setReason(''); }
    catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  return (
    <>
      <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.6)', zIndex:300, backdropFilter:'blur(2px)' }} />
      <div style={{ position:'fixed', left:'50%', top:'50%', transform:'translate(-50%,-50%)', zIndex:301, width:340, background:C.surface, border:`1px solid ${C.border}`, borderRadius:16, display:'flex', flexDirection:'column', overflow:'hidden', boxShadow:'0 24px 60px rgba(0,0,0,0.6)' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'14px 16px', borderBottom:`1px solid ${C.border}` }}>
          <div><div style={{ fontSize:13, fontWeight:700, color:C.text }}>{user.displayName}</div><div style={{ fontSize:10, color:C.textSub }}>{user.email}</div></div>
          <button type="button" onClick={onClose} style={{ background:'transparent', border:'none', cursor:'pointer', color:C.textSub }}><X size={15} /></button>
        </div>

        <div style={{ padding:16, display:'flex', flexDirection:'column', gap:14, overflowY:'auto' }}>
          {error && <div style={{ background:'#f8717120', border:'1px solid #f8717140', borderRadius:8, padding:'8px 12px', fontSize:11, color:C.danger, display:'flex', gap:6 }}><AlertTriangle size={13} style={{ flexShrink:0, marginTop:1 }} />{error}</div>}
          {ok    && <div style={{ background:'#00d9b120', border:'1px solid #00d9b140', borderRadius:8, padding:'8px 12px', fontSize:11, color:C.accent }}>✓ {ok}</div>}

          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ fontSize:11, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>Profil</div>
            <div><label style={lbl}>Rolle</label>
              <select value={role} onChange={e => setRole(e.target.value as AdminUser['role'])} style={field}>
                <option value="user">User</option><option value="admin">Admin</option><option value="superadmin">Superadmin</option>
              </select></div>
            <div><label style={lbl}>Abo-Status</label>
              <select value={sub} onChange={e => setSub(e.target.value as AdminUser['subscriptionStatus'])} style={field}>
                <option value="free">Free</option><option value="trialing">Trialing</option><option value="active">Active</option><option value="canceled">Canceled</option><option value="past_due">Past Due</option>
              </select></div>
            <label style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer', fontSize:12, color:banned?C.danger:C.text }}>
              <input type="checkbox" checked={banned} onChange={e => setBanned(e.target.checked)} style={{ accentColor:C.danger, width:14, height:14 }} />
              Account sperren
            </label>
            <button type="button" onClick={handleProfile} disabled={saving} style={{ background:C.accent, border:'none', borderRadius:8, padding:'8px 0', fontSize:12, fontWeight:700, color:'#000', cursor:saving?'not-allowed':'pointer', opacity:saving?0.6:1, display:'flex', alignItems:'center', justifyContent:'center', gap:6 }}>
              <Save size={13} /> Profil speichern
            </button>
          </div>

          <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:14, display:'flex', flexDirection:'column', gap:10 }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
              <div style={{ fontSize:11, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>Credits</div>
              <div style={{ fontSize:11, color:C.textSub }}>Aktuell: <strong style={{ color:C.text }}>{user.credits.toLocaleString('de')}</strong></div>
            </div>
            <div><label style={lbl}>Betrag (+/-)</label>
              <input type="number" placeholder="100 oder -50" value={delta} onChange={e => setDelta(e.target.value)} style={field} /></div>
            <div><label style={lbl}>Grund (Audit-Log)</label>
              <input type="text" placeholder="Testgutschrift, Fehlerkorrektur…" value={reason} onChange={e => setReason(e.target.value)} style={field} /></div>
            <button type="button" onClick={handleCredits} disabled={saving||!delta||!reason} style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'8px 0', fontSize:12, fontWeight:700, color:C.text, cursor:(saving||!delta||!reason)?'not-allowed':'pointer', opacity:(saving||!delta||!reason)?0.5:1 }}>
              Credits anpassen
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
