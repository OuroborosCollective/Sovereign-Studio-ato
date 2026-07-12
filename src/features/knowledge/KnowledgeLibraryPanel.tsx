import React, { useEffect, useState } from 'react';
import { repairMissingKnowledgeEmbeddings } from '../inference/areInferenceApi';
import {
  deleteKnowledgeSource,
  importKnowledgeUrl,
  listKnowledgeSources,
  searchKnowledge,
  uploadKnowledgeFile,
  type KnowledgeSearchResult,
  type KnowledgeSource,
} from './knowledgeApi';

const C = { bg:'#0e1116', panel:'#161c25', border:'#263042', accent:'#58a6ff', danger:'#f85149', text:'#e6edf3', sub:'#8b949e' } as const;
const control: React.CSSProperties = { minHeight:44, borderRadius:8, border:`1px solid ${C.border}`, background:C.bg, color:C.text, padding:'0 10px', fontFamily:'inherit' };

export function KnowledgeLibraryPanel({ onClose }: { onClose: () => void }) {
  const [sources,setSources] = useState<KnowledgeSource[]>([]);
  const [results,setResults] = useState<KnowledgeSearchResult[]>([]);
  const [url,setUrl] = useState('');
  const [query,setQuery] = useState('');
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState('');

  const load = async () => setSources(await listKnowledgeSources());
  useEffect(() => { void load().catch(reason => setMessage(String(reason))); }, []);
  const run = async (task:()=>Promise<void>) => {
    setBusy(true); setMessage('');
    try { await task(); }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  };
  const finishImport = async (result: Awaited<ReturnType<typeof uploadKnowledgeFile>>) => {
    let detail = result.duplicate ? 'Bereits vorhanden.' : `Gespeichert: ${result.source.title}`;
    if (!result.duplicate && result.source.status === 'partial') {
      detail += ` · Teilweise verarbeitet${result.blocker ? `: ${result.blocker}` : '. Fehlende Vektoren können separat repariert werden.'}`;
    } else if (!result.duplicate && result.blocker) {
      detail += ` · Blocker: ${result.blocker}`;
    }
    setMessage(detail);
    await load();
  };

  return <div style={{ position:'fixed', inset:0, zIndex:9800, background:'rgba(0,0,0,.72)', display:'flex', justifyContent:'flex-end' }}>
    <section style={{ width:'min(100%,600px)', overflowY:'auto', background:C.bg, color:C.text, padding:16 }}>
      <header style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div><small style={{ color:C.accent }}>REFERENZWISSEN</small><h2 style={{ margin:'4px 0 12px' }}>Wissensbibliothek</h2></div>
        <button type="button" onClick={onClose} style={control}>Schließen</button>
      </header>
      <p style={{ color:C.sub, fontSize:12 }}>Getrennt von Erfahrungswissen. SHA-256 verhindert Duplikate; pgvector macht Inhalte semantisch auffindbar.</p>
      {message && <p style={{ border:`1px solid ${C.border}`, padding:9, borderRadius:8 }}>{message}</p>}

      <Box title="URL importieren">
        <input value={url} onChange={e=>setUrl(e.target.value)} placeholder="GitHub- oder Wikipedia-URL" style={{ ...control, width:'100%', boxSizing:'border-box' }}/>
        <button type="button" disabled={busy||!url.trim()} style={{ ...control, width:'100%', marginTop:8, background:C.accent, color:C.bg }} onClick={()=>void run(async()=>{ const r=await importKnowledgeUrl(url.trim()); setUrl(''); await finishImport(r); })}>Importieren</button>
        <label style={{ ...control, display:'flex', alignItems:'center', justifyContent:'center', marginTop:8 }}>
          PDF, Markdown, Text oder Code hochladen
          <input hidden type="file" accept=".pdf,.txt,.md,.markdown,.mdx,.rst,.json,.yaml,.yml,.toml,.py,.ts,.tsx,.js,.jsx,.java,.kt,.c,.cc,.cpp,.h,.hpp,.rs,.go,.cs,.php,.rb,.sh,.sql" onChange={e=>{ const f=e.target.files?.[0]; if(f) void run(async()=>{ const labels={ preparing:'Upload wird vorbereitet…', uploading:'Datei wird nach R2 übertragen…', verifying:'R2-Objekt, Größe und SHA-256 werden geprüft…', processing:'Inhalt wird verarbeitet und eingebettet…', completed:'Upload vollständig bestätigt.', blocked:'Upload blockiert.' } as const; const r=await uploadKnowledgeFile(f,status=>setMessage(labels[status])); await finishImport(r); }); e.currentTarget.value=''; }}/>
        </label>
      </Box>

      <Box title="Semantische Testsuche">
        <div style={{ display:'flex', gap:8 }}><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Suchfrage" style={{ ...control, flex:1 }}/><button type="button" disabled={busy||!query.trim()} style={control} onClick={()=>void run(async()=>setResults(await searchKnowledge(query.trim(),8)))}>Suchen</button></div>
        {results.map(item=><article key={item.blockId} style={{ borderTop:`1px solid ${C.border}`, paddingTop:8, marginTop:8 }}><strong style={{ fontSize:12 }}>{item.sourceTitle}</strong><small style={{ color:C.accent, marginLeft:8 }}>{Math.round(Number(item.similarity)*100)}%</small><p style={{ fontSize:11, whiteSpace:'pre-wrap' }}>{item.content.slice(0,700)}</p></article>)}
      </Box>

      <Box title={`Quellen (${sources.length})`}>
        {sources.some(source=>source.status==='partial')&&<button type="button" disabled={busy} style={{ ...control, width:'100%', marginBottom:8 }} onClick={()=>void run(async()=>{ const repair=await repairMissingKnowledgeEmbeddings(25); setMessage(`${repair.repaired} Vektoren repariert${repair.remaining>0?`, ${repair.remaining} noch offen`:''}.`); await load(); })}>Fehlende Vektoren reparieren</button>}
        {sources.map(source=><div key={source.id} style={{ display:'flex', justifyContent:'space-between', gap:8, borderTop:`1px solid ${C.border}`, padding:'9px 0' }}><div><strong style={{ fontSize:12 }}>{source.title}</strong><div style={{ color:C.sub, fontSize:10 }}>{source.sourceType} · {source.status} · {source.chunkCount} Blöcke</div>{source.blocker&&<div style={{ color:'#d29922', fontSize:9 }}>{source.blocker}</div>}</div><button type="button" disabled={busy} style={{ ...control, color:C.danger }} onClick={()=>void run(async()=>{ await deleteKnowledgeSource(source.id); await load(); })}>Löschen</button></div>)}
        {!sources.length&&<p style={{ color:C.sub, fontSize:12 }}>Noch keine Quellen.</p>}
      </Box>
    </section>
  </div>;
}

function Box({ title,children }:React.PropsWithChildren<{title:string}>){ return <div style={{ background:C.panel, border:`1px solid ${C.border}`, borderRadius:10, padding:12, marginBottom:12 }}><h3 style={{ margin:'0 0 9px', fontSize:14 }}>{title}</h3>{children}</div>; }
