import React, { useEffect, useState } from 'react';
import { Shield, Sparkles, Key, ExternalLink, X, Eye, EyeOff, CircleX } from 'lucide-react';
import type { ProjectSettings } from '../types';
import { defaultSettings } from '../constants';
import { LLM_PROVIDERS, type UserApiKeys } from './UserKeyManager';

interface SettingsModalProps {
  repoUrl: string;
  setRepoUrl: (val: string) => void;
  accessKey: string;
  setAccessKey: (val: string) => void;
  geminiKey: string;
  setGeminiKey: (val: string) => void;
  settings?: ProjectSettings;
  setSettings?: (val: ProjectSettings) => void;
  setShowSettings: (val: boolean) => void;
  userApiKeys: UserApiKeys;
  setUserApiKeys: (keys: UserApiKeys) => void;
}

type UserApiKeyId = keyof UserApiKeys;

const USER_API_KEY_IDS: ReadonlySet<string> = new Set<UserApiKeyId>([
  'pollinations',
  'groq',
  'huggingface',
  'together',
  'openrouter',
  'gemini',
]);

function isUserApiKeyId(providerId: string): providerId is UserApiKeyId {
  return USER_API_KEY_IDS.has(providerId);
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  repoUrl, setRepoUrl, accessKey, setAccessKey, geminiKey, setGeminiKey,
  settings = defaultSettings, setSettings = () => undefined, setShowSettings, userApiKeys, setUserApiKeys
}) => {
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowSettings(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setShowSettings]);

  const handleKeyChange = (providerId: string, value: string) => {
    if (!isUserApiKeyId(providerId)) return;
    setUserApiKeys({ ...userApiKeys, [providerId]: value || undefined });
  };

  const toggleShowKey = (providerId: string) => {
    setShowKeys((prev) => ({ ...prev, [providerId]: !prev[providerId] }));
  };

  const openProviderDocs = (url: string) => {
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const getProviderKey = (providerId: string): string => {
    return isUserApiKeyId(providerId) ? userApiKeys[providerId] || '' : '';
  };

  const activeProviders = Object.values(userApiKeys).filter(v => v).length;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden border border-stone-200 flex flex-col" role="dialog" aria-modal="true" aria-labelledby="settings-title">
        <div className="p-4 bg-indigo-600 text-white flex items-center justify-between">
          <h3 id="settings-title" className="text-sm font-black uppercase tracking-widest flex items-center gap-2">
            <Shield size={16}/> Einstellungen
          </h3>
          <button
            onClick={() => setShowSettings(false)}
            className="text-indigo-200 hover:text-white transition-colors p-1"
            aria-label="Schließen"
            title="Schließen"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
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
                    <div className="relative">
                      <input
                        type={showKeys[provider.id] ? 'text' : 'password'}
                        value={getProviderKey(provider.id)}
                        onChange={(e) => handleKeyChange(provider.id, e.target.value)}
                        placeholder={provider.keyPlaceholder}
                        className="w-full p-2 pr-16 text-[11px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none font-mono"
                        aria-label={`${provider.name} API-Key`}
                      />
                      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                        {getProviderKey(provider.id) && (
                          <button
                            type="button"
                            onClick={() => handleKeyChange(provider.id, '')}
                            className="text-stone-400 hover:text-stone-600 p-1"
                            aria-label="Key löschen"
                            title="Key löschen"
                          >
                            <CircleX size={14} />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => toggleShowKey(provider.id)}
                          className="text-stone-400 hover:text-stone-600 p-1"
                          aria-label={showKeys[provider.id] ? 'Key verbergen' : 'Key anzeigen'}
                          title={showKeys[provider.id] ? 'Key verbergen' : 'Key anzeigen'}
                        >
                          {showKeys[provider.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>
                    <p className="text-[9px] text-stone-500 mt-1">{provider.freeTier}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-4 pt-4 border-t border-stone-200">
            <div>
              <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">
                GitHub Repository <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <input
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  className="w-full p-2 pr-10 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                  aria-label="GitHub Repository URL"
                  required
                />
                {repoUrl && (
                  <button
                    type="button"
                    onClick={() => setRepoUrl('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 p-1"
                    aria-label="Eingabe löschen"
                    title="Eingabe löschen"
                  >
                    <CircleX size={14} />
                  </button>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">GitHub Schreib-Key (optional)</label>
                <div className="relative">
                  <input
                    type={showKeys['github'] ? 'text' : 'password'}
                    value={accessKey}
                    onChange={(e) => setAccessKey(e.target.value)}
                    className="w-full p-2 pr-16 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="nur für private Repos"
                    aria-label="GitHub Schreib-Key"
                  />
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                    {accessKey && (
                      <button
                        type="button"
                        onClick={() => setAccessKey('')}
                        className="text-stone-400 hover:text-stone-600 p-1"
                        aria-label="Key löschen"
                        title="Key löschen"
                      >
                        <CircleX size={14} />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleShowKey('github')}
                      className="text-stone-400 hover:text-stone-600 p-1"
                      aria-label={showKeys['github'] ? 'Key verbergen' : 'Key anzeigen'}
                      title={showKeys['github'] ? 'Key verbergen' : 'Key anzeigen'}
                    >
                      {showKeys['github'] ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Gemini Key (optional)</label>
                <div className="relative">
                  <input
                    type={showKeys['gemini'] ? 'text' : 'password'}
                    value={geminiKey}
                    onChange={(e) => setGeminiKey(e.target.value)}
                    className="w-full p-2 pr-16 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                    placeholder="leer lassen ist ok"
                    aria-label="Gemini API-Key"
                  />
                  <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                    {geminiKey && (
                      <button
                        type="button"
                        onClick={() => setGeminiKey('')}
                        className="text-stone-400 hover:text-stone-600 p-1"
                        aria-label="Key löschen"
                        title="Key löschen"
                      >
                        <CircleX size={14} />
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleShowKey('gemini')}
                      className="text-stone-400 hover:text-stone-600 p-1"
                      aria-label={showKeys['gemini'] ? 'Key verbergen' : 'Key anzeigen'}
                      title={showKeys['gemini'] ? 'Key verbergen' : 'Key anzeigen'}
                    >
                      {showKeys['gemini'] ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3 pt-4 border-t border-stone-200">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Package Manager</label>
                <select value={settings.packageManager} onChange={(e) => setSettings({ ...settings, packageManager: e.target.value as ProjectSettings['packageManager'] })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none" aria-label="Package Manager auswählen">
                  <option value="auto">Auto-Detect</option>
                  <option value="pnpm">pnpm</option>
                  <option value="npm">npm</option>
                  <option value="bun">bun</option>
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-black text-stone-500 uppercase mb-1">Projektart</label>
                <select value={settings.repoMode} onChange={(e) => setSettings({ ...settings, repoMode: e.target.value as ProjectSettings['repoMode'] })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none" aria-label="Projektart auswählen">
                  <option value="monorepo">Monorepo</option>
                  <option value="single">Single Repo</option>
                </select>
              </div>
            </div>
            <div className="bg-indigo-50 p-3 rounded-xl border border-indigo-100">
              <h4 className="text-[10px] font-black text-indigo-800 uppercase flex items-center gap-1 mb-1"><Sparkles size={12}/> Arbeitsweise</h4>
              <textarea value={settings.specialization} onChange={(e) => setSettings({ ...settings, specialization: e.target.value })} rows={2} className="w-full p-2 text-[10px] bg-white border border-indigo-200 rounded-lg focus:ring-1 focus:ring-indigo-500 outline-none resize-none" aria-label="Arbeitsweise beschreiben" />
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
