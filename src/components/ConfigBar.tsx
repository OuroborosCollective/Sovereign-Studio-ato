import React from 'react';
import { Key } from 'lucide-react';

interface ConfigBarProps {
  repoUrl: string;
  setRepoUrl: (url: string) => void;
  handleRepoChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  ghPat: string;
  handleGhPatChange: (val: string) => void;
  geminiKey: string;
  handleGeminiKeyChange: (val: string) => void;
}

export const ConfigBar: React.FC<ConfigBarProps> = ({
  repoUrl, setRepoUrl, handleRepoChange, ghPat, handleGhPatChange, geminiKey, handleGeminiKeyChange
}) => {
  return (
    <div className="bg-stone-100 p-2 border-b border-stone-200 flex items-center justify-between gap-4 text-xs shadow-sm z-10 shrink-0">
      <input
        type="text"
        value={repoUrl}
        onChange={handleRepoChange}
        placeholder="GitHub Repo (z.B. User/Repo)"
        className="px-2 py-1 bg-white border border-stone-300 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500 w-48 font-mono text-[10px]"
      />
      <div className="flex gap-2 w-full max-w-sm ml-auto items-center">
        <Key size={12} className="text-stone-400 shrink-0" />
        <input
          type="password"
          value={ghPat}
          onChange={(e) => handleGhPatChange(e.target.value)}
          placeholder="GitHub PAT (optional)"
          className="flex-1 px-2 py-1 bg-white border border-stone-300 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono text-[10px]"
        />
        <input
          type="password"
          value={geminiKey}
          onChange={(e) => handleGeminiKeyChange(e.target.value)}
          placeholder="Gemini API Key"
          className="flex-1 px-2 py-1 bg-white border border-stone-300 rounded focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono text-[10px]"
        />
      </div>
    </div>
  );
};
