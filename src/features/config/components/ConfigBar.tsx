import React, { useState } from 'react';
import { 
  Settings, 
  X, 
  Sliders, 
  RefreshCw, 
  Monitor
} from 'lucide-react';
import { useConfig } from '../../../hooks/useConfig';

export interface AppConfig {
  [key: string]: any;
}

export type ConfigState = AppConfig;

export const ConfigBar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const { 
    config, 
    updateConfig, 
    resetToDefaults, 
    isLoaded 
  } = useConfig();

  if (!isLoaded) {
    return null;
  }

  const handleUpdate = (updates: Partial<AppConfig>) => {
    updateConfig(updates);
  };

  return (
    <React.Fragment>
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
          onClick={() => setIsOpen(false)}
        >
          <span className="sr-only">Close Overlay</span>
        </div>
      )}

      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed right-6 bottom-6 p-3 bg-indigo-600 text-white rounded-full shadow-lg hover:bg-indigo-700 transition-all hover:scale-110 z-30 group"
          aria-label="Open Configuration"
        >
          <Settings size={24} className="group-hover:rotate-90 transition-transform duration-500" />
        </button>
      )}

      <aside
        className={`fixed top-0 right-0 h-full w-80 bg-white border-l border-slate-200 shadow-2xl z-50 transform transition-transform duration-300 ease-in-out flex flex-col ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-indigo-100 text-indigo-600 rounded-lg">
              <Sliders size={18} />
            </div>
            <h2 className="font-bold text-slate-800 tracking-tight">Configuration</h2>
          </div>
          <button 
            onClick={() => setIsOpen(false)}
            className="p-1 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-md transition-colors"
          >
            <X size={20} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-8">
          <section className="space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
              <Monitor size={14} />
              <span>General Settings</span>
            </div>
            
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-100">
              <p className="text-sm text-slate-500 text-center italic">
                No configurable options available.
              </p>
            </div>
          </section>
        </div>

        <footer className="p-6 border-t border-slate-100 bg-slate-50/80 flex flex-col gap-3">
          <button
            onClick={resetToDefaults}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-semibold text-sm text-slate-600 bg-white border border-slate-200 hover:bg-slate-50 hover:text-slate-800 transition-all shadow-sm"
          >
            <RefreshCw size={14} />
            <span>Reset Defaults</span>
          </button>
        </footer>
      </aside>
    </React.Fragment>
  );
};

export default ConfigBar;