import React from 'react';
import { AlertTriangle, Bot, CheckCircle, Loader2, Send } from 'lucide-react';
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
  isWorking: boolean;
  agentMessage: string;
  progress: number;
}

const lampClass = (active: boolean, color: string) =>
  `w-2.5 h-2.5 rounded-full ${active ? `${color} animate-pulse shadow-lg` : 'bg-stone-700'}`;

export const MainContent: React.FC<MainContentProps> = ({
  workView, setWorkView, selectedFile, currentCode, pipelineState, settings,
  publishAndValidate, patchFromPipeline, mergeWhenGreen,
  chatInput, setChatInput, sendChat, log, cardsCount, fixLoops,
  isWorking, agentMessage, progress
}) => {
  const isError = pipelineState === 'failed';
  const isGreen = pipelineState === 'green';

  return (
    <section className="flex-1 min-w-0 flex flex-col bg-stone-50">
      <div className="h-10 bg-stone-50 border-b border-stone-200 flex items-center gap-2 px-2 shrink-0 overflow-x-auto">
        <button onClick={() => setWorkView('editor')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'editor' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}>CHAT UND EDITOR</button>
        <button onClick={() => setWorkView('pipeline')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'pipeline' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}>ANALYSE</button>
        <span className="text-[11px] font-mono text-stone-600 italic truncate mr-2 px-2 max-w-[220px]">{selectedFile.path}</span>
        {['Planen','Pruefen','Fixen','Freigabe'].map((label) => <button key={label} onClick={() => log(`${label}: bereit.`)} className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold rounded hover:bg-indigo-200">{label}</button>)}
      </div>

      <div className="flex-1 bg-stone-100/30 p-3 sm:p-4 overflow-hidden flex flex-col gap-3">
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-950 shadow-sm">
          <div className="flex items-start gap-3">
            <div className={`mt-0.5 h-10 w-10 shrink-0 rounded-2xl flex items-center justify-center ${isWorking ? 'bg-indigo-600 text-white animate-pulse' : 'bg-white text-indigo-700 border border-indigo-200'}`}>
              {isWorking ? <Loader2 size={20} className="animate-spin"/> : <Bot size={20}/>} 
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={lampClass(isError, 'bg-red-500')} />
                <span className={lampClass(isWorking, 'bg-yellow-400')} />
                <span className={lampClass(isGreen, 'bg-emerald-500')} />
                <strong>Agent Status</strong>
              </div>
              <p className="m-0 leading-relaxed">{agentMessage}</p>
              <div className="mt-2 h-2 rounded-full bg-white border border-indigo-100 overflow-hidden">
                <div className={`h-full bg-indigo-600 transition-all duration-700 ${isWorking ? 'animate-pulse' : ''}`} style={{ width: `${Math.max(4, Math.min(100, progress))}%` }} />
              </div>
              <div className="mt-1 text-[10px] font-bold text-indigo-700">Fortschritt {progress}% · {isWorking ? 'Ich arbeite aktiv, bitte warten.' : 'Bereit fuer den naechsten manuellen Schritt.'}</div>
            </div>
          </div>
        </div>

        <div className="editor-bg flex-1 min-h-[260px] rounded-xl shadow-inner relative overflow-hidden flex flex-col bg-stone-950 font-mono border border-stone-800">
          <div className="h-9 bg-stone-900 border-b border-stone-800 flex items-center gap-2 px-3 text-[10px] text-stone-400">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500"/>
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500"/>
            <span className="w-2.5 h-2.5 rounded-full bg-green-500"/>
            <span className="ml-2">Matrix File Editor · Live Code · {isWorking ? 'arbeitet...' : 'bereit'}</span>
          </div>
          <div className="flex-1 overflow-auto p-3 text-[12px] text-stone-300 whitespace-pre leading-relaxed">
            {currentCode.split('\n').map((line, index) => `${String(index + 1).padStart(3, ' ')} │ ${line}`).join('\n')}
          </div>
        </div>

        {workView === 'pipeline' && (
          <div className="bg-white border border-stone-200 rounded-xl shadow-sm p-3">
            <h3 className="text-sm font-black text-stone-900 mb-2">Sequenzieller Workflow</h3>
            <p className="text-xs text-stone-500 mb-3">Kein Endlos-Springen: Erst wenn ein Schritt fertig ist, gibst du den naechsten frei.</p>
            <div className="grid grid-cols-4 gap-2">
              {[ ['publishing','1 Auftrag'], ['validating','2 Pruefung'], ['failed','3 Fix'], ['green','4 Gruen'] ].map(([state, label]) => (
                <div key={state} className={`p-2 rounded-xl border text-center text-[10px] font-black ${pipelineState === state ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-stone-50 text-stone-500 border-stone-200'}`}>{label}</div>
              ))}
            </div>
            {isError && <div className="mt-3 p-3 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs"><AlertTriangle size={14} className="inline mr-1"/> Fehler gefunden. Jetzt manuell Fixen druecken.</div>}
            {isGreen && <div className="mt-3 p-3 bg-green-50 border border-green-200 text-green-800 rounded-xl text-xs"><CheckCircle size={14} className="inline mr-1"/> Gruen. Freigabe kann bestaetigt werden.</div>}
          </div>
        )}
      </div>

      <div className="h-12 bg-white border-t border-stone-200 flex items-center px-3 sm:px-4 gap-3 shrink-0">
        <span className="text-lg">Chat</span>
        <input value={chatInput} onChange={(event) => setChatInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') sendChat(); }} placeholder="Idee, Auftrag oder Frage eingeben" className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 bg-stone-50" />
        <button disabled={isWorking} onClick={sendChat} className="bg-indigo-600 disabled:bg-stone-300 hover:bg-indigo-700 text-white px-4 py-1.5 rounded text-[10px] font-bold uppercase shadow-sm"><Send size={13}/></button>
      </div>

      <div className="border-t border-indigo-200 px-3 sm:px-4 py-2 flex items-center justify-between bg-indigo-50 shrink-0 gap-3">
        <div className="flex-1 min-w-0"><h4 className="text-[10px] font-black text-indigo-800 uppercase">Auftrag: <span>{cardsCount}</span> Schritte · Fixlauf {fixLoops}/{settings.maxFixLoops}</h4><input readOnly value={agentMessage} className="w-full text-[10px] p-1 border border-indigo-200 rounded bg-white" /></div>
        <div className="flex gap-2 shrink-0">
          <button disabled={isWorking} onClick={publishAndValidate} className="px-4 py-2 bg-indigo-600 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">Pruefen</button>
          <button disabled={isWorking} onClick={patchFromPipeline} className="px-4 py-2 bg-amber-500 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">Fix</button>
          <button disabled={isWorking} onClick={mergeWhenGreen} className="px-4 py-2 bg-emerald-600 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase shadow-sm">Frei</button>
        </div>
      </div>
    </section>
  );
};
