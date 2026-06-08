import React from 'react';
import { Eye, Bot, Download } from 'lucide-react';
import { Card } from '../types';

interface LogSidebarProps {
  built: boolean;
  cards: Card[];
  log: (text: string) => void;
  logs: string[];
  setLogs: (logs: string[]) => void;
  downloadPackage: () => void;
}

export const LogSidebar: React.FC<LogSidebarProps> = ({
  built, cards, log, logs, setLogs, downloadPackage
}) => {
  return (
    <section className="w-[350px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
      <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0"><div>History und Analyse</div><button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600">Leeren</button></div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-white text-[11px]">
        {built && (
          <div className="p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-900 shadow-sm">
            <strong><Eye size={13} className="inline mr-1"/>Auftrag aktiv</strong><br/>
            <span>Planung, Generierung, Analyse und Workflow-Pruefung laufen sichtbar.</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {cards.map((card) => (
                <button key={card.id} onClick={() => log(`Schritt geoeffnet: ${card.title}`)} className="px-2 py-1 rounded bg-white border border-emerald-200 text-[10px] font-bold">{card.title}</button>
              ))}
            </div>
          </div>
        )}
        <div className="p-3 rounded-xl border border-indigo-200 bg-indigo-50 text-indigo-900 shadow-sm">
          <strong><Bot size={13} className="inline mr-1"/>Einfacher Ablauf</strong><br/>
          Links Datei und Auftrag, Mitte Chat und Editor, rechts Verlauf und verstaendliche Fehleranalyse.
        </div>
        {logs.map((entry, index) => (
          <div key={`${entry}-${index}`} className="p-3 bg-stone-100 rounded-xl rounded-tl-none border border-stone-200 text-stone-700 shadow-sm break-words">{entry}</div>
        ))}
      </div>
      <div className="border-t border-stone-200 p-3 bg-stone-50">
        <button onClick={downloadPackage} className="w-full bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2"><Download size={13}/> Verlauf sichern</button>
      </div>
    </section>
  );
};
