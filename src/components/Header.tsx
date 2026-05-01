import React from 'react';
import { RefreshCw, Trash2, Info } from 'lucide-react';

interface HeaderProps {
  loadingTree: boolean;
  setShowPrivacy: (show: boolean) => void;
  handleCleanup: () => void;
  fetchRepoTree: () => void;
}

export function Header({ loadingTree, setShowPrivacy, handleCleanup, fetchRepoTree }: HeaderProps) {
  return (
    <header className="h-14 bg-white/80 backdrop-blur-xl border-b border-stone-200/60 flex items-center justify-between px-4 shrink-0 shadow-[0_4px_30px_rgba(0,0,0,0.03)] z-50">
      <div>
        <h1 className="text-sm font-bold tracking-tight">SOVEREIGN<span className="text-indigo-600">_STUDIO</span></h1>
        <div className="text-[9px] font-bold text-indigo-600 uppercase tracking-widest">Auto-Resolver v3.0.0</div>
      </div>
      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[10px] font-black tracking-wider shadow-sm mr-2 transition-all hover:shadow-md hover:bg-emerald-100/80 cursor-default" title="Hybrid API Canvas Auto-Auth verbunden">
           <div className="relative flex h-2 w-2">
             <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
             <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
           </div>
           CANVAS AUTO-AUTH
        </div>
        <button onClick={() => setShowPrivacy(true)} className="px-3 py-1.5 bg-stone-100 border border-stone-200 text-stone-600 rounded text-[10px] font-bold hover:bg-stone-200 transition-colors flex items-center gap-1">
           <Info size={12} /> DATENSCHUTZ
        </button>
        <button onClick={handleCleanup} className="px-3 py-1.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-[10px] font-bold hover:bg-rose-100 transition-colors flex items-center gap-1">
          <Trash2 size={12} /> CLEANUP
        </button>
        <button onClick={fetchRepoTree} disabled={loadingTree} className="px-3 py-1.5 bg-stone-100 border border-stone-200 rounded text-[10px] font-bold hover:bg-stone-200 transition-colors flex items-center gap-1 disabled:opacity-50">
          <RefreshCw size={12} className={loadingTree ? "animate-spin" : ""} /> {loadingTree ? "LADEN..." : "REFRESH"}
        </button>
      </div>
    </header>
  );
}
