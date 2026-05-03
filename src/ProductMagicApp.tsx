import React, { useMemo, useState } from 'react';
import { Bot, Download, Eye, FolderTree, Plus, Rocket, Send, Shield, Sparkles, Trash2, Wand2 } from 'lucide-react';

type FileItem = { path: string; icon: string };
type Card = { id: string; title: string; body: string };

const makeId = () => String(Date.now() + Math.random());
const demoFiles: FileItem[] = [
  { path: 'src/App.tsx', icon: '🟦' },
  { path: 'src/main.tsx', icon: '🟦' },
  { path: 'package.json', icon: '📦' },
  { path: '.github/workflows/ci.yml', icon: '⚙️' },
  { path: 'android/app/build.gradle', icon: '🤖' },
];
const starterCards = (): Card[] => [
  { id: makeId(), title: '1 · Wunsch', body: 'User beschreibt das gewünschte Produkt oder Feature in natürlicher Sprache.' },
  { id: makeId(), title: '2 · Repo lesen', body: 'Dateibaum, Struktur, Workflows und wichtige Dateien werden als Kontext genutzt.' },
  { id: makeId(), title: '3 · Produkt bauen', body: 'Der große Knopf erzeugt sofort eine interaktive Vorschau und ein Dateipaket.' },
  { id: makeId(), title: '4 · Agent Workspace', body: 'Explorer, Editor, Chat und Systemlog erscheinen wie in einer No-Code-IDE.' },
];

export default function ProductMagicApp() {
  const [repoUrl, setRepoUrl] = useState('https://github.com/OuroborosCollective/Wasd');
  const [accessKey, setAccessKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [blueprint, setBlueprint] = useState('Baue aus diesem Workflow eine klickbare Mini-App mit GitHub Explorer, Auto-Resolver, Living Preview und Agent Workspace.');
  const [cards, setCards] = useState<Card[]>(starterCards());
  const [selectedFile, setSelectedFile] = useState<FileItem>(demoFiles[0]);
  const [built, setBuilt] = useState(false);
  const [chatInput, setChatInput] = useState('Setze diesen Workflow als echtes Produkt um.');
  const [logs, setLogs] = useState<string[]>(['🚀 Sovereign Studio Auto-Resolver geladen.']);

  const generatedPackage = useMemo(() => JSON.stringify({ repoUrl, blueprint, cards, selectedFile: selectedFile.path }, null, 2), [repoUrl, blueprint, cards, selectedFile]);

  const log = (text: string) => setLogs((items) => [text, ...items].slice(0, 12));
  const buildProduct = () => {
    setBuilt(true);
    log('✨ Produkt lebt: Preview, Dateipaket und Agent-Workspace wurden erzeugt.');
  };
  const addCard = () => setCards((items) => [...items, { id: makeId(), title: 'Neues Modul', body: blueprint }]);
  const sendChat = () => {
    if (!chatInput.trim()) return;
    log(`🤖 Agent: Ich habe den Auftrag verstanden: ${chatInput}`);
    setChatInput('');
  };
  const downloadPackage = () => {
    const blob = new Blob([generatedPackage], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sovereign-product-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-screen overflow-hidden bg-stone-50 text-stone-900 font-sans flex flex-col">
      <header className="h-14 bg-white border-b border-stone-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-50">
        <div>
          <h1 className="text-sm font-bold tracking-tight">SOVEREIGN<span className="text-indigo-600">_STUDIO</span></h1>
          <div className="text-[9px] font-bold text-indigo-600 uppercase tracking-widest">Auto-Resolver Product Builder</div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => log('🧹 Workspace Cleanup vorbereitet.')} className="px-3 py-1.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-[10px] font-bold hover:bg-rose-100">🧹 CLEANUP</button>
          <button onClick={() => log('🔄 Demo Tree aktualisiert.')} className="px-3 py-1.5 bg-stone-100 border border-stone-200 rounded text-[10px] font-bold hover:bg-stone-200">🔄 REFRESH TREE</button>
        </div>
      </header>

      <div className="h-12 bg-stone-50 border-b border-stone-200 flex items-center justify-between px-4 shrink-0 text-xs overflow-x-auto gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-bold text-stone-500 uppercase text-[10px]">GitHub URL:</span>
          <input value={repoUrl} onChange={(event) => setRepoUrl(event.target.value)} className="text-xs px-2 py-1 border border-stone-300 rounded w-64 focus:outline-none focus:border-indigo-500 bg-white" />
          <button onClick={() => log(`📁 Repository verbunden: ${repoUrl}`)} className="px-3 py-1 bg-indigo-600 text-white font-bold rounded hover:bg-indigo-700 text-[10px] uppercase">Repo Laden</button>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <label className="flex items-center gap-2"><span className="font-bold text-stone-500 uppercase text-[10px]">GitHub PAT:</span><input value={accessKey} onChange={(event) => setAccessKey(event.target.value)} type="password" placeholder="nur im Feld" className="text-xs px-2 py-1 border border-stone-300 rounded w-40 focus:outline-none focus:border-indigo-500 bg-white" /></label>
          <label className="flex items-center gap-2"><span className="font-bold text-stone-500 uppercase text-[10px]">Gemini Key:</span><input value={geminiKey} onChange={(event) => setGeminiKey(event.target.value)} type="password" placeholder="optional" className="text-xs px-2 py-1 border border-stone-300 rounded w-40 focus:outline-none focus:border-indigo-500 bg-white" /></label>
        </div>
      </div>

      <main className="flex-1 flex overflow-hidden relative">
        <section className="flex flex-col w-[320px] shrink-0 border-r border-stone-200 bg-white">
          <div className="p-3 bg-indigo-50 border-b border-indigo-200 shrink-0 shadow-sm">
            <h3 className="text-[11px] font-black text-indigo-800 mb-1 flex justify-between items-center"><span>🔁 PRODUCT AUTO-RESOLVER</span><span className="px-2 py-0.5 rounded-full bg-indigo-200 text-indigo-800 text-[9px] uppercase">Bereit</span></h3>
            <p className="text-[10px] text-indigo-700 mb-2">Ziel: <span className="font-mono font-bold">Living Preview + Agent Workspace</span></p>
            <button onClick={buildProduct} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2 rounded text-[11px] font-bold uppercase shadow-sm flex items-center justify-center gap-2"><Rocket size={14}/> Produkt bauen</button>
          </div>

          <div className="p-3 bg-stone-50 border-b border-stone-200 shrink-0">
            <h3 className="text-[11px] font-bold text-stone-700 mb-2">⚡ ARCHITECT BLUEPRINT</h3>
            <textarea value={blueprint} onChange={(event) => setBlueprint(event.target.value)} rows={4} className="w-full p-2 text-[11px] border border-stone-300 rounded focus:outline-none focus:border-indigo-500 resize-none shadow-inner" />
            <div className="flex gap-2 mt-2">
              <button onClick={buildProduct} className="flex-1 bg-stone-800 hover:bg-black text-white py-1.5 rounded text-[11px] font-bold uppercase shadow-sm"><Wand2 size={13} className="inline mr-1"/>Generieren</button>
              <button onClick={addCard} className="shrink-0 bg-yellow-100 hover:bg-yellow-200 border border-yellow-300 text-yellow-800 py-1.5 px-3 rounded text-[11px] font-bold uppercase shadow-sm"><Plus size={13} className="inline mr-1"/>Modul</button>
            </div>
          </div>

          <div className="p-2 bg-indigo-50/50 border-b border-stone-200 flex items-center gap-2 shrink-0">
            <input placeholder="Wo ist die App-Logik? ✨" className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 shadow-inner" />
            <button onClick={() => log('✨ Smart Search Demo ausgeführt.')} className="bg-indigo-100 hover:bg-indigo-200 text-indigo-800 px-3 py-1.5 rounded text-[10px] font-bold uppercase shrink-0">✨ SUCHE</button>
          </div>

          <div className="flex-1 overflow-y-auto bg-white">
            {demoFiles.map((file) => <button key={file.path} onClick={() => { setSelectedFile(file); log(`📄 Datei gewählt: ${file.path}`); }} className={`w-full p-3 border-b border-stone-100 text-[13px] flex items-center gap-2 text-left hover:bg-stone-50 ${selectedFile.path === file.path ? 'bg-teal-50 text-teal-700 border-l-4 border-l-teal-600 font-semibold' : 'text-stone-600'}`}><span>{file.icon}</span><span className="truncate">{file.path}</span></button>)}
          </div>
        </section>

        <section className="flex-1 min-w-0 flex flex-col bg-stone-50">
          <div className="h-10 bg-stone-50 border-b border-stone-200 flex items-center gap-2 px-2 shrink-0 overflow-x-auto">
            <span className="text-[11px] font-mono text-stone-600 italic truncate mr-2 px-2 max-w-[220px]">{selectedFile.path}</span>
            {['REVIEW','TESTS','DOCS','CI/CD','README','THREAT MODEL'].map((label) => <button key={label} onClick={() => log(`✨ ${label} vorbereitet.`)} className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded hover:bg-indigo-200">✨ {label}</button>)}
          </div>

          <div className="flex-1 bg-stone-100/30 p-4 overflow-hidden flex flex-col">
            <div className="editor-bg flex-1 rounded-xl shadow-inner relative overflow-hidden flex flex-col bg-stone-950 font-mono">
              <div className="flex-1 overflow-auto p-3 text-[12px] text-stone-300 whitespace-pre leading-relaxed">
{`// ${selectedFile.path}\n// Sovereign Auto-Resolver Preview\n\nconst blueprint = ${JSON.stringify(blueprint, null, 2)};\n\nexport const generatedProduct = {\n  mode: 'living-preview',\n  repo: '${repoUrl}',\n  modules: ${cards.length},\n  ready: ${built}\n};`}
              </div>
            </div>
          </div>

          <div className="h-12 bg-white border-t border-stone-200 flex items-center px-4 gap-3 shrink-0">
            <span className="text-lg">🤖</span>
            <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') sendChat(); }} placeholder="Frag den Code-Agenten..." className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 bg-stone-50" />
            <button onClick={sendChat} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-[10px] font-bold uppercase shadow-sm"><Send size={13}/></button>
          </div>

          <div className="h-16 border-t border-indigo-200 px-4 flex items-center justify-between bg-indigo-50 shrink-0 gap-3">
            <div className="flex-1 min-w-0"><h4 className="text-[10px] font-black text-indigo-800 uppercase">PR-Queue: <span>{cards.length}</span> Module</h4><input value={built ? 'feat: generate sovereign product workspace' : ''} readOnly placeholder="Commit Nachricht..." className="w-full text-[10px] p-1 border border-indigo-200 rounded bg-white" /></div>
            <button onClick={() => log('🛡️ Push PR als Demo vorbereitet.')} className="shrink-0 px-6 py-2 bg-indigo-600 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">🛡️ PUSH PR</button>
          </div>
        </section>

        <section className="w-[350px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
          <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0"><div><span className="text-indigo-600">✨</span> SYSTEM LOG</div><button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600">Leeren</button></div>
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-white text-[11px]">
            {built && <div className="p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 shadow-sm"><strong><Eye size={13} className="inline mr-1"/>Living Product aktiv</strong><br/>{cards.map((card) => <button key={card.id} onClick={() => log(`▶ Modul gestartet: ${card.title}`)} className="mt-2 mr-2 px-2 py-1 rounded bg-white border border-emerald-200 text-[10px] font-bold">{card.title}</button>)}</div>}
            <div className="p-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-900 shadow-sm"><strong><Bot size={13} className="inline mr-1"/>No-Code Agent Oberfläche</strong><br/>Explorer, Editor, Chat, Queue und Systemlog sind in einem Arbeitsfenster verbunden.</div>
            {logs.map((entry, index) => <div key={`${entry}-${index}`} className="p-3 bg-stone-100 rounded-xl rounded-tl-none border border-stone-200 text-stone-700 shadow-sm break-words">{entry}</div>)}
          </div>
          <div className="border-t border-stone-200 p-3 bg-stone-50">
            <button onClick={downloadPackage} className="w-full bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2"><Download size={13}/> Produktpaket sichern</button>
          </div>
        </section>
      </main>
    </div>
  );
}
