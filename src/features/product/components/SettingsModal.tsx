import React from 'react';
import { Shield, Sparkles } from 'lucide-react';
import { ProjectSettings } from '../types';

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
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  repoUrl, setRepoUrl, accessKey, setAccessKey, geminiKey, setGeminiKey, settings, setSettings, setShowSettings
}) => {
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden border border-stone-200">
        <div className="p-4 bg-indigo-600 text-white flex items-center justify-between">
          <h3 className="text-sm font-black uppercase tracking-widest flex items-center gap-2"><Shield size={16}/> Einstellungen</h3>
          <button onClick={() => setShowSettings(false)} className="text-indigo-200 hover:text-white font-bold text-lg" aria-label="Schließen">×</button>
        </div>
        <div className="p-6 space-y-4">
          <div>
            <label htmlFor="settings-repo-url" className="block text-[10px] font-black text-stone-500 uppercase mb-1">GitHub Repository</label>
            <input id="settings-repo-url" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="settings-access-key" className="block text-[10px] font-black text-stone-500 uppercase mb-1">GitHub Schreib-Key optional</label>
              <input id="settings-access-key" type="password" value={accessKey} onChange={(e) => setAccessKey(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="nur fuer private Repos oder Schreiben" />
            </div>
            <div>
              <label htmlFor="settings-ai-key" className="block text-[10px] font-black text-stone-500 uppercase mb-1">AI Key optional</label>
              <input id="settings-ai-key" type="password" value={geminiKey} onChange={(e) => setGeminiKey(e.target.value)} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none" placeholder="leer lassen ist ok" />
            </div>
          </div>
          <div className="bg-emerald-50 p-3 rounded-xl border border-emerald-100 text-[11px] text-emerald-900">
            Free Route zuerst: mlvoca und Pollinations. Eigene Keys sind nur Bonus, nicht Pflicht.
          </div>
          <div className="grid grid-cols-2 gap-3 pt-2">
            <div>
              <label htmlFor="settings-package-manager" className="block text-[10px] font-black text-stone-500 uppercase mb-1">Package Manager</label>
              <select id="settings-package-manager" value={settings.packageManager} onChange={(e) => setSettings({ ...settings, packageManager: e.target.value as any })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none">
                <option value="auto">Auto-Detect</option>
                <option value="pnpm">pnpm</option>
                <option value="npm">npm</option>
                <option value="bun">bun</option>
              </select>
            </div>
            <div>
              <label htmlFor="settings-repo-mode" className="block text-[10px] font-black text-stone-500 uppercase mb-1">Projektart</label>
              <select id="settings-repo-mode" value={settings.repoMode} onChange={(e) => setSettings({ ...settings, repoMode: e.target.value as any })} className="w-full p-2 text-[12px] border border-stone-200 rounded-lg outline-none">
                <option value="monorepo">Monorepo</option>
                <option value="single">Single Repo</option>
              </select>
            </div>
          </div>
          <div className="bg-indigo-50 p-3 rounded-xl border border-indigo-100 mt-2">
            <label htmlFor="settings-specialization" className="block text-[10px] font-black text-indigo-800 uppercase flex items-center gap-1 mb-1"><Sparkles size={12}/> Arbeitsweise</label>
            <textarea id="settings-specialization" value={settings.specialization} onChange={(e) => setSettings({ ...settings, specialization: e.target.value })} rows={2} className="w-full p-2 text-[10px] bg-white border border-indigo-200 rounded-lg focus:ring-1 focus:ring-indigo-500 outline-none resize-none" />
          </div>
        </div>
        <div className="p-4 bg-stone-50 border-t border-stone-200">
          <button onClick={() => setShowSettings(false)} className="w-full bg-stone-900 text-white py-2 rounded-xl text-[11px] font-black uppercase shadow-lg hover:bg-black transition-all">Speichern</button>
        </div>
      </div>
    </div>
  );
};
