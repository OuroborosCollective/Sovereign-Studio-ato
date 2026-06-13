import React from 'react';
import { Bot, CheckCircle, Loader2, Send } from 'lucide-react';
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
  isWorking?: boolean;
  agentMessage?: string;
  progress?: number;
  currentStepLabel?: string;
  nextStepLabel?: string;
  approvalConfirmed?: boolean;
}

export const MainContent: React.FC<MainContentProps> = ({
  workView, setWorkView, selectedFile, currentCode, pipelineState, settings,
  publishAndValidate, patchFromPipeline, mergeWhenGreen,
  chatInput, setChatInput, sendChat, cardsCount, fixLoops,
  isWorking,
  agentMessage,
  progress,
  currentStepLabel,
  nextStepLabel,
  approvalConfirmed = false
}) => {
  const red = pipelineState === 'failed' || pipelineState === 'blocked';
  const green = pipelineState === 'green';
  const yellow = pipelineState === 'planning' || pipelineState === 'generating' || pipelineState === 'validating' || pipelineState === 'fixing' || pipelineState === 'revalidating';
  const derivedWorking = isWorking ?? (pipelineState === 'validating' || pipelineState === 'planning' || pipelineState === 'generating' || pipelineState === 'fixing' || pipelineState === 'revalidating');
  const canApprove = green && !derivedWorking && !approvalConfirmed;
  const derivedMessage = approvalConfirmed
    ? 'Freigabe bestaetigt. Fertig - du musst nichts mehr suchen oder senden.'
    : agentMessage ?? ({
      idle: 'Bereit. Starte links den Auftrag.',
      planning: 'Auftrag uebernommen. Ich plane und schreibe den Code-Entwurf.',
      generating: 'Ich schreibe den sichtbaren Code-Entwurf.',
      validating: 'Ich pruefe aktiv. Bitte warten, ich haenge nicht.',
      failed: 'Pruefung fertig: Fehler gefunden. Ich arbeite weiter.',
      fixing: 'Ich wende den sichtbaren Fix an.',
      revalidating: 'Ich pruefe erneut. Bitte warten.',
      green: 'Alles gruen. Druecke jetzt den grossen Button: Freigabe bestaetigen.',
      blocked: 'Ich komme alleine nicht weiter. Bitte eingreifen.'
    } satisfies Record<PipelineState, string>)[pipelineState];
  const derivedProgress = progress ?? ({ idle: 0, planning: 10, generating: 25, validating: 45, failed: 60, fixing: 70, revalidating: 88, green: 100, blocked: 65 } satisfies Record<PipelineState, number>)[pipelineState];

  const handleChatSubmit = () => {
    if (green) {
      mergeWhenGreen();
      return;
    }
    sendChat();
  };

  return (
    <section className="flex-1 min-w-0 flex flex-col bg-stone-50 pb-20 md:pb-0">
      <div className="h-10 bg-stone-50 border-b border-stone-200 flex items-center gap-2 px-2 shrink-0 overflow-x-auto">
        <button onClick={() => setWorkView('editor')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'editor' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}>CHAT UND EDITOR</button>
        <button onClick={() => setWorkView('pipeline')} className={`px-2 py-1 text-[9px] font-bold rounded ${workView === 'pipeline' ? 'bg-stone-900 text-white' : 'bg-stone-100 text-stone-700'}`}>ANALYSE</button>
        <span className="text-[11px] font-mono text-stone-600 italic truncate px-2 max-w-[220px]">{selectedFile.path}</span>
      </div>

      <div className="flex-1 min-h-0 p-3 sm:p-4 overflow-hidden flex flex-col gap-3">
        <div className="rounded-2xl border border-indigo-200 bg-indigo-50 p-3 text-xs text-indigo-950 shadow-sm">
          <div className="flex gap-3">
            <div className={`h-10 w-10 rounded-2xl flex items-center justify-center shrink-0 ${derivedWorking ? 'bg-indigo-600 text-white animate-pulse' : approvalConfirmed ? 'bg-emerald-600 text-white' : 'bg-white text-indigo-700 border border-indigo-200'}`}>
              {derivedWorking ? <Loader2 size={20} className="animate-spin" /> : approvalConfirmed ? <CheckCircle size={20} /> : <Bot size={20} />}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 font-black">
                <span className={`w-2.5 h-2.5 rounded-full ${red ? 'bg-red-500 animate-pulse' : 'bg-stone-300'}`} />
                <span className={`w-2.5 h-2.5 rounded-full ${yellow ? 'bg-yellow-400 animate-pulse' : 'bg-stone-300'}`} />
                <span className={`w-2.5 h-2.5 rounded-full ${green ? 'bg-emerald-500 animate-pulse' : 'bg-stone-300'}`} />
                Agent Status
              </div>
              <p className="mt-1 mb-0 leading-relaxed">{derivedMessage}</p>
              <div className="mt-2 h-2 rounded-full bg-white border border-indigo-100 overflow-hidden">
                <div className={`h-full transition-all duration-700 ${derivedWorking ? 'animate-pulse bg-indigo-600' : approvalConfirmed ? 'bg-emerald-600' : 'bg-stone-400'}`} style={{ width: `${Math.max(4, Math.min(100, derivedProgress))}%` }} />
              </div>
              <div className="mt-1 text-[10px] font-bold text-indigo-700">
                {approvalConfirmed ? 'Freigabe bestaetigt. Vorgang abgeschlossen.' : derivedWorking ? 'Ich arbeite aktiv an deinem Auftrag. Bitte warten.' : green ? 'Jetzt den grossen Freigabe-Button druecken.' : 'Ein Schritt nach dem anderen. Kein Auto-Endloslauf.'}
              </div>
            </div>
          </div>
          {(currentStepLabel || nextStepLabel) && (
            <div className="mt-3 pt-3 border-t border-indigo-200 flex gap-4 text-[10px]">
              {currentStepLabel && (
                <div className="flex-1">
                  <span className="text-indigo-600 font-bold">Aktuell: </span>
                  <span className="text-indigo-800">{currentStepLabel}</span>
                </div>
              )}
              {nextStepLabel && (
                <div className="flex-1">
                  <span className="text-stone-600 font-bold">Danach: </span>
                  <span className="text-stone-800">{nextStepLabel}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {green && (
          <div className={`rounded-2xl border p-4 shadow-lg ${approvalConfirmed ? 'bg-emerald-50 border-emerald-300' : 'bg-white border-emerald-400 ring-2 ring-emerald-100'}`}>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-black uppercase tracking-wide text-emerald-800">Letzter Schritt</div>
                <h3 className="text-lg font-black text-stone-950 leading-tight">{approvalConfirmed ? 'Freigabe bestaetigt' : 'Freigabe bestaetigen'}</h3>
                <p className="text-xs text-stone-600 mt-1">
                  {approvalConfirmed
                    ? 'Alles erledigt. Du musst nicht nochmal auf Senden, Frei oder Pruefen druecken.'
                    : 'Druecke diesen grossen Button. Das blaue Senden-Symbol ist hierfuer nicht noetig.'}
                </p>
              </div>
              <button
                type="button"
                onClick={mergeWhenGreen}
                disabled={!canApprove}
                className="w-full sm:w-auto min-h-14 px-6 py-3 rounded-2xl bg-emerald-600 disabled:bg-emerald-200 text-white font-black text-sm uppercase shadow-lg shadow-emerald-100 active:scale-[0.98]"
                aria-label="Freigabe bestaetigen"
              >
                {approvalConfirmed ? 'Bestaetigt' : 'Freigabe bestaetigen'}
              </button>
            </div>
          </div>
        )}

        <div className="flex-1 min-h-[260px] rounded-xl shadow-inner overflow-hidden flex flex-col bg-stone-950 font-mono border border-stone-800">
          <div className="h-9 bg-stone-900 border-b border-stone-800 flex items-center gap-2 px-3 text-[10px] text-stone-400">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500"/>
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500"/>
            <span className="w-2.5 h-2.5 rounded-full bg-green-500"/>
            <span className="ml-2">Matrix File Editor · {derivedWorking ? 'arbeitet...' : approvalConfirmed ? 'freigegeben' : 'bereit'}</span>
          </div>
          <div className="flex-1 overflow-auto p-3 text-[12px] text-stone-300 whitespace-pre leading-relaxed">{currentCode.split('\n').map((line, index) => `${String(index + 1).padStart(3, ' ')} │ ${line}`).join('\n')}</div>
        </div>

        {workView === 'pipeline' && (
          <div className="bg-white border border-stone-200 rounded-xl shadow-sm p-3 text-xs text-stone-600">Sequenzieller Workflow: Auftrag fertig → Pruefen → bei Fehler Fixen → erneut Pruefen → Freigabe.</div>
        )}
      </div>

      <div className="h-12 bg-white border-t border-stone-200 flex items-center px-3 sm:px-4 gap-3 shrink-0">
        <span className="text-lg">Chat</span>
        <input
          value={chatInput}
          onChange={(event) => setChatInput(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') handleChatSubmit(); }}
          placeholder={green ? 'Freigabe oben bestaetigen - Senden ist nicht noetig' : 'Idee, Auftrag oder Frage eingeben'}
          className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded bg-stone-50"
        />
        <button
          disabled={(derivedWorking && !green) || approvalConfirmed}
          onClick={handleChatSubmit}
          aria-label={green ? 'Freigabe bestaetigen' : 'Nachricht senden'}
          title={green ? 'Auch dieses Symbol bestaetigt jetzt die Freigabe' : 'Nachricht senden'}
          className="bg-indigo-600 disabled:bg-stone-300 text-white px-4 py-1.5 rounded text-[10px] font-bold uppercase shadow-sm"
        >
          <Send size={13}/>
        </button>
      </div>

      <div className="sticky bottom-0 z-30 border-t border-indigo-200 px-3 sm:px-4 py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between bg-indigo-50 shrink-0 gap-3 shadow-[0_-8px_20px_rgba(79,70,229,0.08)]">
        <div className="flex-1 min-w-0">
          <h4 className="text-[10px] font-black text-indigo-800 uppercase">Auftrag: {cardsCount} Schritte · Fixlauf {fixLoops}/{settings.maxFixLoops}</h4>
          <input readOnly value={derivedMessage} className="w-full text-[10px] p-1 border border-indigo-200 rounded bg-white" />
        </div>
        <div className="grid grid-cols-3 gap-2 w-full sm:w-auto shrink-0">
          <button disabled={derivedWorking || green} onClick={publishAndValidate} className="px-3 py-2 bg-indigo-600 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase">Pruefen</button>
          <button disabled={derivedWorking || pipelineState !== 'failed'} onClick={patchFromPipeline} className="px-3 py-2 bg-amber-500 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase">Fix</button>
          <button disabled={!canApprove} onClick={mergeWhenGreen} className="px-3 py-2 bg-emerald-600 disabled:bg-stone-300 text-white rounded-lg font-bold text-[10px] uppercase">{approvalConfirmed ? 'Bestaetigt' : 'Freigabe'}</button>
        </div>
      </div>
    </section>
  );
};