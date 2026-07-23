import React, { useState } from 'react';
import type { TestRunnerResult } from '../runtime/testRunnerRuntime';
import { C } from './builderConstants';
export function TestRunnerResultCard({ result, onRepair }: { readonly result: TestRunnerResult; readonly onRepair?: (prompt: string) => void }) {
  const [open, setOpen] = useState(false); const color = result.status === 'passed' ? C.green : result.status === 'failed' ? C.rose : C.amber; const icon = result.status === 'passed' ? '✅' : result.status === 'failed' ? '❌' : '⚠️';
  return <article data-testid="test-runner-result-card" style={{ margin:'8px 12px',padding:12,borderRadius:12,border:`1px solid ${color}55`,background:`${color}0d` }}>
    <div style={{ display:'flex',alignItems:'center',gap:8 }}><span>{icon}</span><strong style={{ color }}>{result.status === 'passed' ? 'Tests bestanden' : result.status === 'failed' ? 'Tests fehlgeschlagen' : 'Test-Runner blockiert'}</strong>{result.framework !== 'unknown' ? <code style={{ marginLeft:'auto',color:C.textMuted }}>{result.framework}</code> : null}</div>
    <p style={{ color:C.textSub,fontSize:12 }}>{result.summary}</p>
    {(result.counts.passed + result.counts.failed + result.counts.errors + result.counts.skipped) > 0 ? <div style={{ display:'flex',gap:8,flexWrap:'wrap',fontSize:11 }}><span style={{ color:C.green }}>{result.counts.passed} bestanden</span><span style={{ color:C.rose }}>{result.counts.failed} fehlgeschlagen</span><span style={{ color:C.amber }}>{result.counts.errors} Fehler</span><span style={{ color:C.textMuted }}>{result.counts.skipped} übersprungen</span></div> : null}
    {result.blocker ? <p style={{ color:C.amber,fontSize:11 }}>{result.blocker}</p> : null}
    {result.output ? <><button type="button" onClick={() => setOpen((value) => !value)} style={{ marginTop:8,background:'transparent',border:'none',color:C.sky,cursor:'pointer' }}>{open ? 'Ausgabe schließen' : 'Echte Test-Ausgabe anzeigen'}</button>{open ? <pre style={{ maxHeight:280,overflow:'auto',whiteSpace:'pre-wrap',fontSize:10,padding:10,background:C.bg,border:`1px solid ${C.border}`,color:C.text }}>{result.output}</pre> : null}</> : null}
    {result.hasRepairHint && onRepair ? <button type="button" onClick={() => onRepair(`Repariere die fehlgeschlagenen ${result.framework === 'unknown' ? '' : `${result.framework}-`}Tests aus der belegten Ausgabe. Erzeuge einen minimalen Fix mit Regressionstest und bereite nur einen Draft PR vor.\n\n${result.output.slice(0,6000)}`)} style={{ marginTop:10,minHeight:44,padding:'8px 14px',borderRadius:9,border:`1px solid ${C.rose}`,background:`${C.rose}18`,color:C.rose,cursor:'pointer' }}>🛠 Reparieren</button> : null}
  </article>;
}
export default TestRunnerResultCard;
