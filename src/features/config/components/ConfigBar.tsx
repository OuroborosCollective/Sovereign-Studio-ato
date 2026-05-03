import React, { useState } from 'react';
import { 
  Settings, 
  X, 
  Sliders, 
  Save, 
  RefreshCw, 
  Database, 
  Monitor, 
  ShieldCheck
} from 'lucide-react';
import { useConfig } from '../../../hooks/useConfig';
import { ConfigState } from '../types';

export const ConfigBar: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const { 
    config, 
    updateField, 
    saveConfig, 
    resetToDefaults, 
    isDirty 
  } = useConfig();

  const handleSave = async () => {
    await saveConfig();
    setTimeout(() => setIsOpen(false), 300);
  };

  const handleChange = (key: keyof ConfigState, value: string | number | boolean) => {
    updateField(key, value);
  };

  return (
    <React.Fragment>
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
          onClick={() => setIsOpen(false)}
        ></div>
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
              <span>General Appearance</span>
            </div>
            
            <div className="space-y-3">
              <label className="block">
                <span className="text-sm font-medium text-slate-700">Theme</span>
                <select 
                  value={config.theme}
                  onChange={(e) => handleChange('theme', e.target.value as ConfigState['theme'])}
                  className="mt-1.5 w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all"
                >
                  <option value="light">Light Mode</option>
                  <option value="dark">Dark Mode</option>
                  <option value="system">System Preference</option>
                </select>
              </label>

              <div className="flex items-center justify-between py-2">
                <span className="text-sm font-medium text-slate-700">Auto Save Changes</span>
                <button 
                  onClick={() => handleChange('autoSave', !config.autoSave)}
                  className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${
                    config.autoSave ? 'bg-indigo-600' : 'bg-slate-200'
                  }`}
                >
                  <span 
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      config.autoSave ? 'translate-x-6' : 'translate-x-1'
                    }`} 
                  ></span>
                </button>
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
              <Database size={14} />
              <span>Backend Connectivity</span>
            </div>
            
            <div className="space-y-4">
              <label className="block">
                <span className="text-sm font-medium text-slate-700">API Endpoint</span>
                <input 
                  type="text"
                  value={config.apiEndpoint}
                  onChange={(e) => handleChange('apiEndpoint', e.target.value)}
                  placeholder="https://..."
                  className="mt-1.5 w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 outline-none transition-all"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-slate-700">Retry Attempts</span>
                <input 
                  type="range"
                  min="0"
                  max="10"
                  value={config.maxRetries}
                  onChange={(e) => handleChange('maxRetries', parseInt(e.target.value, 10))}
                  className="mt-2 w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                />
                <div className="flex justify-between text-[10px] text-slate-400 mt-1 font-medium">
                  <span>0</span>
                  <span>Current: {config.maxRetries}</span>
                  <span>10</span>
                </div>
              </label>
            </div>
          </section>

          <section className="space-y-4">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest">
              <ShieldCheck size={14} />
              <span>Diagnostics</span>
            </div>
            
            <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
              <div className="flex items-center justify-between">
                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-amber-900">Debug Mode</span>
                  <span className="text-xs text-amber-700/70">Enables verbose logging</span>
                </div>
                <button 
                  onClick={() => handleChange('debugMode', !config.debugMode)}
                  className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none ${
                    config.debugMode ? 'bg-amber-500' : 'bg-slate-300'
                  }`}
                >
                  <span 
                    className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                      config.debugMode ? 'translate-x-6' : 'translate-x-1'
                    }`} 
                  ></span>
                </button>
              </div>
            </div>
          </section>
        </div>

        <footer className="p-6 border-t border-slate-100 bg-slate-50/80 flex flex-col gap-3">
          <button
            onClick={handleSave}
            disabled={!isDirty}
            className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg font-semibold text-sm transition-all shadow-sm ${
              isDirty 
                ? 'bg-indigo-600 text-white hover:bg-indigo-700 hover:shadow-md' 
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <Save size={16} />
            Apply Changes
          </button>
          
          <button
            onClick={resetToDefaults}
            className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg font-medium text-sm text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            <RefreshCw size={14} />
            Reset Defaults
          </button>
        </footer>
      </aside>
    </React.Fragment>
  );
};

export default ConfigBar;