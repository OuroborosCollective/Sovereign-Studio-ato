import React, { useState } from 'react';
import type { AutoCodeReviewResult } from '../runtime/autoCodeReviewRuntime';
import { categoryLabel, severityIcon } from '../runtime/autoCodeReviewRuntime';
import { C } from './builderConstants';
export function AutoCodeReviewCard({ result, onCancel }: { readonly result: AutoCodeReviewResult; readonly onCancel?: () => void }) {
  const [open,setOpen] = useState(result.decision !== 'passed'); const blocked = result.decision !== 'passed'; const color = result.decision === 'passed' ? C.green : result.decision === 'blocked_high' ? C.rose : C.amber;
  return <article data-testid="auto-code-review-card" style={{ margin:'8px 12px',padding:12,borderRadius:12,border:`1px solid ${color}55`,background:`${color}0d` }}>
    <div style={{ display:'flex',alignItems:'center',gap:8 }}><span>{result.decision === 'passed' ? '✅' : result.decision === 'blocked_high' ? '🔴' : '⚠️'}</span><strong style={{ color }}>{result.decision === 'passed' ? 'Code Review bestanden' : result.decision === 'blocked_high' ? 'Code Review blockiert' : 'Code Review nicht verfügbar'}</strong><span style={{ marginLeft:'auto',fontSize:10,color:C.textMuted }}>{result.resolvedTransport || 'keine Route'}{result.fallbackUsed ? ' · Fallback' : ''}</span></div>
    <p style={{ color:C.textSub,fontSize:12 }}>{result.summary}</p>
    <div style={{ display:'flex',gap:8,fontSize:11 }}><span style={{ color:C.rose }}>{result.highCount} HIGH</span><span style={{ color:C.amber }}>{result.mediumCount} MEDIUM</span><span style={{ color:C.green }}>{result.lowCount} LOW</span></div>
    {result.findings.length ? <><button type="button" aria-expanded={open} title={open ? 'Gefundene Schwachstellen ausblenden' : 'Gefundene Schwachstellen einblenden'} onClick={() => setOpen((value) => !value)} style={{ marginTop:8,background:'transparent',border:'none',color:C.sky,cursor:'pointer' }}>{open ? 'Findings schließen' : 'Findings anzeigen'}</button>{open ? <div>{result.findings.map((finding,index) => <div key={`${finding.file}-${index}`} style={{ marginTop:6,padding:8,borderRadius:8,border:`1px solid ${finding.severity === 'HIGH' ? C.rose : C.border}`,background:C.bg }}><div style={{ fontSize:10,color:C.textMuted }}>{severityIcon(finding.severity)} {finding.severity} · {categoryLabel(finding.category)} · {finding.file}{finding.lineHint ? ` · ${finding.lineHint}` : ''}</div><div style={{ fontSize:12,color:C.text }}>{finding.description}</div></div>)}</div> : null}</> : null}
    {result.error ? <p style={{ fontSize:10,color:C.amber }}>Blocker: {result.error}</p> : null}
    {blocked && onCancel ? <button type="button" onClick={onCancel} title="Zurück zum Fix-Workflow wechseln" style={{ marginTop:8,minHeight:44,padding:'8px 14px',borderRadius:9,border:`1px solid ${color}`,background:`${color}18`,color,cursor:'pointer' }}>Zurück zum Fix</button> : null}
  </article>;
}
export default AutoCodeReviewCard;
