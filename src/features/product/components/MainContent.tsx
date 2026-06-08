import React from 'react';
import { Code2, RefreshCw, AlertTriangle, CheckCircle, Send } from 'lucide-react';
import { FileItem, WorkView, PipelineState, ProjectSettings } from '../types';

interface MainContentProps {
  workView: WorkView;
  setWorkView: (view: WorkView) => void;
  selectedFile: FileItem;
  currentCode: string;
  pipelineState: PipelineState;
  settings: ProjectSettings;
  publishAndValidate: () => void;
  patchFromPipeline: () => void;
  mergeWhenGreen: () => void;
  chatInput: string;
  setChatInput: (val: string) => void;
  sendChat: () => void;
  log: (text: string) => void;
  cardsCount: number;
  fixLoops: number;
}

export const MainContent: React.FC<MainContentProps> = ({
  workView, setWorkView, selectedFile, currentCode, pipelineState, settings,
  publishAndValidate, patchFromPipeline, mergeWhenGreen,
  chatInput, setChatInput, sendChat, log, cardsCount, fixLoops
}) => {
  return (
    <section className="flex-1 min-w-0 flex flex-col bg-stone-50">
      <div className="h-10 bg-stone-50 border-b border-stone-200 flex items-center gap-2 px-2 shrink-0 overflow-x-auto">
        <button onClick={() => setWorkView('editor')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'editor' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}><Code2 size={11} className="inline mr-1"/>CHAT UND EDITOR</button>
        <button onClick={() => setWorkView('pipeline')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'pipeline' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}><RefreshCw size={11} className="inline mr-1"/>ANALYSE</button>
        <span className="text-[11px] font-mono text-stone-600 italic truncate mr-2 px-2 max-w-[220px]">{selectedFile.path}</span>
        {['Planen','Generieren','Pruefen','Fixen','Freigabe'].map((label) => <button key={label} onClick={() => log(`${label}: Schritt vorbereitet.`)} className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded hover:bg-indigo-200">{label}</button>)}
      </div>

      {workView === 'editor' ? (
        <div className="flex-1 bg-stone-100/30 p-4 overflow-hidden flex flex-col gap-3">
          <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-900">
            Mitte aktiv: Nach Auftrag-Start siehst du hier Chat, Datei-Editor und Live-Status. Bei Fehlern startet der sichtbare Fix genau hier.
          </div>
          <div className="editor-bg flex-1 rounded-xl shadow-inner relative overflow-hidden flex flex-col bg-stone-950 font-mono border border-stone-800">
            <div className="h-8 bg-stone-900 border-b border-stone-800 flex items-center gap-2 px-3 text-[10px] text-stone-400"><span className="w-2 h-2 rounded-full bg-red-500"/><span className="w-2 h-2 rounded-full bg-yellow-500"/><span className="w-2 h-2 rounded-full bg-green-500"/><span className="ml-2">Matrix File Editor · live zusehen</span></div>
            <div className="flex-1 overflow-auto p-3 text-[12px] text-stone-300 whitespace-pre leading-relaxed">
              {currentCode.split('\n').map((line, index) => `${String(index + 1).padStart(3, ' ')} │ ${line}`).join('\n')}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 bg-stone-100/30 p-4 overflow-y-auto">
          <div className="bg-white border border-stone-200 rounded-xl shadow-sm p-4">
            <h3 className="text-sm font-black text-stone-900 mb-2">Analyse und Workflow-Pruefung</h3>
            <p className="text-xs text-stone-500 mb-4">Ich erklaere verstaendlich, ob alles ok ist. Wenn Workflows gruen sind, darfst du bestaetigen. Bei Fehlern springe ich zurueck in den Editor und starte Fixes.</p>
            <div className="grid grid-cols-4 gap-2 mb-4">
              {[ ['publishing','1 Auftrag'], ['validating','2 Pruefung'], ['failed','3 Fix'], ['green','4 Fertig'] ].map(([state, label]) => (
                <div key={state} className={`p-3 rounded-xl border text-center text-[10px] font-black ${pipelineState === state ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-stone-50 text-stone-500 border-stone-200'}`}>{label}</div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={publishAndValidate} className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-[10px] font-black uppercase">Pruefung starten</button>
              <button onClick={patchFromPipeline} className="px-4 py-2 bg-amber-100 text-amber-800 border border-amber-200 rounded-lg text-[10px] font-black uppercase">Fix sichtbar starten</button>
              <button onClick={mergeWhenGreen} className="px-4 py-2 bg-green-600 text-white rounded-lg text-[10px] font-black uppercase">Freigabe bestaetigen</button>
            </div>
            {pipelineState === 'failed' && <div className="mt-4 p-3 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs"><AlertTriangle size={14} className="inline mr-1"/> Fehler gefunden. Die Ansicht geht zurueck in den Editor und der Fix wird sichtbar erzeugt.</div>}
            {pipelineState === 'green' && <div className="mt-4 p-3 bg-green-50 border border-green-200 text-green-800 rounded-xl text-xs"><CheckCircle size={14} className="inline mr-1"/> Alles gruen. Der naechste Schritt braucht deine Bestaetigung.</div>}
          </div>
        </div>
      )}

      <div className="h-12 bg-white border-t border-stone-200 flex items-center px-4 gap-3 shrink-0">
        <span className="text-lg">Chat</span>
        <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') sendChat(); }} placeholder="Idee, Auftrag oder Frage eingeben" className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 bg-stone-50" />
        <button onClick={sendChat} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-[10px] font-bold uppercase shadow-sm"><Send size={13}/></button>
      </div>

      <div className="h-16 border-t border-indigo-200 px-4 flex items-center justify-between bg-indigo-50 shrink-0 gap-3">
        <div className="flex-1 min-w-0"><h4 className="text-[10px] font-black text-indigo-800 uppercase">Auftrag: <span>{cardsCount}</span> Schritte · Fixlauf {fixLoops}/{settings.maxFixLoops}</h4><input readOnly placeholder="Status und naechste Aktion..." className="w-full text-[10px] p-1 border border-indigo-200 rounded bg-white" /></div>
        <button onClick={publishAndValidate} className="shrink-0 px-6 py-2 bg-indigo-600 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">Pruefen</button>
      </div>
    </section>
  );
};
