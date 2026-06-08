import React from 'react';
import { Download } from 'lucide-react';
import { Card } from '../types';

interface LogSidebarProps {
  built: boolean;
  cards: Card[];
  log: (text: string) => void;
  logs: string[];
  setLogs: (logs: string[]) => void;
  downloadPackage: () => void;
}

export const LogSidebar: React.FC<LogSidebarProps> = ({ logs, setLogs, downloadPackage }) => {
  return (
    <section className="w-full md:w-[350px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
      <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0">
        <div>Log</div>
        <button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600">Leeren</button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-white text-[11px]">
        {logs.map((entry, index) => (
          <div key={`${entry}-${index}`} className={`p-3 rounded-xl rounded-tl-none border border-stone-200 text-stone-700 shadow-sm break-words ${index === 0 ? 'bg-indigo-50 animate-pulse' : 'bg-stone-100'}`}>{entry}</div>
        ))}
      </div>
      <div className="border-t border-stone-200 p-3 bg-stone-50">
        <button onClick={downloadPackage} className="w-full bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2"><Download size={13}/> Verlauf sichern</button>
      </div>
    </section>
  );
};
