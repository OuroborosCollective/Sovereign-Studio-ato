import React, { useState } from 'react';
import { 
  Settings, 
  X, 
  Sliders, 
  RefreshCw, 
  Monitor,
  Cpu,
  Zap,
  Layers,
  Activity
} from 'lucide-react';
import { useConfig } from '../../../hooks/useConfig';

export interface AppConfig {
  canvas: {
    resolutionScale: number;
    fpsLimit: number;
    showStats: boolean;
    bloomEnabled: boolean;
  };
  gemini: {
    temperature: number;
    topP: number;
    maxTokens: number;
    model: 'gemini-1.5-pro' | 'gemini-1.5-flash';
  };
  [key: string]: any;
}

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

  const handleCanvasUpdate = (updates: Partial<AppConfig['canvas']>) => {
    updateConfig({
      canvas: { ...config.canvas, ...updates }
    });
  };

  const handleGeminiUpdate = (updates: Partial<AppConfig['gemini']>) => {
    updateConfig({
      gemini: { ...config.gemini, ...updates }
    });
  };

  return (
    <React.Fragment>
      {isOpen && (
        <div 
          className="fixed inset-0 bg-slate-950/40 backdrop-blur-sm z-40 transition-opacity"
          onClick={() => setIsOpen(false)}
        >
          <span className="sr-only">Close Overlay</span>
        </div>
      )}

      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed right-6 bottom-6 p-4 bg-indigo-600 text-white rounded-2xl shadow-xl shadow-indigo-500/20 hover:bg-indigo-700 transition-all hover:scale-110 z-30 group"
          aria-label="Open Configuration"
        >
          <Settings size={24} className="group-hover:rotate-90 transition-transform duration-700" />
        </button>
      )}

      <aside
        className={`fixed top-0 right-0 h-full w-85 bg-white border-l border-slate-200 shadow-2xl z-50 transform transition-transform duration-500 cubic-bezier(0.4, 0, 0.2, 1) flex flex-col ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="px-6 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-600 text-white rounded-xl shadow-md shadow-indigo-200">
              <Sliders size={20} />
            </div>
            <div>
              <h2 className="font-bold text-slate-900 leading-none">System Engine</h2>
              <span className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Parameters</span>
            </div>
          </div>
          <button 
            onClick={() => setIsOpen(false)}
            className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-all"
          >
            <X size={20} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-10">
          {/* Canvas Engine Section */}
          <section className="space-y-5">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">
              <Monitor size={14} className="text-indigo-500" />
              <span>Canvas Visuals</span>
            </div>
            
            <div className="space-y-6">
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                    <Layers size={14} className="text-slate-400" /> Resolution Scale
                  </label>
                  <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600">{config.canvas.resolutionScale}x</span>
                </div>
                <input 
                  type="range" min="0.5" max="2" step="0.25"
                  value={config.canvas.resolutionScale}
                  onChange={(e) => handleCanvasUpdate({ resolutionScale: parseFloat(e.target.value) })}
                  className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                />
              </div>

              <div className="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2 cursor-pointer">
                  <Activity size={14} className="text-slate-400" /> Performance Stats
                </label>
                <button 
                  onClick={() => handleCanvasUpdate({ showStats: !config.canvas.showStats })}
                  className={`w-10 h-5 rounded-full transition-colors relative ${config.canvas.showStats ? 'bg-indigo-600' : 'bg-slate-300'}`}
                >
                  <div className={`absolute top-1 left-1 w-3 h-3 bg-white rounded-full transition-transform ${config.canvas.showStats ? 'translate-x-5' : 'translate-x-0'}`} />
                </button>
              </div>
            </div>
          </section>

          {/* Gemini Generator Section */}
          <section className="space-y-5">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-widest border-b border-slate-100 pb-2">
              <Zap size={14} className="text-amber-500" />
              <span>Gemini Intelligence</span>
            </div>

            <div className="space-y-6">
              <div className="space-y-3">
                <label className="text-sm font-medium text-slate-700 flex items-center gap-2">
                  <Cpu size={14} className="text-slate-400" /> Model Variant
                </label>
                <select 
                  value={config.gemini.model}
                  onChange={(e) => handleGeminiUpdate({ model: e.target.value as any })}
                  className="w-full p-2.5 bg-white border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition-shadow"
                >
                  <option value="gemini-1.5-pro">Gemini 1.5 Pro (Precision)</option>
                  <option value="gemini-1.5-flash">Gemini 1.5 Flash (Speed)</option>
                </select>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <label className="text-sm font-medium text-slate-700">Temperature</label>
                  <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600">{config.gemini.temperature}</span>
                </div>
                <input 
                  type="range" min="0" max="1" step="0.1"
                  value={config.gemini.temperature}
                  onChange={(e) => handleGeminiUpdate({ temperature: parseFloat(e.target.value) })}
                  className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <p className="text-[10px] text-slate-400 italic">Higher values result in more creative outputs.</p>
              </div>
            </div>
          </section>
        </div>

        <footer className="p-6 border-t border-slate-100 bg-slate-50/80 flex flex-col gap-3">
          <button
            onClick={resetToDefaults}
            className="group w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl font-bold text-sm text-slate-600 bg-white border border-slate-200 hover:bg-slate-900 hover:text-white transition-all shadow-sm active:scale-95"
          >
            <RefreshCw size={14} className="group-hover:rotate-180 transition-transform duration-500" />
            <span>Reset Engine Defaults</span>
          </button>
          <div className="flex justify-center">
            <span className="text-[9px] text-slate-400 font-medium tracking-tighter">SOVEREIGN STUDIO DESIGN-CODER V1.0</span>
          </div>
        </footer>
      </aside>
    </React.Fragment>
  );
};

export default ConfigBar;