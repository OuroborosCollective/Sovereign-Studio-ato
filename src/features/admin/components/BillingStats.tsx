/**
 * BillingStats — MRR, active subscriptions, credit volume.
 * Issue #460
 */

import React from 'react';
import { TrendingUp, Users, Zap, DollarSign } from 'lucide-react';
import { useAdminBillingStats, useAdminTransactions } from '../hooks/useAdminApi';

const C = { bg:'#0e1116', surface:'#161c24', border:'#232d3a', accent:'#00d9b1', text:'#cdd9e5', textSub:'#768390' } as const;

function StatCard({ icon:Icon, label, value, sub, color }: { icon: React.ComponentType<{size?:number;color?:string}>; label:string; value:string; sub?:string; color:string }) {
  return (
    <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, padding:16, display:'flex', gap:12, alignItems:'flex-start' }}>
      <div style={{ padding:8, borderRadius:8, background:`${color}22`, flexShrink:0 }}><Icon size={18} color={color}/></div>
      <div>
        <div style={{ fontSize:11, color:C.textSub, marginBottom:4 }}>{label}</div>
        <div style={{ fontSize:22, fontWeight:700, color:C.text }}>{value}</div>
        {sub && <div style={{ fontSize:10, color:C.textSub, marginTop:2 }}>{sub}</div>}
      </div>
    </div>
  );
}

export function BillingStats() {
  const { stats, loading, error } = useAdminBillingStats();
  const { transactions, loading:txLoading } = useAdminTransactions();

  if (loading||txLoading) return <div style={{ color:C.textSub, fontSize:12, padding:24, textAlign:'center' }}>Lade Billing-Daten…</div>;
  if (error) return <div style={{ color:'#f87171', fontSize:12, padding:24, textAlign:'center' }}>{error}</div>;
  if (!stats) return null;

  const fmt = (n:number) => n.toFixed(2).replace('.',',');

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <StatCard icon={TrendingUp} label="MRR"           value={`€ ${fmt(stats.mrr)}`}            sub="Monatlich wiederkehrend" color="#00d9b1"/>
        <StatCard icon={Users}      label="Aktive Abos"   value={String(stats.activeSubscriptions)} sub="Zahlende Nutzer"          color="#818cf8"/>
        <StatCard icon={Zap}        label="Total Credits"  value={stats.totalCredits.toLocaleString('de')} sub="Über alle Nutzer" color="#fb923c"/>
        <StatCard icon={DollarSign} label="Umsatz gesamt" value={`€ ${fmt(stats.totalRevenue)}`}   sub={`Churn ${(stats.churnRate*100).toFixed(1)} %`} color="#34d399"/>
      </div>

      <div style={{ background:C.surface, border:`1px solid ${C.border}`, borderRadius:12, overflow:'hidden' }}>
        <div style={{ padding:'10px 14px', borderBottom:`1px solid ${C.border}`, fontSize:11, fontWeight:700, color:C.textSub, textTransform:'uppercase', letterSpacing:'0.08em' }}>Letzte Transaktionen</div>
        {transactions.slice(0,5).map(t => (
          <div key={t.id} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'8px 14px', borderBottom:`1px solid ${C.border}` }}>
            <div>
              <div style={{ fontSize:12, color:C.text }}>{t.userEmail}</div>
              <div style={{ fontSize:10, color:C.textSub }}>{t.description}</div>
            </div>
            <div style={{ textAlign:'right' }}>
              <div style={{ fontSize:12, fontWeight:600, color:t.amount>0?'#34d399':C.textSub }}>{t.amount>0?`+ € ${fmt(t.amount)}`:'—'}</div>
              <div style={{ fontSize:10, color:C.textSub }}>{new Date(t.createdAt).toLocaleDateString('de')}</div>
            </div>
          </div>
        ))}
        {transactions.length===0 && <div style={{ padding:24, textAlign:'center', color:C.textSub, fontSize:12 }}>Keine Transaktionen</div>}
      </div>
    </div>
  );
}
