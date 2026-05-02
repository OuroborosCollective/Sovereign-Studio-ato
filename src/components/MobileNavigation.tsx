import React from 'react';
import { Folder, Code2, MessageSquare } from 'lucide-react';

interface MobileNavigationProps {
  activeTab: 'explorer' | 'editor' | 'chat';
  setActiveTab: (tab: 'explorer' | 'editor' | 'chat') => void;
}

export function MobileNavigation({ activeTab, setActiveTab }: MobileNavigationProps) {
  return (
    <nav className="lg:hidden h-14 bg-white border-t border-stone-200 flex items-center justify-around shrink-0 z-50 shadow-[0_-2px_10px_rgba(0,0,0,0.05)] absolute bottom-0 left-0 w-full select-none">
      <button 
        onClick={() => setActiveTab('explorer')} 
        className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'explorer' ? 'text-indigo-600' : 'text-stone-400'}`}
      >
        <Folder size={18} />
        <span className="text-[9px] font-bold uppercase tracking-wider">Planung</span>
      </button>
      <button 
        onClick={() => setActiveTab('editor')} 
        className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'editor' ? 'text-indigo-600' : 'text-stone-400'}`}
      >
        <Code2 size={18} />
        <span className="text-[9px] font-bold uppercase tracking-wider">Code</span>
      </button>
      <button 
        onClick={() => setActiveTab('chat')} 
        className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'chat' ? 'text-indigo-600' : 'text-stone-400'}`}
      >
        <MessageSquare size={18} />
        <span className="text-[9px] font-bold uppercase tracking-wider">Log</span>
      </button>
    </nav>
  );
}