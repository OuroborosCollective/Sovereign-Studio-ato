import React from 'react';
import { Github, Key, Shield, LogIn } from 'lucide-react';

interface ConfigBarProps {
  repoUrl: string;
  setRepoUrl: (url: string) => void;
  handleRepoChange: () => void;
  ghPat: string;
  handleGhPatChange: (val: string) => void;
  geminiKey: string;
  handleGeminiKeyChange: (val: string) => void;
  handleGoogleLogin: () => void;
}

export function ConfigBar({
  repoUrl,
  setRepoUrl,
  handleRepoChange,
  ghPat,
  handleGhPatChange,
  geminiKey,
  handleGeminiKeyChange,
  handleGoogleLogin
}: ConfigBarProps) {
  return (
    <div className="h-12 bg-stone-50 border-b border-stone-200 flex items-center justify-between px-4 shrink-0 text-xs overflow-x-auto gap-4 hide-scrollbar">
      <div className="flex items-center gap-2 shrink-0">
        <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1">
          <Github size={12} /> Repo:
        </span>
        <input
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          className="text-xs px-2 py-1 border border-stone-300 rounded w-64 focus:outline-none focus:border-indigo-500 bg-white"
        />
        <button
          onClick={handleRepoChange}
          className="px-3 py-1 bg-indigo-600 text-white font-bold rounded hover:bg-indigo-700 transition-colors text-[10px] uppercase"
        >
          Laden
        </button>
      </div>

      <div
        className="flex items-center gap-3 shrink-0"
        title="Datenschutz-Hinweis: APIs-Schlüssel werden ausschließlich lokal auf deinem Gerät im sicheren Speicher gespeichert und nur für direkte, sichere HTTPS-Verbindungen zu GitHub und Google APIs verwendet."
      >
        <div className="flex items-center gap-2">
          <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1 cursor-help">
            <Shield size={12} /> GH PAT:
          </span>
          <input
            type="password"
            value={ghPat}
            onChange={(e) => handleGhPatChange(e.target.value)}
            placeholder="ghp_..."
            className="text-xs px-2 py-1 border border-stone-300 rounded w-40 focus:outline-none focus:border-indigo-500 bg-white"
          />
        </div>

        <div className="flex items-center gap-2 border-l border-stone-200 pl-3">
          <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1 cursor-help">
            <Key size={12} /> Gemini:
          </span>
          <input
            type="password"
            value={geminiKey}
            onChange={(e) => handleGeminiKeyChange(e.target.value)}
            placeholder="API-Schlüssel..."
            className="text-xs px-2 py-1 border border-stone-300 rounded w-32 focus:outline-none focus:border-indigo-500 bg-white"
          />
          <span className="text-[10px] text-stone-400 font-bold uppercase mx-1">oder</span>
          <button
            onClick={handleGoogleLogin}
            className="flex items-center gap-1.5 px-3 py-1 bg-white border border-stone-300 text-stone-700 font-bold rounded hover:bg-stone-50 hover:border-stone-400 transition-all text-[10px] uppercase shadow-sm active:scale-95"
          >
            <LogIn size={12} className="text-red-500" />
            Google Login
          </button>
        </div>
      </div>
    </div>
  );
}