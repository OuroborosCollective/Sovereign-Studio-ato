/**
 * UserTable — Paginated user list with search, inline role/ban badges.
 * Issue #460
 */

import React from 'react';
import { Search, ChevronLeft, ChevronRight, Edit2, Ban } from 'lucide-react';
import type { AdminUser } from '../api/adminApiClient';
import type { UseAdminUsersResult } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;

interface UserTableProps { api: UseAdminUsersResult; onEdit: (u: AdminUser) => void; }

function roleBadge(role: AdminUser['role']) {
  const map = { user:{label:'User',color:'#64748b'}, admin:{label:'Admin',color:'#818cf8'}, superadmin:{label:'Super',color:'#f59e0b'} };
  const { label, color } = map[role] ?? map.user;
  return <span style={{ fontSize:9, fontWeight:700, padding:'2px 6px', borderRadius:4, background:`${color}22`, color, textTransform:'uppercase', letterSpacing:'0.05em' }}>{label}</span>;
}

function subBadge(s: AdminUser['subscriptionStatus']) {
  const map = { active:'#34d399', trialing:'#60a5fa', canceled:'#64748b', past_due:'#f87171', free:'#64748b' };
  const color = map[s] ?? '#64748b';
  return <span style={{ fontSize:9, fontWeight:600, padding:'2px 6px', borderRadius:4, background:`${color}22`, color, textTransform:'uppercase', letterSpacing:'0.05em' }}>{s}</span>;
}

export function UserTable({ api, onEdit }: UserTableProps) {
  const { users, total, page, loading, error, search, setSearch, setPage } = api;
  const totalPages = Math.max(1, Math.ceil(total / 50));

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ position:'relative' }}>
        <Search size={13} style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:C.textSub }} />
        <input type="text" placeholder="E-Mail oder Name suchen…" value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); }}
          style={{ width:'100%', minHeight:48, boxSizing:'border-box', background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'10px 12px 10px 34px', fontSize:12, color:C.text, outline:'none' }} />
      </div>

      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflowX:'auto', overflowY:'hidden', WebkitOverflowScrolling:'touch' }}>
        <div style={{ display:'grid', gridTemplateColumns:'minmax(180px,1fr) 72px 88px 72px 48px', gap:8, minWidth:500, padding:'9px 12px', borderBottom:`1px solid ${C.border}`, fontSize:10, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.06em' }}>
          <span>Nutzer</span><span>Rolle</span><span>Abo</span><span>Credits</span><span />
        </div>

        {loading && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Lade…</div>}
        {error   && <div style={{ padding:16, color:C.danger, fontSize:12, textAlign:'center' }}>{error}</div>}

        {!loading && users.map(u => (
          <div key={u.id} style={{ display:'grid', gridTemplateColumns:'minmax(180px,1fr) 72px 88px 72px 48px', gap:8, minWidth:500, minHeight:58, padding:'9px 12px', borderBottom:`1px solid ${C.border}`, opacity:u.isBanned ? 0.5 : 1, alignItems:'center' }}>
            <div style={{ minWidth:0 }}>
              <div style={{ fontSize:12, color:C.text, fontWeight:600, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', display:'flex', alignItems:'center', gap:4 }}>
                {u.displayName}{u.isBanned && <Ban size={11} color={C.danger} />}
              </div>
              <div style={{ fontSize:10, color:C.textSub, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{u.email}</div>
            </div>
            <div>{roleBadge(u.role)}</div>
            <div>{subBadge(u.subscriptionStatus)}</div>
            <div style={{ fontSize:12, color:C.text, fontWeight:600 }}>{u.credits.toLocaleString('de')}</div>
            <button type="button" onClick={() => onEdit(u)} style={{ width:44, minWidth:44, minHeight:44, background:'transparent', border:`1px solid ${C.border}`, cursor:'pointer', padding:4, borderRadius:8, color:C.textSub, display:'flex', alignItems:'center', justifyContent:'center' }} aria-label={`${u.displayName} bearbeiten`}><Edit2 size={16} /></button>
          </div>
        ))}

        {!loading && users.length === 0 && !error && (
          <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Nutzer gefunden.</div>
        )}
      </div>

      {totalPages > 1 && (
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', fontSize:11, color:C.textSub }}>
          <button type="button" disabled={page<=1} onClick={() => setPage(page-1)} style={{ minWidth:44, minHeight:44, background:'transparent', border:`1px solid ${C.border}`, borderRadius:8, padding:'8px 10px', cursor:page<=1?'not-allowed':'pointer', color:C.textSub, opacity:page<=1?0.4:1 }} aria-label="Vorherige Nutzerseite"><ChevronLeft size={16} /></button>
          <span>Seite {page} / {totalPages} ({total})</span>
          <button type="button" disabled={page>=totalPages} onClick={() => setPage(page+1)} style={{ minWidth:44, minHeight:44, background:'transparent', border:`1px solid ${C.border}`, borderRadius:8, padding:'8px 10px', cursor:page>=totalPages?'not-allowed':'pointer', color:C.textSub, opacity:page>=totalPages?0.4:1 }} aria-label="Nächste Nutzerseite"><ChevronRight size={16} /></button>
        </div>
      )}
    </div>
  );
}
