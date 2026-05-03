import React from 'react';
import { Folder, Code2, MessageSquare } from 'lucide-react';

interface MobileNavigationProps {
  activeTab: 'explorer' | 'editor' | 'chat';
  setActiveTab: (tab: 'explorer' | 'editor' | 'chat') => void;
}

export function MobileNavigation({ activeTab, setActiveTab }: MobileNavigationProps) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 h-16 bg-white/70 backdrop-blur-md border-t border-white/20 flex items-center justify-around shrink-0 z-[100] shadow-[0_-8px_32px_rgba(0,0,0,0.08)] select-none pb-safe">
      <button 
        onClick={() => setActiveTab('explorer')} 
        className={`flex flex-col items-center justify-center gap-1 w-full h-full transition-all duration-300 ${activeTab === 'explorer' ? 'text-indigo-600' : 'text-stone-400 hover:text-stone-600'}`}
      >
        <div className={`p-1.5 rounded-xl transition-colors ${activeTab === 'explorer' ? 'bg-indigo-50' : 'bg-transparent'}`}>
          <Folder size={20} strokeWidth={activeTab === 'explorer' ? 2.5 : 2} />
        </div>
        <span className="text-[10px] font-bold uppercase tracking-tight">Planung</span>
      </button>
      
      <button 
        onClick={() => setActiveTab('editor')} 
        className={`flex flex-col items-center justify-center gap-1 w-full h-full transition-all duration-300 ${activeTab === 'editor' ? 'text-indigo-600' : 'text-stone-400 hover:text-stone-600'}`}
      >
        <div className={`p-1.5 rounded-xl transition-colors ${activeTab === 'editor' ? 'bg-indigo-50' : 'bg-transparent'}`}>
          <Code2 size={20} strokeWidth={activeTab === 'editor' ? 2.5 : 2} />
        </div>
        <span className="text-[10px] font-bold uppercase tracking-tight">Code</span>
      </button>
      
      <button 
        onClick={() => setActiveTab('chat')} 
        className={`flex flex-col items-center justify-center gap-1 w-full h-full transition-all duration-300 ${activeTab === 'chat' ? 'text-indigo-600' : 'text-stone-400 hover:text-stone-600'}`}
      >
        <div className={`p-1.5 rounded-xl transition-colors ${activeTab === 'chat' ? 'bg-indigo-50' : 'bg-transparent'}`}>
          <MessageSquare size={20} strokeWidth={activeTab === 'chat' ? 2.5 : 2} />
        </div>
        <span className="text-[10px] font-bold uppercase tracking-tight">Log</span>
      </button>
    </nav>
  );
}