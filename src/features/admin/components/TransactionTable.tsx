/**
 * TransactionTable — Transaction history with type/user filters.
 * Issue #460
 */

import React from 'react';
import { Filter } from 'lucide-react';
import type { Transaction } from '../api/adminApiClient';
import type { UseAdminTransactionsResult } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390', danger:'#f87171' } as const;

const TYPE_LABELS: Record<Transaction['type'], string> = {
  credit_purchase:'Credit-Kauf', subscription:'Abo', refund:'Erstattung', adjustment:'Anpassung', usage:'Nutzung',
};
const STATUS_COLORS: Record<Transaction['status'], string> = {
  completed:'#34d399', pending:'#fbbf24', failed:'#f87171', refunded:'#818cf8',
};

export function finiteTransactionAmount(value: unknown): number | null {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatAmount(value: unknown, currency: string): string {
  const amount = finiteTransactionAmount(value);
  if (amount === null || amount <= 0) return '—';
  try {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: currency || 'EUR',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2).replace('.', ',')} ${currency || 'EUR'}`;
  }
}

export function TransactionTable({ api }: { api: UseAdminTransactionsResult }) {
  const { transactions, total, loading, error, filterType, setFilterType, setFilterUserId, filterUserId } = api;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'flex', gap:8 }}>
        <div style={{ position:'relative', flex:1 }}>
          <Filter size={11} style={{ position:'absolute', left:8, top:'50%', transform:'translateY(-50%)', color:C.textSub }} />
          <input type="text" placeholder="User-ID filtern…" value={filterUserId} onChange={e => setFilterUserId(e.target.value)}
            style={{ width:'100%', minHeight:44, boxSizing:'border-box', background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'9px 10px 9px 28px', fontSize:12, color:C.text, outline:'none' }} />
        </div>
        <select value={filterType} onChange={e => setFilterType(e.target.value)}
          style={{ minHeight:44, background:C.surface, border:`1px solid ${C.border}`, borderRadius:8, padding:'9px 10px', fontSize:12, color:C.text, outline:'none', cursor:'pointer' }}>
          <option value="">Alle Typen</option>
          {Object.entries(TYPE_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>

      <div style={{ fontSize:10, color:C.textSub }}>{total} Transaktionen</div>

      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflowX:'auto', overflowY:'hidden', WebkitOverflowScrolling:'touch' }}>
        <div style={{ display:'grid', gridTemplateColumns:'minmax(140px,1fr) 80px 86px 76px', gap:8, minWidth:430, padding:'9px 12px', borderBottom:`1px solid ${C.border}`, fontSize:10, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.06em' }}>
          <span>Beschreibung</span><span>Typ</span><span>Betrag</span><span>Status</span>
        </div>
        {loading && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Lade…</div>}
        {error   && <div style={{ padding:16, color:C.danger, fontSize:12 }}>{error}</div>}
        {!loading && transactions.map(t => {
          const amount = finiteTransactionAmount(t.amount);
          return (
            <div key={t.id} style={{ display:'grid', gridTemplateColumns:'minmax(140px,1fr) 80px 86px 76px', gap:8, padding:'10px 12px', borderBottom:`1px solid ${C.border}`, alignItems:'center', minWidth:430 }}>
              <div style={{ minWidth:0 }}>
                <div style={{ fontSize:11, color:C.text, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{t.description}</div>
                <div style={{ fontSize:10, color:C.textSub, overflowWrap:'anywhere' }}>{t.userEmail} · {new Date(t.createdAt).toLocaleDateString('de')}</div>
              </div>
              <div style={{ fontSize:10, color:C.textSub }}>{TYPE_LABELS[t.type]??t.type}</div>
              <div style={{ fontSize:11, fontWeight:600, color:amount !== null && amount > 0 ? '#34d399' : C.textSub }}>{formatAmount(t.amount, t.currency)}</div>
              <div><span style={{ fontSize:9, fontWeight:700, padding:'3px 6px', borderRadius:4, background:`${STATUS_COLORS[t.status]}22`, color:STATUS_COLORS[t.status], textTransform:'uppercase', letterSpacing:'0.05em' }}>{t.status}</span></div>
            </div>
          );
        })}
        {!loading && transactions.length===0 && !error && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Transaktionen.</div>}
      </div>
    </div>
  );
}
