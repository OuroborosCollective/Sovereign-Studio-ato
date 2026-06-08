import React from 'react';
import { Download, Trash2 } from 'lucide-react';

interface LogSidebarProps {
  logs: string[];
  setLogs: (logs: string[]) => void;
  downloadPackage: () => void;
}

export const LogSidebar: React.FC<LogSidebarProps> = ({ logs, setLogs, downloadPackage }) => {
  return (
    <section className="w-full md:w-[350px] shrink-0 border-l border-stone-200 bg-white flex flex-col">
      <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center justify-between shrink-0">
        <div>Log</div>
        <button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600 flex items-center gap-1">
          <Trash2 size={12} /> Leeren
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-2 bg-white text-[11px]">
        {logs.map((entry, index) => (
          <div
            key={`${entry}-${index}`}
            className={`p-3 rounded-xl rounded-tl-none border text-stone-700 shadow-sm break-words transition-all duration-300 ${
              index === 0
                ? 'bg-indigo-50 border-indigo-200 animate-[pulse_2s_ease-in-out_infinite]'
                : 'bg-stone-100 border-stone-200'
            }`}
          >
            {entry}
          </div>
        ))}
        {logs.length === 0 && (
          <div className="text-center text-stone-400 py-8 text-[10px]">
            Noch keine Log-Eintraege.
          </div>
        )}
      </div>
      <div className="border-t border-stone-200 p-3 bg-stone-50">
        <button
          onClick={downloadPackage}
          className="w-full bg-stone-900 text-white py-2 rounded-lg text-[10px] font-black uppercase flex items-center justify-center gap-2 hover:bg-black transition-colors"
        >
          <Download size={13} /> Verlauf sichern
        </button>
      </div>
    </section>
  );
};
