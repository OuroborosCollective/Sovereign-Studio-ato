/**
 * RefactorPanel - Main UI for AI-powered code refactoring
 * 
 * This is the main interface for the refactor feature.
 * It's the central hub for all AI operations in the app.
 */

import React, { useState, useCallback } from 'react';
import { 
  Bot, 
  ChevronRight, 
  Code2, 
  FileCode2, 
  Loader2, 
  Play, 
  RefreshCw, 
  Sparkles, 
  Trash2,
  Zap,
  GitBranch,
  History,
  Eye,
  Send,
} from 'lucide-react';
import { useRefactor, useProviderStatus, useAnalyze, useGenerate } from './RefactorContext';
import { type RefactorPlan, type RefactorTask } from './RefactorEngine';

// ============================================================
// Parse GitHub URL
// ============================================================

function parseGithubRepoUrl(value: string): { owner: string; repo: string } | null {
  const match = value.match(/github\.com\/([^\/\s]+)\/([^\/\s#?]+)/i);
  if (!match) return null;
  return { owner: match[1], repo: match[2].replace(/\.git$/, '') };
}

// ============================================================
// Provider Status Badge
// ============================================================

function ProviderBadge() {
  const { currentProvider, isLoading } = useProviderStatus();
  const { geminiKey, groqKey } = useRefactor();

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-stone-900 rounded-lg">
      {isLoading ? (
        <Loader2 size={14} className="text-amber-400 animate-spin" />
      ) : (
        <Zap size={14} className="text-emerald-400" />
      )}
      <span className="text-xs font-mono text-stone-300">
        {currentProvider.toUpperCase()}
      </span>
      {geminiKey?.trim() && (
        <span className="text-[10px] text-amber-500">GEMINI</span>
      )}
      {groqKey?.trim() && (
        <span className="text-[10px] text-emerald-500">GROQ</span>
      )}
    </div>
  );
}

// ============================================================
// Repo Input Section
// ============================================================

interface RepoInputProps {
  onLoad: (url: string, files: any[]) => void;
}

function RepoInput({ onLoad }: RepoInputProps) {
  const { repoUrl, setRepoUrl } = useRefactor();
  const [branch, setBranch] = useState('main');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  const loadRepo = useCallback(async () => {
    const parsed = parseGithubRepoUrl(repoUrl);
    if (!parsed) {
      setStatus('❌ Invalid GitHub URL');
      return;
    }

    setLoading(true);
    setStatus(`Loading ${parsed.owner}/${parsed.repo}...`);

    try {
      const headers: Record<string, string> = { Accept: 'application/vnd.github+json' };
      // TODO: Add token support for private repos
      // const token = localStorage.getItem('sovereign_github_pat');
      // if (token) headers.Authorization = `Bearer ${token}`;

      const response = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${branch}?recursive=1`,
        { headers }
      );

      if (!response.ok) {
        throw new Error(`GitHub API: ${response.status}`);
      }

      const data = await response.json();
      const treeData: any[] = data.tree ?? [];
      const files = treeData
        .filter(f => f.type === 'blob' || f.type === 'tree')
        .map(f => ({ path: f.path, type: f.type, size: f.size }))
        .slice(0, 250);

      setStatus(`✓ ${files.length} files loaded`);
      onLoad(repoUrl, files);
    } catch (err: any) {
      setStatus(`❌ Error: ${err?.message || 'Failed to load'}`);
    } finally {
      setLoading(false);
    }
  }, [repoUrl, branch, onLoad]);

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <GitBranch size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-500" />
          <input
            type="text"
            value={repoUrl}
            onChange={e => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            className="w-full bg-stone-800 border border-stone-700 text-stone-200 placeholder-stone-500 
                       px-4 py-2 pl-10 rounded-lg font-mono text-sm focus:outline-none 
                       focus:border-amber-500 focus:shadow-[0_0_10px_rgba(245,158,11,0.2)]"
          />
        </div>
        <input
          type="text"
          value={branch}
          onChange={e => setBranch(e.target.value)}
          placeholder="main"
          className="w-24 bg-stone-800 border border-stone-700 text-stone-300 placeholder-stone-500 
                     px-3 py-2 rounded-lg font-mono text-sm focus:outline-none focus:border-amber-500"
        />
      </div>
      <button
        onClick={loadRepo}
        disabled={loading}
        className="w-full bg-amber-600 hover:bg-amber-500 disabled:bg-amber-900 disabled:text-amber-700 
                   text-black font-mono font-bold py-2 rounded-lg transition-all flex items-center justify-center gap-2"
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : <GitBranch size={16} />}
        {loading ? 'LOADING...' : 'LOAD REPOSITORY'}
      </button>
      {status && (
        <p className={`text-xs font-mono ${status.startsWith('❌') ? 'text-red-400' : 'text-emerald-400'}`}>
          {status}
        </p>
      )}
    </div>
  );
}

// ============================================================
// Task List
// ============================================================

interface TaskListProps {
  plan: RefactorPlan;
  onSelectTask: (task: RefactorTask) => void;
  onGenerateAll: () => void;
}

function TaskList({ plan, onSelectTask, onGenerateAll }: TaskListProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-stone-300">REFACTOR TASKS</h3>
        <button
          onClick={onGenerateAll}
          className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-bold rounded flex items-center gap-1"
        >
          <Sparkles size={12} />
          GENERATE ALL
        </button>
      </div>
      <div className="space-y-1">
        {plan.tasks.map((task, i) => (
          <button
            key={task.id}
            onClick={() => onSelectTask(task)}
            className="w-full text-left px-3 py-2 bg-stone-800 hover:bg-stone-700 border border-stone-700 
                       hover:border-amber-500/50 rounded-lg transition-all flex items-center gap-3 group"
          >
            <span className="w-6 h-6 rounded-full bg-amber-600 text-black text-xs font-bold flex items-center justify-center">
              {i + 1}
            </span>
            <span className="flex-1 text-sm text-stone-300 group-hover:text-amber-200 truncate">
              {task.title}
            </span>
            <ChevronRight size={14} className="text-stone-600 group-hover:text-amber-400" />
          </button>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// Code Preview
// ============================================================

interface CodePreviewProps {
  task: RefactorTask;
  onApply: (code: string) => void;
  onExplain: () => void;
}

function CodePreview({ task, onApply, onExplain }: CodePreviewProps) {
  const [generatedCode, setGeneratedCode] = useState<string | null>(task.generatedCode || null);
  const [loading, setLoading] = useState(false);
  const { generateCode } = useRefactor();

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    try {
      const code = await generateCode(task);
      setGeneratedCode(code);
    } catch (err) {
      console.error('Generation failed:', err);
    } finally {
      setLoading(false);
    }
  }, [task, generateCode]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-amber-400">
          <Code2 size={14} className="inline mr-2" />
          {task.title}
        </h3>
        <div className="flex gap-2">
          <button
            onClick={onExplain}
            className="px-3 py-1 bg-stone-700 hover:bg-stone-600 text-stone-300 text-xs rounded flex items-center gap-1"
          >
            <Eye size={12} />
            EXPLAIN
          </button>
          {!generatedCode && (
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-500 disabled:bg-amber-900 
                         text-black text-xs font-bold rounded flex items-center gap-1"
            >
              {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              {loading ? 'GENERATING...' : 'GENERATE'}
            </button>
          )}
        </div>
      </div>
      
      <p className="text-xs text-stone-400">{task.description}</p>

      {generatedCode && (
        <div className="relative">
          <pre className="bg-stone-900 border border-stone-700 rounded-lg p-4 overflow-auto max-h-96 text-xs font-mono text-stone-300">
            {generatedCode}
          </pre>
          <div className="absolute top-2 right-2 flex gap-2">
            <button
              onClick={() => onApply(generatedCode)}
              className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-bold rounded"
            >
              APPLY
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// History Panel
// ============================================================

interface HistoryPanelProps {
  history: RefactorPlan[];
  onSelect: (plan: RefactorPlan) => void;
}

function HistoryPanel({ history, onSelect }: HistoryPanelProps) {
  if (history.length === 0) {
    return (
      <div className="text-center py-8 text-stone-500 text-sm">
        <History size={24} className="mx-auto mb-2 opacity-50" />
        No refactor history yet
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {history.map((plan) => (
        <button
          key={plan.id}
          onClick={() => onSelect(plan)}
          className="w-full text-left px-3 py-2 bg-stone-800/50 hover:bg-stone-700 border border-stone-700/50 
                     hover:border-stone-600 rounded transition-all"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-stone-300 truncate">{plan.context.projectName}</span>
            <span className="text-[10px] text-stone-500">{plan.tasks.length} tasks</span>
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[10px] text-amber-500">{plan.provider.toUpperCase()}</span>
            <span className="text-[10px] text-stone-600">
              {new Date(plan.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </button>
      ))}
    </div>
  );
}

// ============================================================
// Main RefactorPanel Component
// ============================================================

export function RefactorPanel() {
  const { 
    files, 
    setFiles,
    history, 
    currentPlan, 
    setCurrentPlan,
    isLoading,
    error,
    lastResult,
  } = useRefactor();

  const [selectedTask, setSelectedTask] = useState<RefactorTask | null>(null);
  const [activeTab, setActiveTab] = useState<'tasks' | 'history' | 'output'>('tasks');
  const [chatInput, setChatInput] = useState('');
  const [explanation, setExplanation] = useState<string | null>(null);

  const analyze = useAnalyze();
  const generate = useGenerate();

  const handleLoadRepo = useCallback(async (url: string, repoFiles: any[]) => {
    setFiles(repoFiles);
    try {
      const plan = await analyze(url, repoFiles);
      setCurrentPlan(plan);
      setActiveTab('tasks');
    } catch (err) {
      console.error('Analysis failed:', err);
    }
  }, [analyze, setFiles, setCurrentPlan]);

  const handleGenerateAll = useCallback(async () => {
    if (!currentPlan) return;
    
    for (const task of currentPlan.tasks) {
      try {
        const code = await generate(`Generate code for: ${task.description}`, {});
        task.generatedCode = code;
        task.status = 'completed';
      } catch (err) {
        task.status = 'failed';
        task.error = String(err);
      }
    }
    setCurrentPlan({ ...currentPlan });
  }, [currentPlan, generate, setCurrentPlan]);

  const handleApplyCode = useCallback((code: string) => {
    // Copy to clipboard
    navigator.clipboard.writeText(code);
    // TODO: Implement actual file apply via GitHub API
  }, []);

  const handleExplain = useCallback(async () => {
    if (!selectedTask?.generatedCode) return;
    try {
      const result = await generate(`Explain this code in German:\n\n${selectedTask.generatedCode}`, { temperature: 0.3 });
      setExplanation(result);
    } catch (err) {
      console.error('Explain failed:', err);
    }
  }, [selectedTask, generate]);

  const handleChat = useCallback(async () => {
    if (!chatInput.trim()) return;
    try {
      await generate(chatInput, {});
      setChatInput('');
      setActiveTab('output');
    } catch (err) {
      console.error('Chat failed:', err);
    }
  }, [chatInput, generate]);

  return (
    <div className="h-full flex flex-col bg-stone-950 text-stone-100">
      {/* Header */}
      <div className="shrink-0 border-b border-stone-800 p-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
            <Bot size={20} className="text-black" />
          </div>
          <div>
            <h1 className="font-mono font-bold text-lg">REFACTOR</h1>
            <p className="text-[10px] text-stone-500">AI-Powered Code Transformation</p>
          </div>
        </div>
        <ProviderBadge />
      </div>

      {/* Tab Navigation */}
      <div className="shrink-0 flex border-b border-stone-800">
        {(['tasks', 'history', 'output'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 px-4 py-2 text-xs font-bold uppercase transition-colors ${
              activeTab === tab
                ? 'bg-stone-800 text-amber-400 border-b-2 border-amber-500'
                : 'text-stone-500 hover:text-stone-300'
            }`}
          >
            {tab === 'tasks' && <FileCode2 size={12} className="inline mr-1" />}
            {tab === 'history' && <History size={12} className="inline mr-1" />}
            {tab === 'output' && <Eye size={12} className="inline mr-1" />}
            {tab.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {/* Repo Input - Always visible */}
        <RepoInput onLoad={handleLoadRepo} />

        {/* Error Display */}
        {error && (
          <div className="p-3 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm font-mono">
            ❌ {error}
          </div>
        )}

        {/* Tasks Tab */}
        {activeTab === 'tasks' && (
          <div className="space-y-4">
            {currentPlan ? (
              <>
                <div className="p-3 bg-stone-900/50 border border-stone-700 rounded-lg">
                  <h2 className="text-sm font-bold text-amber-400 mb-2">{currentPlan.context.projectName}</h2>
                  <pre className="text-xs text-stone-400 whitespace-pre-wrap font-mono">{currentPlan.analysis}</pre>
                </div>
                <TaskList 
                  plan={currentPlan} 
                  onSelectTask={setSelectedTask}
                  onGenerateAll={handleGenerateAll}
                />
              </>
            ) : (
              <div className="text-center py-8 text-stone-500 text-sm">
                <Sparkles size={24} className="mx-auto mb-2 opacity-50" />
                Load a repository to begin refactoring
              </div>
            )}
          </div>
        )}

        {/* History Tab */}
        {activeTab === 'history' && (
          <HistoryPanel history={history} onSelect={setCurrentPlan} />
        )}

        {/* Output Tab */}
        {activeTab === 'output' && (
          <div className="space-y-4">
            {explanation && (
              <div className="p-3 bg-blue-900/30 border border-blue-800 rounded-lg">
                <h3 className="text-sm font-bold text-blue-400 mb-2">EXPLANATION</h3>
                <p className="text-sm text-blue-200 font-mono">{explanation}</p>
              </div>
            )}
            {lastResult && (
              <div className="relative">
                <pre className="bg-stone-900 border border-stone-700 rounded-lg p-4 overflow-auto max-h-[60vh] text-xs font-mono text-stone-300">
                  {lastResult}
                </pre>
                <button
                  onClick={() => navigator.clipboard.writeText(lastResult)}
                  className="absolute top-2 right-2 px-3 py-1 bg-stone-700 hover:bg-stone-600 text-stone-300 text-xs rounded"
                >
                  COPY
                </button>
              </div>
            )}
          </div>
        )}

        {/* Task Detail View */}
        {selectedTask && activeTab === 'tasks' && (
          <CodePreview 
            task={selectedTask} 
            onApply={handleApplyCode}
            onExplain={handleExplain}
          />
        )}
      </div>

      {/* Chat Input */}
      <div className="shrink-0 border-t border-stone-800 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={chatInput}
            onChange={e => setChatInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleChat(); }}
            placeholder="Ask anything or describe what to build..."
            className="flex-1 bg-stone-800 border border-stone-700 text-stone-200 placeholder-stone-500 
                       px-4 py-3 rounded-lg font-mono text-sm focus:outline-none 
                       focus:border-amber-500 focus:shadow-[0_0_10px_rgba(245,158,11,0.2)]"
          />
          <button
            onClick={handleChat}
            disabled={isLoading}
            className="bg-amber-600 hover:bg-amber-500 disabled:bg-amber-900 disabled:text-amber-700 
                       text-black font-mono font-bold px-6 rounded-lg transition-all flex items-center gap-2"
          >
            {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            {isLoading ? 'WORKING...' : 'SEND'}
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between text-[10px] text-stone-600 font-mono">
          <span>Press Enter to send • Free AI active</span>
          <span>{files.length} files loaded</span>
        </div>
      </div>
    </div>
  );
}

export default RefactorPanel;