import React from 'react';
import { Settings, FolderTree, Sparkles } from 'lucide-react';
import { useProductMagic } from './features/product/hooks/useProductMagic';
import { SettingsModal } from './features/product/components/SettingsModal';
import { Sidebar } from './features/product/components/Sidebar';
import { MainContent } from './features/product/components/MainContent';
import { LogSidebar } from './features/product/components/LogSidebar';

export type RepoFile = {
  path: string;
  type: 'blob' | 'tree';
  size?: number;
};

export function loadFromStorage(key: string, fallback = ''): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function saveToStorage(key: string, value: string) {
  try {
    if (value.trim()) {
      localStorage.setItem(key, value.trim());
    } else {
      localStorage.removeItem(key);
    }
  } catch {
    // localStorage is optional in embedded/restricted WebViews.
  }
}

export const parseGithubRepoUrl = (value: string): { owner: string; repo: string } | null => {
  const match = value.match(/github\.com\/([^/\s]+)\/([^/\s#?]+)/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/, '') };
};

export async function fetchRepoTree(
  owner: string,
  repo: string,
  branch: string,
  token: string
): Promise<RepoFile[]> {
  const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
  if (token.trim()) headers.Authorization = `Bearer ${token.trim()}`;

  const response = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/git/trees/${branch}?recursive=1`,
    { headers }
  );

  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`GitHub API ${response.status}: ${text || response.statusText}`);
  }

  const data = await response.json();
  const treeData: any[] = data.tree ?? [];
  const files: RepoFile[] = [];

  for (const f of treeData) {
    if (f.type === 'blob' || f.type === 'tree') {
      files.push({ path: f.path, type: f.type, size: f.size });
      if (files.length >= 250) break;
    }
  }

  return files;
}

function MobileTabs({ mobilePane, setMobilePane, isWorking }: { mobilePane: string; setMobilePane: (pane: 'auftrag' | 'live' | 'log') => void; isWorking: boolean }) {
  return (
    <nav className="fixed bottom-2 left-2 right-2 z-50 grid grid-cols-3 gap-1 p-1.5 bg-black/90 rounded-2xl shadow-2xl md:hidden">
      {(['auftrag', 'live', 'log'] as const).map((pane) => (
        <button
          key={pane}
          onClick={() => setMobilePane(pane)}
          disabled={isWorking && pane !== mobilePane}
          className={`py-2.5 px-2 rounded-xl text-[11px] font-black uppercase transition-colors ${
            mobilePane === pane ? 'bg-indigo-600 text-white' : 'bg-stone-700 text-stone-300'
          }`}
        >
          {pane === 'auftrag' ? 'Auftrag' : pane === 'live' ? 'Live' : 'Log'}
        </button>
      ))}
    </nav>
  );
}

export default function ProductMagicApp() {
  const {
    repoUrl, setRepoUrl,
    accessKey, setAccessKey,
    geminiKey, setGeminiKey,
    blueprint, setBlueprint,
    cards,
    selectedFile, setSelectedFile,
    built,
    chatInput, setChatInput,
    logs, setLogs,
    workView, setWorkView,
    pipelineState,
    fixLoops,
    showSettings, setShowSettings,
    settings, setSettings,
    currentCode,
    log,
    buildProduct,
    addCard,
    sendChat,
    downloadPackage,
    publishAndValidate,
    patchFromPipeline,
    mergeWhenGreen,
    isWorking,
    agentMessage,
    progress,
    mobilePane, setMobilePane,
    currentStepLabel,
    nextStepLabel,
    approvalConfirmed
  } = useProductMagic();

  return (
    <div className="flex flex-col h-screen bg-stone-100 text-stone-900 font-sans selection:bg-indigo-100 selection:text-indigo-900">
      <header className="h-12 bg-white border-b border-stone-200 flex items-center justify-between px-4 shrink-0 shadow-sm z-10">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center shadow-indigo-200 shadow-lg"><Sparkles size={16} className="text-white" /></div>
          <h1 className="text-[13px] font-black tracking-tighter uppercase flex items-center gap-2">Sovereign Studio <span className="text-[10px] bg-stone-100 px-2 py-0.5 rounded-full text-stone-500 border border-stone-200">V3.0-CORE</span></h1>
        </div>
        <div className="flex items-center gap-4">
          <div className="hidden md:flex items-center gap-4 text-[10px] font-bold text-stone-400 uppercase tracking-widest">
            <span className="flex items-center gap-1.5"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" /> Agent Online</span>
            <span className="w-px h-3 bg-stone-200" />
            <span className="flex items-center gap-1.5"><FolderTree size={12} /> {settings.repoMode}</span>
          </div>
          <button
            onClick={() => setShowSettings(true)}
            className="p-2 hover:bg-stone-100 rounded-full transition-colors text-stone-600"
            aria-label="Einstellungen öffnen"
          >
            <Settings size={18} />
          </button>
        </div>
      </header>

      {showSettings && (
        <SettingsModal
          repoUrl={repoUrl} setRepoUrl={setRepoUrl}
          accessKey={accessKey} setAccessKey={setAccessKey}
          geminiKey={geminiKey} setGeminiKey={setGeminiKey}
          settings={settings} setSettings={setSettings}
          setShowSettings={setShowSettings}
        />
      )}

      <MobileTabs mobilePane={mobilePane} setMobilePane={setMobilePane} isWorking={isWorking} />

      <main className="flex-1 flex overflow-hidden pb-16 md:pb-0">
        <div className={`${mobilePane === 'auftrag' ? 'flex' : 'hidden'} md:flex`}>
          <Sidebar
            settings={settings}
            buildProduct={buildProduct}
            blueprint={blueprint}
            setBlueprint={setBlueprint}
            addCard={addCard}
            log={log}
            selectedFile={selectedFile}
            setSelectedFile={setSelectedFile}
            setWorkView={setWorkView}
            repoUrl={repoUrl}
            setRepoUrl={setRepoUrl}
            setShowSettings={setShowSettings}
            isWorking={isWorking}
          />
        </div>

        <div className={`flex-1 min-w-0 flex flex-col ${mobilePane === 'live' ? 'flex' : 'hidden'} md:flex`}>
          <MainContent
            workView={workView}
            setWorkView={setWorkView}
            selectedFile={selectedFile}
            currentCode={currentCode}
            pipelineState={pipelineState}
            settings={settings}
            publishAndValidate={publishAndValidate}
            patchFromPipeline={patchFromPipeline}
            mergeWhenGreen={mergeWhenGreen}
            chatInput={chatInput}
            setChatInput={setChatInput}
            sendChat={sendChat}
            log={log}
            cardsCount={cards.length}
            fixLoops={fixLoops}
            isWorking={isWorking}
            agentMessage={agentMessage}
            progress={progress}
            currentStepLabel={currentStepLabel}
            nextStepLabel={nextStepLabel}
            approvalConfirmed={approvalConfirmed}
            targetLink={targetLink}
          />
        </div>

        <div className={`${mobilePane === 'log' ? 'flex' : 'hidden'} md:flex`}>
          <LogSidebar
            logs={logs}
            setLogs={setLogs}
            downloadPackage={downloadPackage}
          />
        </div>
      </main>
    </div>
  );
}
