import React, { useState, useEffect, useRef } from 'react';
import { 
  Folder, Code2, MessageSquare, Trash2, RefreshCw, Github, Key, 
  Play, Sparkles, Shield, FileText, CheckCircle, AlertTriangle, Info, 
  Search, BookOpen, Flame, Beaker, Unlock
} from 'lucide-react';
import { PaywallModal } from './features/paywall/components/PaywallModal';
import { PrivacyModal } from './features/privacy/components/PrivacyModal';
import { MobileNavigation } from './components/MobileNavigation';
import { Header } from './components/Header';
import { ConfigBar } from './features/config/components/ConfigBar';
import { storageService } from './services/storageService';
import Editor from '@monaco-editor/react';

// --- Types ---
type FileNode = { path: string, type: string, mode: string, sha: string };
type LogMessage = { id: number, text: string, type: 'info' | 'success' | 'warning' | 'error' | 'idea' };
type BatchFile = { path: string, content?: string, isDelete?: boolean };
type PRState = { branch: string | null, number: number | null, lastErrorLog: string, isFixing: boolean, lastCommitSha: string | null };

const SafeLogText = ({ text }: { text: string }) => (
  <span dangerouslySetInnerHTML={{ __html: text }} />
);

export default function App() {
  // --- State ---
  const [repoUrl, setRepoUrl] = useState("https://github.com/OuroborosCollective/Wasd");
  const [repoOwner, setRepoOwner] = useState("OuroborosCollective");
  const [repoName, setRepoName] = useState("Wasd");
  const [ghPat, setGhPat] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  
  const [activeTab, setActiveTab] = useState<'explorer' | 'editor' | 'chat'>('explorer');
  const [fullTree, setFullTree] = useState<FileNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(false);
  const [treeError, setTreeError] = useState("");
  
  const [activeFile, setActiveFile] = useState<FileNode | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [loadingFile, setLoadingFile] = useState(false);
  const [fileTooLarge, setFileTooLarge] = useState(false);
  const MAX_FILE_SIZE = 500 * 1024; // 500 KB

  const [batchFiles, setBatchFiles] = useState<BatchFile[]>([]);
  const [activePR, setActivePR] = useState<PRState>({ branch: null, number: null, lastErrorLog: "", isFixing: false, lastCommitSha: null });
  const [ciStatus, setCiStatus] = useState<{ text: string, percent: number, isFailed: boolean, isRunning: boolean } | null>(null);
  
  const [logs, setLogs] = useState<LogMessage[]>([
    { id: 1, text: "🚀 <b>Sovereign Studio v3.0.0 geladen</b><br>- Dynamisches Repo: Du kannst nun via URL jedes Git-Repository analysieren.<br>- Hybride API: Canvas Auto-Auth ist aktiv. Custom Keys sind optional.<br>- Smart Context: KI nutzt nun den vollständigen Verzeichnisbaum.<br>- Stack Enforcer: Strikter Fokus auf Node, React, TypeScript.", type: 'info' }
  ]);
  
  const [architectInput, setArchitectInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);

  // --- Paywall & Usage Limits ---
  const [prRuns, setPrRuns] = useState<number>(0);
  const [ideaRuns, setIdeaRuns] = useState<number>(0);
  const [isPro, setIsPro] = useState<boolean>(false);
  const [showPaywall, setShowPaywall] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const logIdCounter = useRef(2);
  const ciPollTimer = useRef<number | null>(null);

  // --- Effects ---
  useEffect(() => {
    const loadData = async () => {
      const pat = await storageService.get('ss_gh_pat');
      if (pat) setGhPat(pat);

      const gKey = await storageService.get('ss_gemini_key');
      if (gKey) setGeminiKey(gKey);

      const pr = await storageService.get('ss_pr_runs');
      if (pr) setPrRuns(parseInt(pr, 10));

      const idea = await storageService.get('ss_idea_runs');
      if (idea) setIdeaRuns(parseInt(idea, 10));

      const pro = await storageService.get('ss_is_pro');
      if (pro) setIsPro(pro === 'true');
    };
    loadData();
  }, []);

  useEffect(() => {
    fetchRepoTree();
    
    return () => {
      if (ciPollTimer.current) window.clearTimeout(ciPollTimer.current);
    };
  }, [repoOwner, repoName]);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // --- Error Logger ---
  const logPersistentError = async (err: any, context: string) => {
    try {
      const logsJson = await storageService.get('ss_error_log');
      const currentLogs = JSON.parse(logsJson || '[]');
      let errMsg = err?.message || String(err);
      
      if (ghPat) errMsg = errMsg.split(ghPat).join('[REDACTED_GH_PAT]');
      if (geminiKey) errMsg = errMsg.split(geminiKey).join('[REDACTED_GEMINI_KEY]');
      
      currentLogs.push({ time: new Date().toISOString(), context, message: errMsg });
      storageService.set('ss_error_log', JSON.stringify(currentLogs.slice(-50)));
    } catch (e) {
      // Ignore
    }
  };

  // --- Handlers ---
  const handleGhPatChange = (val: string) => {
    setGhPat(val);
    storageService.set('ss_gh_pat', val);
  };

  const handleGeminiKeyChange = (val: string) => {
    setGeminiKey(val);
    storageService.set('ss_gemini_key', val);
  };

  const handleCleanup = async () => {
    await storageService.remove('ss_gh_pat');
    await storageService.remove('ss_gemini_key');
    setGhPat("");
    setGeminiKey("");
    setLogs([]);
    addLog('Workspace Cleanup abgeschlossen. Alle sensitiven API-Schlüssel wurden vom Gerät gelöscht.', 'success');
  };

  const addLog = (text: string, type: LogMessage['type'] = 'info') => {
    setLogs(prev => [...prev, { id: logIdCounter.current++, text, type }]);
  };

  const handleRepoChange = () => {
    const regex = /github\.com\/([^/]+)\/([^/]+)/;
    const match = repoUrl.match(regex);
    if (match && match.length >= 3) {
      const newOwner = match[1];
      const newName = match[2].replace(/\.git$/, '');
      setRepoOwner(newOwner);
      setRepoName(newName);
      addLog(`🔄 <b>Repository erfolgreich gewechselt:</b><br><code>${newOwner}/${newName}</code>`, 'success');
      
      setActiveFile(null);
      setFileContent("");
      setFileTooLarge(false);
      setBatchFiles([]);
      setActivePR({ branch: null, number: null, lastErrorLog: "", isFixing: false, lastCommitSha: null });
      setCiStatus(null);
      if (ciPollTimer.current) {
        window.clearTimeout(ciPollTimer.current);
        ciPollTimer.current = null;
      }
    } else {
      addLog(`❌ <b>Ungültige URL.</b> Erwartet: <code>https://github.com/owner/repo</code>`, "error");
    }
  };

  const fetchRepoTree = async () => {
    if (ghPat && !ghPat.startsWith('ghp_') && !ghPat.startsWith('github_pat_')) {
       addLog('<b>Fehler:</b> Ungültiger GitHub PAT. Token muss mit "ghp_" oder "github_pat_" beginnen.', "error");
       return;
    }

    setLoadingTree(true);
    setTreeError("");
    try {
      const headers: Record<string, string> = { 'Accept': 'application/vnd.github.v3+json' };
      if (ghPat) headers['Authorization'] = `token ${ghPat}`;
      
      const response = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/trees/main?recursive=1`, { headers });
      if (!response.ok) throw new Error(`HTTP ${response.status} - Repository eventuell privat oder existiert nicht.`);
      const data = await response.json();
      
      if (data.truncated) {
        addLog(`⚠️ <b>Achtung:</b> Repository ist sehr groß. Tree wurde von GitHub abgeschnitten.`, "warning");
      }
      
      const files = data.tree.filter((item: any) => item.type === 'blob');
      setFullTree(files);
      addLog(`📁 <b>Tree geladen:</b> ${files.length} Dateien im Index gefunden.`, "success");
    } catch (err: any) {
      addLog(`❌ <b>Fehler beim Laden des Trees:</b> ${err.message}<br>Tipp: Bei privaten Repositories PAT prüfen.`, "error");
      setTreeError("Repository konnte nicht geladen werden.");
    } finally {
      setLoadingTree(false);
    }
  };

  const loadFile = async (file: FileNode) => {
    setActiveFile(file);
    setActiveTab('editor');
    setLoadingFile(true);
    setFileContent("");
    setFileTooLarge(false);
    
    try {
      const branch = activePR.branch || 'main';
      let response = await fetch(`https://raw.githubusercontent.com/${repoOwner}/${repoName}/${branch}/${file.path}`);
      if (!response.ok) {
        const headers: Record<string, string> = { 'Accept': 'application/vnd.github.v3.raw' };
        if (ghPat) headers['Authorization'] = `token ${ghPat}`;
        
        response = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/contents/${file.path}?ref=${branch}`, { headers });
        if (!response.ok) throw new Error("Datei nicht lesbar");
      }
      const text = await response.text();
      if (text.length > MAX_FILE_SIZE) {
         setFileTooLarge(true);
         if (!isPro) {
            setFileContent("// ⚠️ Diese Datei ist zu groß für den Free-Plan (>500KB).\n// Bitte schalte PRO frei, um große Dateien im Editor anzusehen.");
         } else {
            setFileContent(text.substring(0, 100000) + "\n\n... [File too large. Previewing first 100k chars.] ...");
         }
      } else {
         setFileTooLarge(false);
         setFileContent(text);
      }
    } catch (err) {
      setFileContent(`// Fehler beim Laden: ${err}`);
    } finally {
      setLoadingFile(false);
    }
  };

  const callGeminiAPI = async (prompt: string, system: string) => {
    const customKey = geminiKey.trim();
    let envKey = "";
    try {
        if (typeof (import.meta as any) !== 'undefined' && (import.meta as any).env && (import.meta as any).env.VITE_GEMINI_API_KEY) {
            envKey = (import.meta as any).env.VITE_GEMINI_API_KEY;
        } else if (typeof process !== 'undefined' && process.env && process.env.GEMINI_API_KEY) {
            envKey = process.env.GEMINI_API_KEY;
        }
    } catch(e) {}
    
    let activeApiKey = customKey !== "" ? customKey : envKey;
    if (!activeApiKey) {
        addLog(`❌ <b>Gemini API-Schlüssel fehlt.</b>`, "error");
        return "";
    }

    const { GoogleGenerativeAI } = await import("@google/generative-ai");
    const ai = new GoogleGenerativeAI(activeApiKey);
    const model = ai.getGenerativeModel({ model: "gemini-1.5-flash", systemInstruction: system });
    
    const maxRetries = 3;
    for (let i = 0; i <= maxRetries; i++) {
        try {
            const result = await model.generateContent(prompt);
            const response = await result.response;
            return response.text() || "";
        } catch (err: any) {
            if (i === maxRetries) throw err;
            await new Promise(r => setTimeout(r, 2000));
        }
    }
    return "";
  };

  const runArchitect = async (isAutoFix = false, autoFixLog = "") => {
    if (!isPro && prRuns >= 15) {
      setShowPaywall(true);
      return;
    }

    const input = isAutoFix ? autoFixLog : architectInput.trim();
    if (!input) return;

    setPrRuns(prev => {
      const newVal = prev + 1;
      storageService.set('ss_pr_runs', String(newVal));
      return newVal;
    });

    setIsProcessing(true);
    setActiveTab('editor');
    addLog("<b>Architekt evaluiert Blueprint...</b>", "info");

    try {
      const treeContext = fullTree.slice(0, 400).map(f => f.path).join('\n');
      const architectSys = `Du bist Architekt. TECH: Node, TS, React. KEIN RUST! GIB NUR JSON ZURÜCK: [ { "path": "...", "task": "...", "action": "modify" } ]`;
      const rawPlan = await callGeminiAPI(input + "\nTree:\n" + treeContext, architectSys);
      
      let cleanPlan = rawPlan.replace(/json/gi, '').replace(//g, '').trim();
      const startIdx = cleanPlan.indexOf('[');
      const endIdx = cleanPlan.lastIndexOf(']');
      if (startIdx !== -1 && endIdx !== -1) cleanPlan = cleanPlan.substring(startIdx, endIdx + 1);
      
      const plan = JSON.parse(cleanPlan);
      const newFiles: BatchFile[] = [];

      for (const step of plan) {
        if (step.path.match(/lock\.json|lock\.yaml|\.lock/i) || step.path.toLowerCase().includes('jules')) {
          continue;
        }

        addLog(`⚙️ <b>Schreibe Code:</b> <code>${step.path}</code>`, "info");
        const branch = activePR.branch || 'main';
        let existingCode = "";
        try {
          const res = await fetch(`https://raw.githubusercontent.com/${repoOwner}/${repoName}/${branch}/${step.path}`);
          if (res.ok) existingCode = await res.text();
        } catch {}

        const compilerSys = `Du bist ein Elite Code-Generator. TECH: Node, TS, React. KEIN RUST! Gib AUSSCHLIESSLICH den kompletten, validen Code zurück.`;
        const compilerPrompt = `Datei: ${step.path}\nBisheriger Code:\n${existingCode}\n\nAufgabe: ${step.task}`;
        let newCode = await callGeminiAPI(compilerPrompt, compilerSys);
        newCode = newCode.replace(/^[a-z]*\n/i, '').replace(/[a-z]*\n?/gi, '').replace(//g, '').trim();
        
        newFiles.push({ path: step.path, content: newCode });
        setActiveFile({ path: step.path, type: 'blob', mode: '100644', sha: '' });
        setFileContent(newCode);
      }

      setBatchFiles(prev => [...prev, ...newFiles]);
      addLog(`🚀 <b>Workflow Abgeschlossen.</b>`, "success");
    } catch (err: any) {
      logPersistentError(err, 'runArchitect');
      addLog(`<b>Fehler:</b> ${err.message}`, "error");
    } finally {
      setIsProcessing(false);
    }
  };

  const suggestIdeas = async () => {
    if (!isPro && ideaRuns >= 6) { setShowPaywall(true); return; }
    if (fullTree.length === 0) return;
    
    setIdeaRuns(p => { const n = p + 1; storageService.set('ss_idea_runs', String(n)); return n; });
    setIsProcessing(true);
    setActiveTab('chat');
    addLog("✨ Scanne Architektur...", "idea");
    
    try {
        const paths = fullTree.slice(0, 150).map(f => f.path).join('\n');
        const ideas = await callGeminiAPI(`Struktur:\n${paths}\n\nSchlage 3 Verbesserungen vor.`, "Tech Lead. Bulletpoints.");
        addLog(`✨ <b>Ideen:</b><br>${ideas}`, "idea");
    } catch (e: any) { addLog(`Fehler: ${e.message}`, "error"); } 
    finally { setIsProcessing(false); }
  };

  const handlePush = async () => {
    if (!ghPat) return;
    setIsProcessing(true);
    try {
      const headers = { 'Authorization': `token ${ghPat}`, 'Accept': 'application/vnd.github.v3+json' };
      let branchName = activePR.branch || `architect-fix-${Date.now()}`;
      let baseSha;

      if (!activePR.branch) {
          const refRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/refs/heads/main`, {headers});
          const refData = await refRes.json();
          baseSha = refData.object.sha;
          await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/refs`, {
              method: 'POST', headers, body: JSON.stringify({ ref: `refs/heads/${branchName}`, sha: baseSha })
          });
      } else {
          const refRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/refs/heads/${branchName}`, {headers});
          const refData = await refRes.json();
          baseSha = refData.object.sha;
      }

      const commitRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/commits/${baseSha}`, {headers});
      const commitData = await commitRes.json();
      
      const tree = batchFiles.map(f => ({
          path: f.path, mode: '100644', type: 'blob', content: f.content, sha: f.isDelete ? null : undefined
      }));

      const newTreeRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/trees`, {
          method: 'POST', headers, body: JSON.stringify({ base_tree: commitData.tree.sha, tree })
      });
      const newTreeData = await newTreeRes.json();

      const newCommitRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/commits`, {
          method: 'POST', headers, body: JSON.stringify({ message: `AI Fix`, tree: newTreeData.sha, parents: [baseSha] })
      });
      const newCommitData = await newCommitRes.json();

      await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/refs/heads/${branchName}`, {
          method: 'PATCH', headers, body: JSON.stringify({ sha: newCommitData.sha })
      });

      if (!activePR.branch) {
          const prRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/pulls`, {
              method: 'POST', headers, body: JSON.stringify({ title: `AI: ${branchName}`, head: branchName, base: "main", body: "AI edits." })
          });
          const prData = await prRes.json();
          setActivePR({ branch: branchName, number: prData.number, lastErrorLog: "", isFixing: false, lastCommitSha: newCommitData.sha });
      } else {
          setActivePR(p => ({ ...p, lastCommitSha: newCommitData.sha }));
      }
      setBatchFiles([]);
      addLog("🟢 <b>Push erfolgreich!</b>", "success");
    } catch(err: any) { addLog(`Push Error: ${err.message}`, "error"); }
    finally { setIsProcessing(false); }
  };

  const fetchCIStatus = async () => {
    if (!ghPat || !activePR.lastCommitSha) return;
    setIsProcessing(true);
    try {
        const headers = { 'Authorization': `token ${ghPat}`, 'Accept': 'application/vnd.github.v3+json' };
        const res = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/commits/${activePR.lastCommitSha}/check-runs`, { headers });
        const data = await res.json();
        if (data.check_runs && data.check_runs.length > 0) {
            const run = data.check_runs[0];
            setCiStatus({ text: run.name, percent: run.status === 'completed' ? 100 : 50, isFailed: run.conclusion === 'failure', isRunning: run.status !== 'completed' });
            if (run.conclusion === 'failure') setActivePR(prev => ({ ...prev, lastErrorLog: run.output?.text || "CI failed." }));
        }
    } catch(e) {} finally { setIsProcessing(false); }
  };

  const getLogClasses = (type: string) => {
    switch(type) {
      case 'error': return 'bg-red-50 border-red-200 text-red-800';
      case 'success': return 'bg-green-50 border-green-200 text-green-800';
      case 'warning': return 'bg-amber-50 border-amber-200 text-amber-800';
      case 'idea': return 'bg-indigo-50 border-indigo-200 text-indigo-900';
      default: return 'bg-stone-50 border-stone-200 text-stone-800';
    }
  };

  return (
    <div className="w-full h-[100dvh] flex flex-col bg-[#f3f3f2] text-stone-900 overflow-hidden text-sm">
      <Header loadingTree={loadingTree} setShowPrivacy={setShowPrivacy} handleCleanup={handleCleanup} fetchRepoTree={fetchRepoTree} />
      <ConfigBar />

      <main className="flex-1 flex overflow-hidden relative">
        <div className={`${activeTab === 'explorer' ? 'flex' : 'hidden'} lg:flex flex-col lg:w-80 shrink-0 border-r border-stone-200/60 glass-panel h-full pb-14 lg:pb-0 z-10`}>
          <div className="p-3 bg-indigo-50 border-b border-indigo-200 shrink-0">
            <h3 className="text-[11px] font-black text-indigo-800 mb-1 flex justify-between items-center uppercase">
              <span>CI RESOLVER</span>
              <span className="px-2 py-0.5 rounded-full bg-indigo-200 text-indigo-800 text-[9px]">{activePR.number ? `PR #${activePR.number}` : "-"}</span>
            </h3>
            <div className="flex gap-2 mt-2">
              <button onClick={() => runArchitect(true, activePR.lastErrorLog)} disabled={isProcessing || !activePR.lastErrorLog} className="flex-1 bg-rose-600 text-white py-1.5 rounded text-[10px] font-bold uppercase">FIX CI</button>
              <button onClick={fetchCIStatus} disabled={isProcessing} className="flex-1 bg-indigo-600 text-white py-1.5 rounded text-[10px] font-bold uppercase">CHECK</button>
            </div>
          </div>

          <div className="p-3 bg-stone-50 border-b border-stone-200 shrink-0">
            <h3 className="text-[11px] font-bold text-stone-700 mb-2 flex items-center gap-1 uppercase"><Sparkles size={12}/> Blueprint</h3>
            <textarea value={architectInput} onChange={(e) => setArchitectInput(e.target.value)} rows={3} className="w-full p-2 text-[11px] border border-stone-300 rounded focus:border-indigo-500 resize-none" placeholder="Task..."/>
            <div className="flex gap-2 mt-2">
              <button onClick={() => runArchitect()} disabled={isProcessing} className="flex-1 bg-stone-800 text-white py-1.5 rounded-lg text-[11px] font-bold uppercase">GENERIERE</button>
              <button onClick={suggestIdeas} disabled={isProcessing} className="shrink-0 bg-yellow-100 border border-yellow-300 text-yellow-800 px-3 py-1.5 rounded-lg text-[11px]">✨</button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto bg-white custom-scrollbar">
             {loadingTree ? <div className="p-4 text-xs flex justify-center"><RefreshCw size={14} className="animate-spin text-stone-400" /></div> : 
               <div>
                  {fullTree.slice(0, 200).map((file) => (
                    <div key={file.path} onClick={() => loadFile(file)} className={`px-4 py-2 border-b border-stone-100 text-[13px] truncate cursor-pointer ${activeFile?.path === file.path ? 'bg-indigo-600 text-white font-bold' : 'hover:bg-stone-50 text-stone-600'}`}>{file.path}</div>
                  ))}
               </div>
             }
          </div>
        </div>

        <div className={`${activeTab === 'editor' ? 'flex' : 'hidden'} lg:flex flex-1 flex-col min-w-0 bg-stone-50/70 pb-14 lg:pb-0 relative`}>
          <div className="h-10 bg-white border-b border-stone-200 flex items-center px-3 shrink-0 text-[11px] font-mono text-stone-600 truncate">{activeFile ? activeFile.path : "Keine Datei"}</div>
          <div className="flex-1 p-2 lg:p-4 flex flex-col relative overflow-hidden">
            <div className="bg-[#0c0a09] flex-1 rounded-2xl shadow-xl relative overflow-hidden flex flex-col border border-stone-800">
               {loadingFile || isProcessing ? <div className="flex-1 flex items-center justify-center text-indigo-400 font-mono text-xs uppercase"><RefreshCw size={14} className="animate-spin mr-2"/> Processing...</div> : (
                 <Editor
                    height="100%"
                    defaultLanguage="typescript"
                    theme="vs-dark"
                    value={fileContent}
                    options={{ readOnly: !isPro && fileTooLarge, minimap: { enabled: false }, fontSize: 12 }}
                    onChange={(v) => v && !fileTooLarge && setFileContent(v)}
                 />
               )}
            </div>
          </div>
          <div className="h-16 border-t border-indigo-200 px-4 flex items-center justify-between bg-indigo-50 shrink-0">
              <div className="truncate"><h4 className="text-[10px] font-black text-indigo-800 uppercase">Status</h4><p className="text-[10px] text-indigo-600">{batchFiles.length} Aktionen bereit.</p></div>
              <button onClick={handlePush} disabled={batchFiles.length === 0 || isProcessing} className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-bold text-[10px] uppercase">PUSH PR</button>
          </div>
        </div>

        <div className={`${activeTab === 'chat' ? 'flex' : 'hidden'} lg:flex flex-col lg:w-[350px] shrink-0 border-l border-stone-200/60 glass-panel h-full pb-14 lg:pb-0 z-10`}>
           <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold flex justify-between shrink-0"><span>LOG</span><button onClick={() => setLogs([])} className="text-stone-400">Clear</button></div>
           <div className="flex-1 overflow-y-auto p-4 bg-white text-[11px] flex flex-col gap-3">
              {logs.map((log) => (
                <div key={log.id} className={`p-3 rounded-xl border ${getLogClasses(log.type)}`}>
                  <SafeLogText text={log.text} />
                </div>
              ))}
              <div ref={logsEndRef} />
           </div>
        </div>
      </main>

      <MobileNavigation activeTab={activeTab} setActiveTab={setActiveTab} />
      <PaywallModal isOpen={showPaywall} onClose={() => setShowPaywall(false)} onUpgrade={async () => { setIsPro(true); await storageService.set('ss_is_pro', 'true'); setShowPaywall(false); }} onSubscribe={async () => { setIsPro(true); await storageService.set('ss_is_pro', 'true'); setShowPaywall(false); }} />
      <PrivacyModal isOpen={showPrivacy} onClose={() => setShowPrivacy(false)} onAccept={() => setShowPrivacy(false)} />
    </div>
  );
}