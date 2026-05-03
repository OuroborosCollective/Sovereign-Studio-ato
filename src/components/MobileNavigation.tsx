import React from 'react';
import { Folder, Code2, MessageSquare } from 'lucide-react';

interface MobileNavigationProps {
  activeTab: 'explorer' | 'editor' | 'chat';
  setActiveTab: (tab: 'explorer' | 'editor' | 'chat') => void;
}

export function MobileNavigation({ activeTab, setActiveTab }: MobileNavigationProps) {
  const tabs = [
    { id: 'explorer' as const, icon: Folder, label: 'Planung' },
    { id: 'editor' as const, icon: Code2, label: 'Code' },
    { id: 'chat' as const, icon: MessageSquare, label: 'Log' }
  ];

  return (
    <div className="lg:hidden absolute bottom-6 left-1/2 -translate-x-1/2 w-[calc(100%-2.5rem)] max-w-sm z-[100] px-1 pointer-events-none">
      <nav className="flex items-center justify-around h-16 bg-white/40 backdrop-blur-2xl border border-white/50 rounded-2xl shadow-[0_12px_40px_rgba(0,0,0,0.15)] pointer-events-auto overflow-hidden ring-1 ring-black/5">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex flex-col items-center justify-center w-full h-full transition-all duration-500 ease-out outline-none tap-highlight-transparent ${
                isActive ? 'text-indigo-600' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {isActive && (
                <div className="absolute inset-x-2 inset-y-2 bg-white/60 rounded-xl shadow-sm transition-all duration-500" />
              )}
              
              <div className="relative flex flex-col items-center gap-0.5">
                <div className={`p-1 transition-transform duration-300 ${isActive ? 'scale-110' : 'scale-100'}`}>
                  <Icon 
                    size={20} 
                    strokeWidth={isActive ? 2.5 : 2} 
                    className="transition-all duration-300"
                  />
                </div>
                <span className={`text-[9px] font-black uppercase tracking-[0.1em] transition-all duration-300 ${
                  isActive ? 'opacity-100 translate-y-0' : 'opacity-70 -translate-y-0.5'
                }`}>
                  {tab.label}
                </span>
              </div>

              {isActive && (
                <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-8 h-1 bg-indigo-600 rounded-t-full" />
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}