import React from 'react';
import { Settings, X, Save, RefreshCw, Sliders } from 'lucide-react';

interface ConfigBarProps {
  isOpen: boolean;
  onClose: () => void;
  config: Record<string, any>;
  onChange: (key: string, value: any) => void;
  onSave: () => void;
  onReset: () => void;
}

export const ConfigBar: React.FC<ConfigBarProps> = ({
  isOpen,
  onClose,
  config,
  onChange,
  onSave,
  onReset,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-80 bg-white border-l border-slate-200 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
      <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80 backdrop-blur-sm sticky top-0">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-50 text-blue-600 rounded-lg">
            <Settings className="w-5 h-5" />
          </div>
          <h2 className="font-bold text-slate-800 tracking-tight">Configuration</h2>
        </div>
        <button
          onClick={onClose}
          className="p-2 hover:bg-slate-200 rounded-full transition-all active:scale-95"
          aria-label="Close configuration"
        >
          <X className="w-5 h-5 text-slate-500" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-8">
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-400 uppercase tracking-wider">
            <Sliders className="w-3 h-3" />
            General Settings
          </div>
          
          <div className="space-y-5">
            {Object.entries(config).map(([key, value]) => (
              <div key={key} className="group">
                <label className="block text-sm font-semibold text-slate-700 mb-2 transition-colors group-hover:text-blue-600 capitalize">
                  {key.replace(/([A-Z])/g, ' $1').trim()}
                </label>
                
                {typeof value === 'boolean' ? (
                  <div className="flex items-center">
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={(e) => onChange(key, e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-100 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                  </div>
                ) : typeof value === 'number' ? (
                  <input
                    type="number"
                    value={value}
                    onChange={(e) => onChange(key, Number(e.target.value))}
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none transition-all"
                  />
                ) : (
                  <input
                    type="text"
                    value={value}
                    onChange={(e) => onChange(key, e.target.value)}
                    className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none transition-all"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="p-5 border-t border-slate-100 bg-slate-50/80 backdrop-blur-sm flex gap-3">
        <button
          onClick={onSave}
          className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white px-4 py-2.5 rounded-xl font-semibold text-sm transition-all shadow-lg shadow-blue-500/20 active:scale-[0.98]"
        >
          <Save className="w-4 h-4" />
          Apply Changes
        </button>
        <button
          onClick={onReset}
          className="flex items-center justify-center px-3 py-2.5 text-slate-600 bg-white border border-slate-200 hover:bg-slate-100 rounded-xl transition-all active:scale-95"
          title="Reset to default"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default ConfigBar;