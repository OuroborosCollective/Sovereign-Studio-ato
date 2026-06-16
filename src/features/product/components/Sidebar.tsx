import React from 'react';
import { FileItem, ProjectSettings } from '../types';
import { demoFiles } from '../constants';
import { Rocket, Wand2, Plus, Settings } from 'lucide-react';

interface SidebarProps {
  settings: ProjectSettings;
  buildProduct: () => void;
  blueprint: string;
  setBlueprint: (val: string) => void;
  addCard: () => void;
  log: (text: string) => void;
  selectedFile: FileItem;
  setSelectedFile: (file: FileItem) => void;
  setWorkView: (view: any) => void;
  repoUrl: string;
  setRepoUrl: (url: string) => void;
  setShowSettings: (show: boolean) => void;
  isWorking?: boolean;
}

const IDEA_CHIPS = [
  'README + Update History',
  'CI Fehleranalyse',
  'Android Release Check',
  'Workflow Auto-Fix',
  'Dokumentation + Tabellen',
  'Release Notes generieren',
];

export const Sidebar: React.FC<SidebarProps> = ({
  settings, buildProduct, blueprint, setBlueprint, addCard, log, selectedFile, setSelectedFile, setWorkView,
  repoUrl, setRepoUrl, setShowSettings, isWorking
}) => {
  const handleChipClick = (chip: string) => {
    setBlueprint(chip);
    log(`Idee ausgewaehlt: ${chip}`);
  };

  return (
    <section className="w-full md:w-64 shrink-0 border-r border-stone-200 bg-white flex flex-col">
      <div className="p-3 bg-indigo-50 border-b border-indigo-100 shrink-0">
        <h2 className="text-[11px] font-black text-indigo-900 mb-1 uppercase tracking-tighter">GitHub Repository</h2>
        <input
          type="text"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          placeholder="https://github.com/user/repo"
          className="w-full p-2 text-[10px] border border-indigo-200 rounded focus:outline-none focus:border-indigo-500 bg-white shadow-inner"
        />
        <div className="flex items-center justify-between mt-2">
          <p className="text-[9px] text-indigo-700 flex-1">PAT Token optional in Einstellungen</p>
          <button
            onClick={() => setShowSettings(true)}
            className="text-indigo-700 hover:text-indigo-900 p-1"
            title="Einstellungen oeffnen"
            aria-label="Einstellungen oeffnen"
          >
            <Settings size={16} />
          </button>
        </div>
      </div>

      <div className="p-4 bg-stone-50 border-b border-stone-200 shrink-0">
        <p className="text-[10px] text-stone-600 mb-2">Profil: <span className="font-mono font-bold">{settings.repoMode}/{settings.packageManager}/{settings.linter}</span></p>
        <button
          onClick={buildProduct}
          disabled={isWorking}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:bg-stone-400 text-white py-2 rounded text-[11px] font-bold uppercase shadow-sm flex items-center justify-center gap-2 active:scale-95 transition-all"
        >
          <Rocket size={14}/> Auftrag starten
        </button>
      </div>

      <div className="p-3 bg-stone-50 border-b border-stone-200 shrink-0">
        <h3 className="text-[11px] font-bold text-stone-700 mb-2">Idee oder Auftrag</h3>
        <textarea
          value={blueprint}
          onChange={(event) => setBlueprint(event.target.value)}
          rows={4}
          className="w-full p-2 text-[11px] border border-stone-300 rounded focus:outline-none focus:border-indigo-500 resize-none shadow-inner"
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={buildProduct}
            disabled={isWorking}
            className="flex-1 bg-stone-800 hover:bg-black disabled:bg-stone-400 text-white py-1.5 rounded text-[11px] font-bold uppercase shadow-sm"
          >
            <Wand2 size={13} className="inline mr-1"/>Uebernehmen
          </button>
          <button
            onClick={addCard}
            className="shrink-0 bg-yellow-100 hover:bg-yellow-200 border border-yellow-300 text-yellow-800 py-1.5 px-3 rounded text-[11px] font-bold uppercase shadow-sm"
          >
            <Plus size={13} className="inline mr-1"/>Notiz
          </button>
        </div>
        
        <div className="mt-3">
          <p className="text-[10px] font-bold text-stone-600 mb-2">Idee-Fabrik:</p>
          <div className="flex flex-wrap gap-1.5">
            {IDEA_CHIPS.map((chip) => (
              <button
                key={chip}
                onClick={() => handleChipClick(chip)}
                className="border border-indigo-200 rounded-full bg-indigo-50 text-indigo-700 px-2 py-1 text-[9px] font-bold hover:bg-indigo-100 transition-colors"
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
        
        <p className="text-[9px] text-stone-500 mt-2">Fuer echte GitHub-Schreibaktionen: PAT Token im Zahnrad eintragen.</p>
      </div>

      <div className="p-2 bg-indigo-50/50 border-b border-stone-200 flex items-center gap-2 shrink-0">
        <input placeholder="Datei suchen" className="flex-1 text-[11px] p-1.5 border border-stone-300 rounded focus:outline-none focus:border-indigo-500 shadow-inner" />
        <button onClick={() => log('Dateisuche vorbereitet.')} className="bg-indigo-100 hover:bg-indigo-200 text-indigo-800 px-3 py-1.5 rounded text-[10px] font-bold uppercase shrink-0">Suche</button>
      </div>

      <div className="flex-1 overflow-y-auto bg-white">
        {demoFiles.map((file) => (
          <button
            key={file.path}
            onClick={() => { setSelectedFile(file); setWorkView('editor'); log(`Datei gewaehlt: ${file.path}`); }}
            className={`w-full p-3 border-b border-stone-100 text-[13px] flex items-center gap-2 text-left hover:bg-stone-50 ${selectedFile.path === file.path ? 'bg-teal-50 text-teal-700 border-l-4 border-l-teal-600 font-semibold' : 'text-stone-600'}`}
          >
            <span>{file.icon}</span>
            <span className="truncate">{file.path}</span>
          </button>
        ))}
      </div>
    </section>
  );
};
