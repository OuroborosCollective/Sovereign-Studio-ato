import React from 'react';
import { Shield, Sparkles, Key, ExternalLink } from 'lucide-react';
import { ProjectSettings } from '../types';
import { LLM_PROVIDERS, type UserApiKeys } from './UserKeyManager';

interface SettingsModalProps {
  repoUrl: string;
  setRepoUrl: (val: string) => void;
  accessKey: string;
  setAccessKey: (val: string) => void;
  geminiKey: string;
  setGeminiKey: (val: string) => void;
  settings: ProjectSettings;
  setSettings: (val: ProjectSettings) => void;
  setShowSettings: (val: boolean) => void;
  userApiKeys: UserApiKeys;
  setUserApiKeys: (keys: UserApiKeys) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  repoUrl, setRepoUrl, accessKey, setAccessKey, geminiKey, setGeminiKey, 
  settings, setSettings, setShowSettings, userApiKeys, setUserApiKeys
}) => {
  const handleKeyChange = (providerId: string, value: string) => {
    setUserApiKeys({ ...userApiKeys, [providerId]: value || undefined });
  };

  const openProviderDocs = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const getProviderKey = (providerId: string): string => {
    return userApiKeys[providerId as keyof UserApiKeys] || '';
  };

  const activeProviders = Object.values(userApiKeys).filter(v => v).length;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden border border-stone-200 flex flex-col">
        <div className="p-4 bg-indigo-600 text-white flex items-center justify-between">
          <h3 className="text-sm font-black uppercase tracking-widest flex items-center gap-2">
            <Shield size={16}/> Einstellungen
          </h3>
          <button onClick={() => setShowSettings(false)} className="text-indigo-200 hover:text-white font-bold text-lg" aria-label="Schließen">×</button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* API Keys Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-black text-stone-500 uppercase flex items-center gap-2">
                <Key size={14}/> LLM API-Keys
                {activeProviders > 0 && (
                  <span className="bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full text-[10px]">
                    {activeProviders} aktiv
                  </span>
                )}
              </h4>
            </div>
            
            <div className="bg-emerald-50 p-3 rounded-xl border border-emerald-100 text-[11px] text-emerald-900">
              🌐 Kostenlose Routen (mlvoca, pollinations) funktionieren ohne Keys. Optionale Keys ermöglichen Backup bei Limit.
            </div>

            {/* Provider Key Inputs */}
            <div className="space-y-3">
              {LLM_PROVIDERS.filter(p => p.id !== 'mlvoca').map((provider) => (
                <div key={provider.id} className="flex items-start gap-3 p-3 bg-stone-50 rounded-xl border border-stone-200">
                  <span className="text-xl mt-0.5">{provider.icon}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] font-bold text-stone-700">{provider.name}</label>
                      <button
                        onClick={() => openProviderDocs(provider.docsUrl)}
                        className="text-[10px] text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                      >
                        <ExternalLink size={10}/> API-Key erstellen
                      </button>
                    </div>
                    <input
                      type="password"
                      value={getProviderKey(provider.id)}
                      onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                      placeholder={provider.keyPlaceholder}
                      className="w-full p-2 text-[11px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none font-mono"
                    />
                    <p className="text-[9px] text-stone-500 mt-1">{provider.freeTier}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Repository & Access Section */}
          <div className="space-y-4 pt-4 border-t border-stone-200">
            <div>
              <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">GitHub Repository</label>
              <input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">GitHub Schreib-Key optional</label>
                <input type="password" value={accessKey} onChange={(e) => setAccessKey(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="nur fuer private Repos" />
              </div>
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Gemini Key (optional)</label>
                <input type="password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="leer lassen ist ok" />
              </div>
            </div>
          </div>

          {/* Project Settings */}
          <div className="space-y-3 pt-4 border-t border-stone-200">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Package Manager</label>
                <select value={settings.packageManager} onChange={(e) => setSettings({ ...settings, packageManager: e.target.value as any })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none">
                  <option value="auto">Auto-Detect</option>
                  <option value="pnpm">pnpm</option>
                  <option value="npm">npm</option>
                  <option value="bun">bun</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Projektart</label>
                <select value={settings.repoMode} onChange={(e) => setSettings({ ...settings, repoMode: e.target.value as any })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none">
                  <option value="monorepo">Monorepo</option>
                  <option value="single">Single Repo</option>
                </select>
              </div>
            </div>
            <div className="bg-indigo-50 p-3 rounded-xl border border-indigo-100">
              <h4 className="text-[10px] font-black text-indigo-800 uppercase flex items-center gap-1 mb-1"><Sparkles size={12}/> Arbeitsweise</h4>
              <textarea value={settings.specialization} onChange={(e) => setSettings({ ...settings, specialization: e.target.value })} rows={2} className="w-full p-2 text-[10px] bg-white border border-indigo-200 rounded-lg focus:ring-1 focus:ring-indigo-500 outline-none resize-none" />
            </div>
          </div>
        </div>
        
        <div className="p-4 bg-stone-50 border-t border-stone-200">
          <button onClick={() => setShowSettings(false)} className="w-full bg-stone-900 text-white py-3 rounded-xl text-[11px] font-black uppercase shadow-lg hover:bg-black transition-all">
            Speichern & Schließen
          </button>
        </div>
      </div>
    </div>
  );
};
