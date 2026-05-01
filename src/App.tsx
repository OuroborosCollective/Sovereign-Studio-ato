import React, { useState, useEffect, useRef } from 'react';
import { 
  Folder, Code2, MessageSquare, Trash2, RefreshCw, Github, Key, 
  Play, Sparkles, Shield, FileText, CheckCircle, AlertTriangle, Info, 
  Search, BookOpen, Flame, Beaker, Unlock
} from 'lucide-react';
import { PaywallModal } from './components/PaywallModal';
import { PrivacyModal } from './components/PrivacyModal';
import Editor from '@monaco-editor/react';

// --- Types ---
type FileNode = { path: string, type: string, mode: string, sha: string };
type LogMessage = { id: number, text: string, type: 'info' | 'success' | 'warning' | 'error' | 'idea' };
type BatchFile = { path: string, content?: string, isDelete?: boolean };
type PRState = { branch: string | null, number: number | null, lastErrorLog: string, isFixing: boolean, lastCommitSha: string | null };

export default function App() {
  // --- State ---
  const [repoUrl, setRepoUrl] = useState("https://github.com/OuroborosCollective/Wasd");
  const [repoOwner, setRepoOwner] = useState("OuroborosCollective");
  const [repoName, setRepoName] = useState("Wasd");
  const [ghPat, setGhPat] = useState(() => localStorage.getItem('ss_gh_pat') || "");
  const [geminiKey, setGeminiKey] = useState(() => localStorage.getItem('ss_gemini_key') || "");
  
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
  const [prRuns, setPrRuns] = useState<number>(() => {
    const saved = localStorage.getItem('ss_pr_runs');
    return saved !== null ? parseInt(saved, 10) : 0;
  });
  const [ideaRuns, setIdeaRuns] = useState<number>(() => {
    const saved = localStorage.getItem('ss_idea_runs');
    return saved !== null ? parseInt(saved, 10) : 0;
  });
  const [isPro, setIsPro] = useState<boolean>(() => {
    return localStorage.getItem('ss_is_pro') === 'true';
  });
  const [showPaywall, setShowPaywall] = useState(false);
  const [showPrivacy, setShowPrivacy] = useState(false);

  const logsEndRef = useRef<HTMLDivElement>(null);
  const logIdCounter = useRef(2);
  const ciPollTimer = useRef<number | null>(null);

  // --- Effects ---
  useEffect(() => {
    fetchRepoTree();
    
    // Cleanup on unmount
    return () => {
      if (ciPollTimer.current) window.clearTimeout(ciPollTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoOwner, repoName]); // Fetch when repo changes

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // --- Error Logger ---
  const logPersistentError = (err: any, context: string) => {
    try {
      const currentLogs = JSON.parse(localStorage.getItem('ss_error_log') || '[]');
      let errMsg = err?.message || String(err);
      
      // Sanitize tokens from logs just in case
      if (ghPat) errMsg = errMsg.split(ghPat).join('[REDACTED_GH_PAT]');
      if (geminiKey) errMsg = errMsg.split(geminiKey).join('[REDACTED_GEMINI_KEY]');
      
      currentLogs.push({ time: new Date().toISOString(), context, message: errMsg });
      localStorage.setItem('ss_error_log', JSON.stringify(currentLogs.slice(-50)));
    } catch (e) {
      // Ignorieren falls localStorage voll ist
    }
  };

  // --- Handlers ---
  const handleGhPatChange = (val: string) => {
    setGhPat(val);
    localStorage.setItem('ss_gh_pat', val);
  };

  const handleGeminiKeyChange = (val: string) => {
    setGeminiKey(val);
    localStorage.setItem('ss_gemini_key', val);
  };

  const handleCleanup = () => {
    localStorage.removeItem('ss_gh_pat');
    localStorage.removeItem('ss_gemini_key');
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
        if (ghPat && !ghPat.startsWith('ghp_') && !ghPat.startsWith('github_pat_')) {
          throw new Error('Ungültiges PAT Format');
        }
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
            setFileContent(text.substring(0, 100000) + "\n\n... [File is too large to display entirely. Previewing first 100000 characters.] ...");
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
    // Safely check for env variable to prevent ReferenceError in browser
    let envKey = "";
    try {
        if (typeof import.meta !== 'undefined' && (import.meta as any).env && (import.meta as any).env.VITE_GEMINI_API_KEY) {
            envKey = (import.meta as any).env.VITE_GEMINI_API_KEY;
        } else if (typeof process !== 'undefined' && process.env && process.env.GEMINI_API_KEY) {
            envKey = process.env.GEMINI_API_KEY;
        }
    } catch(e) {}
    
    let activeApiKey = customKey !== "" ? customKey : envKey;
    
    if (!activeApiKey) {
        addLog(`❌ <b>Gemini API-Schlüssel fehlt:</b> Es konnte kein API-Schlüssel in der lokalen Umgebung oder im Secure Storage gefunden werden. Bitte gib deinen API-Schlüssel oben im Eingabefeld ein, um fortzufahren.`, "error");
        return "";
    }

    const { GoogleGenAI } = await import("@google/genai");
    const ai = new GoogleGenAI({ apiKey: activeApiKey });
    const maxRetries = 4;
    const delays = [1000, 2000, 4000, 8000];
    
    for (let i = 0; i <= maxRetries; i++) {
        try {
            const response = await ai.models.generateContent({
              model: "gemini-3-flash-preview",
              contents: prompt,
              config: { systemInstruction: system }
            });
            return response.text || "";
        } catch (err: any) {
            logPersistentError(err, `callGeminiAPI attempt ${i+1}`);
            if (i === maxRetries) {
                throw err;
            }
            await new Promise(resolve => setTimeout(resolve, delays[i]));
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
      localStorage.setItem('ss_pr_runs', String(newVal));
      return newVal;
    });

    setIsProcessing(true);
    setActiveTab('editor');
    addLog("<b>Architekt evaluiert Blueprint und wählt Ziel-Dateien...</b>", "info");

    try {
      const maxContextFiles = 400;
      const treeContext = fullTree.length > 0 
        ? fullTree.slice(0, maxContextFiles).map(f => f.path).join('\\n') 
        : "Keine Struktur geladen.";
      
      const architectSys = `Du bist ein brillanter Software-Architekt für das Projekt.
      WICHTIGE PROJEKT-REGELN:
      1. MONOREPO & NODE: Fokus auf Node.js, TypeScript, React.
      2. RUST VERBOTEN: Benutze, schreibe oder empfehle NIEMALS Rust!
      3. AGENTEN SCHÜTZEN: Ignoriere/Überspringe ALLE Dateien mit '.jules' oder 'jules' im Namen.
      4. LOCKFILES TABU: 'pnpm-lock.yaml', 'package-lock.json', 'yarn.lock' dürfen nicht bearbeitet werden.
      5. KONTEXT: Unten steht die aktuelle Verzeichnisstruktur. Wähle basierend darauf die RICHTIGEN Pfade aus.
      
      AKTUELLE STRUKTUR (Auszug):\n${treeContext}\n
      
      GIB AUSSCHLIESSLICH EIN VALIDES JSON-ARRAY ZURÜCK OHNE WEITEREN TEXT.
      Format: [ { "path": "exakter/pfad.ts", "task": "Was repariert/gebaut werden muss", "action": "modify" | "delete" } ]`;
      
      const rawPlan = await callGeminiAPI(input, architectSys);
      let cleanPlan = rawPlan.replace(/```[a-z]*\n/gi, '').replace(/```/g, '').trim();
      const startIdx = cleanPlan.indexOf('[');
      const endIdx = cleanPlan.lastIndexOf(']');
      if (startIdx !== -1 && endIdx !== -1) cleanPlan = cleanPlan.substring(startIdx, endIdx + 1);
      
      const plan = JSON.parse(cleanPlan);
      const newBatch: BatchFile[] = [];
      let processed = 0;

      for (const step of plan) {
        if (step.path.match(/lock\.json|lock\.yaml|\.lock/i) || step.path.toLowerCase().includes('jules')) {
          addLog(`🛡️ <b>Schutzmechanismus:</b> Überspringe System/Agenten-Datei <code>${step.path}</code>.`, "warning");
          continue; 
        }

        const isDeleteAction = step.action === 'delete' || step.task.toLowerCase().includes('lösche') || step.task.toLowerCase().includes('delete');
        if (isDeleteAction) {
          addLog(`🗑️ <b>Löschen:</b> <code>${step.path}</code> zur Entfernung markiert.`, "info");
          newBatch.push({ path: step.path, isDelete: true });
          processed++;
          continue; 
        }

        addLog(`⚙️ <b>Schreibe Code:</b> <code>${step.path}</code>...`, "info");
        
        const branch = activePR.branch || 'main';
        let existingCode = "";
        try {
          const res = await fetch(`https://raw.githubusercontent.com/${repoOwner}/${repoName}/${branch}/${step.path}`);
          if (res.ok) existingCode = await res.text();
        } catch { /* ignore */ }

        const compilerSys = `Du bist ein Elite Code-Generator.
        TECH STACK: Node.js, TypeScript, React. KEIN RUST!
        REGEL: Gib AUSSCHLIESSLICH den kompletten, validen, ausführbaren Code zurück. Keine Erklärungen.`;
        
        const compilerPrompt = `Datei: ${step.path}\nBisheriger Code:\n${existingCode}\n\nAufgabe: ${step.task}\n\nSetze dies um.`;
        let newCode = await callGeminiAPI(compilerPrompt, compilerSys);
        newCode = newCode.replace(/^```[a-z]*\n/gi, '').replace(/\n```$/gi, '').replace(/```/g, '').trim();
        
        newBatch.push({ path: step.path, content: newCode });
        setActiveFile({ path: step.path, type: 'blob', mode: '100644', sha: '' });
        setFileContent(newCode);
        processed++;
        addLog(`✅ <b>Fertig:</b> <code>${step.path}</code> implementiert.`, "success");
      }

      if (processed === 0) {
        addLog(`ℹ️ Keine verwertbaren Aktionen vom Architekten zurückgegeben.`, "warning");
        if (activePR.isFixing) setActivePR(p => ({ ...p, isFixing: false }));
      } else {
        setBatchFiles(prev => [...prev, ...newBatch]);
        addLog(`🚀 <b>Workflow Abgeschlossen:</b> Dateien in Batch-Queue hinzugefügt.`, "success");
        if (isAutoFix) {
          addLog(`⚙️ <b>Auto-Fix aktiv:</b> Starte Push Pipeline...`, "warning");
        }
      }

    } catch (err: any) {
      logPersistentError(err, 'runArchitect');
      addLog(`<b>Fehler im Architekt-Workflow:</b> ${err.message}`, "error");
      if (activePR.isFixing) setActivePR(p => ({ ...p, isFixing: false }));
    } finally {
      setIsProcessing(false);
    }
  };

  const suggestIdeas = async () => {
    if (!isPro && ideaRuns >= 6) {
        setShowPaywall(true);
        return;
    }
    
    if (fullTree.length === 0) {
        addLog("Bitte lade ein Repo, um Ideen zu generieren.", "warning");
        return;
    }
    
    setIdeaRuns(prev => {
      const newVal = prev + 1;
      localStorage.setItem('ss_idea_runs', String(newVal));
      return newVal;
    });

    setIsProcessing(true);
    setActiveTab('chat');
    addLog("✨ Scanne Projektarchitektur für Ideen...", "idea");
    
    try {
        const paths = fullTree.slice(0, 150).map(f => f.path).join('\n');
        const prompt = `Struktur:\n${paths}\n\nSchlage 3 präzise Architektur- oder Feature-Verbesserungen auf Deutsch vor.`;
        const ideas = await callGeminiAPI(prompt, "Du bist Tech Lead. Analysiere das Repo. Antworte in kurzen Bulletpoints (HTML format, verwende <ul> und <li>, keine Markdown code blöcke).");
        addLog(`✨ <b>Architektur Ideen:</b><br><div class="mt-2 text-stone-700">${ideas}</div>`, "idea");
    } catch (e: any) { 
        logPersistentError(e, 'suggestIdeas');
        addLog(`Fehler: ${e.message}`, "error"); 
    } 
    finally { 
        setIsProcessing(false); 
    }
  };

  const handlePush = async () => {
    if (!ghPat) {
       addLog("Kein GitHub PAT eingetragen! Push nicht möglich.", "error");
       return;
    }
    setIsProcessing(true);
    
    if (!ghPat || (!ghPat.startsWith('ghp_') && !ghPat.startsWith('github_pat_'))) {
       addLog('<b>Fehler:</b> Ein gültiger GitHub PAT (beginnend mit ghp_ oder github_pat_) ist erforderlich für Push & Commit.', 'error');
       setIsProcessing(false);
       return;
    }

    try {
      const headers = { 'Authorization': `token ${ghPat}`, 'Accept': 'application/vnd.github.v3+json' };
      let branchName = activePR.branch;
      let isNewBranch = false;
      let baseSha;

      if (!branchName) {
          branchName = `architect-fix-${Date.now()}`;
          isNewBranch = true;
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
      
      const currentTreeRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/trees/${commitData.tree.sha}?recursive=1`, {headers});
      const currentTreeData = await currentTreeRes.json();
      const liveTree = currentTreeData.tree;

      const tree = [];
      for (const f of batchFiles) {
          if (f.isDelete) {
              const existingItem = liveTree.find((item: any) => item.path === f.path);
              if (existingItem) tree.push({ path: f.path, mode: existingItem.mode, type: existingItem.type, sha: null });
          } else {
              tree.push({ path: f.path, mode: '100644', type: 'blob', content: f.content });
          }
      }

      const newTreeRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/trees`, {
          method: 'POST', headers, body: JSON.stringify({ base_tree: commitData.tree.sha, tree })
      });
      const newTreeData = await newTreeRes.json();

      const msgPrompt = `Generiere kurze Commit-Message für: ${batchFiles.map(f=>f.path).join(", ")}.`;
      let commitMessage = `Sovereign AI Deployment (${batchFiles.length} actions)`;
      try {
        const msg = await callGeminiAPI(msgPrompt, "Du bist Git Commit Generator. Antworte NUR mit text.");
        if (msg) commitMessage = `✨ ${msg.trim()}`;
      } catch(e) {}

      const newCommitRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/commits`, {
          method: 'POST', headers, body: JSON.stringify({ message: commitMessage, tree: newTreeData.sha, parents: [baseSha] })
      });
      const newCommitData = await newCommitRes.json();

      await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/git/refs/heads/${branchName}`, {
          method: 'PATCH', headers, body: JSON.stringify({ sha: newCommitData.sha })
      });

      if (isNewBranch) {
          const prRes = await fetch(`https://api.github.com/repos/${repoOwner}/${repoName}/pulls`, {
              method: 'POST', headers, body: JSON.stringify({ title: `Sovereign AI: ${branchName}`, head: branchName, base: "main", body: "Auto-generated AI modifications." })
          });
          const prData = await prRes.json();
          setActivePR({ branch: branchName, number: prData.number, lastErrorLog: "", isFixing: false, lastCommitSha: newCommitData.sha });
          addLog(`🟢 <b>PR #${prData.number} Erstellt!</b>`, "success");
      } else {
          setActivePR(p => ({ ...p, lastCommitSha: newCommitData.sha }));
          addLog(`🟢 <b>Änderungen an PR #${activePR.number} gepusht!</b>`, "success");
      }
      
      setBatchFiles([]);
    } catch(err: any) {
      logPersistentError(err, 'handlePush');
      addLog(`<b>Push Error:</b> ${err.message}`, "error");
    } finally {
      setIsProcessing(false);
    }
  };

  const getLogClasses = (type: string) => {
    switch(type) {
      case 'error': return 'bg-red-50 border-red-200 text-red-800';
      case 'success': return 'bg-green-50 border-green-200 text-green-800';
      case 'warning': return 'bg-amber-50 border-amber-200 text-amber-800';
      case 'idea': return 'bg-indigo-50 border-indigo-200 text-indigo-900';
      case 'info': return 'bg-blue-50 border-blue-200 text-blue-900';
      default: return 'bg-stone-50 border-stone-200 text-stone-800';
    }
  };

  return (
    <div className="w-full h-[100dvh] flex flex-col font-sans bg-[#f3f3f2] text-stone-900 overflow-hidden text-sm selection:bg-indigo-200 selection:text-indigo-900 animate-fade-in">
      
      {/* Header */}
      <header className="h-14 bg-white/80 backdrop-blur-xl border-b border-stone-200/60 flex items-center justify-between px-4 shrink-0 shadow-[0_4px_30px_rgba(0,0,0,0.03)] z-50">
        <div>
          <h1 className="text-sm font-bold tracking-tight">SOVEREIGN<span className="text-indigo-600">_STUDIO</span></h1>
          <div className="text-[9px] font-bold text-indigo-600 uppercase tracking-widest">Auto-Resolver v3.0.0</div>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full text-[10px] font-black tracking-wider shadow-sm mr-2 transition-all hover:shadow-md hover:bg-emerald-100/80 cursor-default" title="Hybrid API Canvas Auto-Auth verbunden">
             <div className="relative flex h-2 w-2">
               <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
               <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
             </div>
             CANVAS AUTO-AUTH
          </div>
          <button onClick={() => setShowPrivacy(true)} className="px-3 py-1.5 bg-stone-100 border border-stone-200 text-stone-600 rounded text-[10px] font-bold hover:bg-stone-200 transition-colors flex items-center gap-1">
             <Info size={12} /> DATENSCHUTZ
          </button>
          <button onClick={handleCleanup} className="px-3 py-1.5 bg-rose-50 border border-rose-200 text-rose-700 rounded text-[10px] font-bold hover:bg-rose-100 transition-colors flex items-center gap-1">
            <Trash2 size={12} /> CLEANUP
          </button>
          <button onClick={fetchRepoTree} disabled={loadingTree} className="px-3 py-1.5 bg-stone-100 border border-stone-200 rounded text-[10px] font-bold hover:bg-stone-200 transition-colors flex items-center gap-1 disabled:opacity-50">
            <RefreshCw size={12} className={loadingTree ? "animate-spin" : ""} /> {loadingTree ? "LADEN..." : "REFRESH"}
          </button>
        </div>
      </header>

      {/* Config Bar */}
      <div className="h-12 bg-stone-50 border-b border-stone-200 flex items-center justify-between px-4 shrink-0 text-xs overflow-x-auto gap-4 hide-scrollbar">
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1"><Github size={12}/> Repo:</span>
          <input 
            type="text" 
            value={repoUrl} 
            onChange={(e) => setRepoUrl(e.target.value)}
            className="text-xs px-2 py-1 border border-stone-300 rounded w-64 focus:outline-none focus:border-indigo-500 bg-white"
          />
          <button onClick={handleRepoChange} className="px-3 py-1 bg-indigo-600 text-white font-bold rounded hover:bg-indigo-700 transition-colors text-[10px] uppercase">
            Laden
          </button>
        </div>
        <div className="flex items-center gap-3 shrink-0" title="Datenschutz-Hinweis: APIs-Schlüssel werden ausschließlich lokal auf deinem Gerät (localStorage) gespeichert und nur für direkte, sichere HTTPS-Verbindungen zu GitHub und Google APIs verwendet. Es findet keine externe Erfassung oder Speicherung durch diese App statt.">
          <div className="flex items-center gap-2">
            <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1 cursor-help"><Shield size={12}/> GH PAT:</span>
            <input 
              type="password" 
              value={ghPat}
              onChange={(e) => handleGhPatChange(e.target.value)}
              placeholder="ghp_..." 
              className="text-xs px-2 py-1 border border-stone-300 rounded w-40 focus:outline-none focus:border-indigo-500 bg-white"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-stone-500 uppercase text-[10px] flex items-center gap-1 cursor-help"><Key size={12}/> Gemini:</span>
            <input 
              type="password" 
              value={geminiKey}
              onChange={(e) => handleGeminiKeyChange(e.target.value)}
              placeholder="API-Schlüssel eingeben..." 
              className="text-xs px-2 py-1 border border-stone-300 rounded w-48 focus:outline-none focus:border-indigo-500 bg-white"
            />
          </div>
        </div>
      </div>

      {/* Main Area */}
      <main className="flex-1 flex overflow-hidden relative">
        
        {/* TAB: EXPLORER & ARCHITECT */}
        <div className={`${activeTab === 'explorer' ? 'flex' : 'hidden'} lg:flex flex-col lg:w-80 shrink-0 border-r border-stone-200/60 glass-panel h-full pb-14 lg:pb-0 z-10 shadow-[4px_0_24px_rgba(0,0,0,0.02)]`}>
          
          <div className="p-3 bg-indigo-50 border-b border-indigo-200 shrink-0 shadow-sm">
            <h3 className="text-[11px] font-black text-indigo-800 mb-1 flex justify-between items-center">
              <span className="flex items-center gap-1"><RefreshCw size={12}/> PR AUTO-RESOLVER</span>
              <span className="px-2 py-0.5 rounded-full bg-indigo-200 text-indigo-800 text-[9px] uppercase">
                {activePR.number ? `PR #${activePR.number}` : "Kein aktiver PR"}
              </span>
            </h3>
            <div className="text-[10px] text-indigo-700 mb-2">
              Ziel-Branch: <span className="font-mono font-bold">{activePR.branch || "-"}</span>
            </div>
            
            <div className="flex gap-2">
              <button disabled className="flex-1 bg-indigo-600 disabled:opacity-50 text-white py-1.5 rounded text-[10px] font-bold uppercase transition-colors">
                CI PRÜFEN
              </button>
            </div>
          </div>

          <div className="p-3 bg-stone-50 border-b border-stone-200 shrink-0">
            <h3 className="text-[11px] font-bold text-stone-700 mb-2 flex items-center gap-1">
              <Sparkles size={12}/> ARCHITECT BLUEPRINT
            </h3>
            <textarea 
              value={architectInput}
              onChange={(e) => setArchitectInput(e.target.value)}
              rows={3} 
              className="w-full p-2 text-[11px] border border-stone-300 rounded focus:outline-none focus:border-indigo-500 resize-none shadow-inner" 
              placeholder="Beschreibe Task..."
            />
            <div className="flex gap-2 mt-2">
              <button 
                onClick={() => runArchitect()}
                disabled={isProcessing}
                className="flex-1 bg-stone-800 disabled:opacity-70 hover:bg-black text-white py-1.5 rounded-lg text-[11px] font-bold uppercase transition-all shadow-sm hover:shadow-md flex items-center justify-center gap-1 hover-lift"
              >
                {isProcessing ? "LÄUFT..." : "GENERIERE"}
              </button>
              <button 
                onClick={suggestIdeas}
                disabled={isProcessing}
                className="shrink-0 bg-yellow-100 hover:bg-yellow-200 border border-yellow-300 text-yellow-800 px-3 py-1.5 rounded-lg text-[11px] font-bold uppercase transition-all shadow-sm hover:shadow-md hover-lift"
                title="KI-Vorschläge basierend auf Repository generieren"
              >
                ✨ IDEEN
              </button>
            </div>
            
            {!isPro ? (
               <div className="mt-3 bg-white p-2 rounded-lg border border-stone-200">
                 <div className="flex justify-between items-center mb-1">
                   <span className="text-[10px] font-bold text-stone-600">Free Limits</span>
                   <button onClick={() => setShowPaywall(true)} className="text-[9px] font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 px-2 py-0.5 rounded-full transition-colors">PRO FREISCHALTEN</button>
                 </div>
                 
                 <div className="space-y-2 mt-2">
                   <div>
                     <div className="flex justify-between text-[9px] text-stone-500 mb-0.5">
                       <span>PR Auto-Resolver</span>
                       <span>{prRuns} / 15</span>
                     </div>
                     <div className="w-full bg-stone-100 rounded-full h-1.5 overflow-hidden">
                       <div className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${Math.min(100, (prRuns / 15) * 100)}%` }}></div>
                     </div>
                   </div>
                   
                   <div>
                     <div className="flex justify-between text-[9px] text-stone-500 mb-0.5">
                       <span>Ideen-Generator</span>
                       <span>{ideaRuns} / 6</span>
                     </div>
                     <div className="w-full bg-stone-100 rounded-full h-1.5 overflow-hidden">
                       <div className="bg-amber-400 h-1.5 rounded-full transition-all duration-500" style={{ width: `${Math.min(100, (ideaRuns / 6) * 100)}%` }}></div>
                     </div>
                   </div>
                 </div>
               </div>
            ) : (
                <div className="mt-3 bg-indigo-50 px-3 py-3 rounded-xl border border-indigo-200/50 shadow-sm flex flex-col gap-2 relative overflow-hidden group">
                   <div className="absolute -top-4 -right-4 p-2 opacity-5 group-hover:opacity-10 transition-opacity duration-300">
                     <Shield size={64} />
                   </div>
                   <div className="flex items-center justify-between z-10">
                     <span className="text-[10px] font-black text-indigo-900 flex items-center gap-1.5 uppercase tracking-wider"><Sparkles size={12} className="text-indigo-600"/> PRO AKTIV</span>
                     <span className="text-[9px] font-bold bg-indigo-200/50 text-indigo-800 px-1.5 py-0.5 rounded shadow-sm">UNLIMITED</span>
                   </div>
                   <div className="text-[9.5px] text-indigo-700/80 leading-relaxed z-10 pr-4 mt-1 border-t border-indigo-200/50 pt-2">
                     <b>Große Dateien Feature:</b> Du kannst nun Dateien über 500KB im intelligenten Editor laden und bearbeiten. Limits wurden vollständig aufgehoben!
                   </div>
                </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto bg-white custom-scrollbar">
             {loadingTree ? (
               <div className="p-4 text-xs flex flex-col items-center justify-center h-full">
                  <div className="w-full flex-1 flex flex-col gap-3 py-4 max-w-sm">
                    <div className="flex items-center justify-center mb-4 gap-2 text-stone-400 font-bold uppercase tracking-wide text-[10px]">
                      <RefreshCw size={14} className="animate-spin text-stone-400" />
                      Lade Repository Struktur...
                    </div>
                    {[...Array(12)].map((_, i) => (
                      <div key={i} className="flex items-center gap-3">
                         <div className="w-4 h-4 rounded bg-tree-skeleton shrink-0"></div>
                         <div className={`h-3 rounded bg-tree-skeleton ${i % 4 === 0 ? 'w-full' : i % 3 === 0 ? 'w-2/3' : i % 2 === 0 ? 'w-4/5' : 'w-1/2'}`} style={{ animationDelay: `${i * 0.1}s` }}></div>
                     </div>
                    ))}
                  </div>
               </div>
             ) : treeError ? (
               <div className="p-4 text-xs text-red-500 text-center font-bold">{treeError}</div>
             ) : (
               <div className="select-none">
                  {fullTree.slice(0, 200).map((file) => {
                    const isActive = activeFile?.path === file.path;
                    const isImportant = file.path.match(/package\.json$|\.tsx?$|\.jsx?$/i);
                    const icon = file.path.includes('.json') ? '📦' : file.path.includes('.ts') ? '🟦' : file.path.includes('.js') ? '🟨' : '📄';
                    
                    return (
                      <div 
                        key={file.sha + file.path}
                        onClick={() => loadFile(file)}
                        className={`px-4 py-2 border-b border-stone-100 text-[13px] flex items-center gap-2 cursor-pointer transition-colors ${isActive ? 'bg-indigo-600 text-white font-bold shadow-md' : 'hover:bg-stone-50 text-stone-600'}`}
                      >
                         <span>{icon}</span>
                         <span className={`truncate ${isImportant && !isActive ? 'font-medium' : ''}`}>{file.path}</span>
                      </div>
                    )
                  })}
               </div>
             )}
          </div>
        </div>

        {/* TAB: EDITOR & BATCH */}
        <div className={`${activeTab === 'editor' ? 'flex' : 'hidden'} lg:flex flex-1 flex-col min-w-0 bg-stone-50/70 pb-14 lg:pb-0 relative`}>
          
          <div className="h-10 bg-white/60 backdrop-blur-md border-b border-stone-200/60 flex items-center px-3 shrink-0 overflow-x-auto hide-scrollbar select-none shadow-[0_2px_10px_rgba(0,0,0,0.02)] z-10">
             <span className="text-[11px] font-mono text-stone-600 italic truncate mr-4 max-w-[200px]">
               {activeFile ? activeFile.path : "Keine Datei gewählt"}
             </span>
          </div>

          <div className="flex-1 p-2 lg:p-4 overflow-hidden flex flex-col relative">
            <div className={`bg-[#0c0a09] font-mono flex-1 rounded-2xl shadow-[inset_0_2px_20px_rgba(0,0,0,0.5),0_4px_12px_rgba(0,0,0,0.1)] relative overflow-hidden flex flex-col border border-stone-800 ${isProcessing ? 'compile-active' : ''}`}>
               {loadingFile || isProcessing ? (
                 <div className="flex-1 flex flex-col bg-[#0c0a09] relative overflow-hidden">
                    <div className="scanline"></div>
                    <div className="p-4 flex gap-4 h-full relative z-10 leading-relaxed font-mono">
                      <div className="w-8 shrink-0 flex flex-col items-end gap-[14px] text-stone-700 pt-[1px] border-r border-[#292524] pr-2 select-none opacity-50">
                         {[...Array(20)].map((_, i) => (
                            <span key={i} className="text-[12px] h-[12px] leading-none">{i + 1}</span>
                         ))}
                      </div>
                      <div className="flex-1 flex flex-col pt-0 gap-[14px]">
                        <div className="flex items-center gap-2 text-indigo-400 text-xs font-black tracking-widest uppercase mb-2 animate-pulse w-max bg-indigo-500/10 px-3 py-1 rounded">
                           <RefreshCw size={14} className="animate-spin" /> {isProcessing ? "PROCESSING DATA..." : "DECRYPTING SOURCE..."}
                        </div>
                        {[...Array(15)].map((_, i) => (
                          <div key={i} className={`h-[12px] rounded bg-cyber-skeleton ${i % 5 === 0 ? 'w-1/2' : i % 4 === 0 ? 'w-2/3' : i % 3 === 0 ? 'w-[80%]' : i % 2 === 0 ? 'w-1/3' : 'w-[90%]'}`} style={{ animationDelay: `${i * 0.05}s`, opacity: Math.max(0.1, 1 - i * 0.05) }}></div>
                        ))}
                      </div>
                    </div>
                 </div>
               ) : (
                 <div className="flex-1 auto-rows-max overflow-auto text-[12px] text-stone-300 relative h-full">
                   {!activeFile ? (
                      <div className="text-stone-500 italic p-4">// Wähle eine Datei im Explorer, um den Code zu laden.</div>
                   ) : !isPro ? (
                      <div className="flex flex-col items-center justify-center p-8 text-center h-full max-w-lg mx-auto animate-slide-up">
                         <div className="w-16 h-16 bg-white/5 rounded-2xl flex items-center justify-center shadow-lg border border-white/5 mb-6 hover-lift transition-transform">
                           <Shield size={32} className="text-indigo-400" />
                         </div>
                         <h3 className="text-lg font-black text-white mb-3">Premium Editor gesperrt</h3>
                         <p className="text-stone-400 text-sm mb-8 leading-relaxed">
                            Die Monaco Editor Ansicht sowie die Behebung von fehlerhaften Dateien sind Premium-Funktionen.
                            Mit einem Upgrade schaltest du den kompletten <b className="text-white">Full-Workflow</b> frei: Von der Kreation, Linting, Fehlerbehebung über Datenbankanbindung bis hin zum Deployment.
                         </p>
                         
                         <button 
                           onClick={() => setShowPaywall(true)}
                           className="bg-[#FFE01B] hover:bg-[#F2D000] text-black font-black uppercase text-[11px] tracking-wider py-4 px-8 rounded-full shadow-[0_4px_14px_rgba(255,224,27,0.4)] transition-all hover:scale-105 active:scale-95 flex items-center gap-2 hover-lift"
                         >
                           <span>💌 Mit Mailchimp fortsetzen & Fixen</span>
                         </button>

                         <p className="text-stone-600 text-[10px] mt-6 font-medium">Auch Datenblatt-Uploads (PDF) werden nach dem Upgrade freigeschaltet.</p>
                      </div>
                   ) : (
                      <div className="pointer-events-auto h-full w-full flex flex-col">
                        {fileTooLarge && (
                           <div className="bg-yellow-900/40 text-yellow-500 text-[10px] p-2 border-b border-yellow-700/50 flex items-center justify-between font-bold tracking-wider shrink-0 uppercase">
                              <div className="flex items-center gap-2">
                                ⚠️ Datei zu groß &gt;500KB. {isPro ? 'Vorschau-Modus aktiv.' : 'Nur für Pro-Nutzer.'}
                              </div>
                              {!isPro && (
                                 <button onClick={() => setShowPaywall(true)} className="ml-2 bg-yellow-500/20 hover:bg-yellow-500/30 text-yellow-400 px-2 py-0.5 rounded transition-colors border border-yellow-500/30 shadow-sm cursor-pointer pointer-events-auto">
                                    PRO FREISCHALTEN
                                 </button>
                              )}
                           </div>
                        )}
                        <div className="flex-1 min-h-0 relative">
                           <Editor
                              height="100%"
                              defaultLanguage={activeFile.path.endsWith('.ts') || activeFile.path.endsWith('.tsx') ? 'typescript' : 
                                             activeFile.path.endsWith('.js') || activeFile.path.endsWith('.jsx') ? 'javascript' : 
                                             activeFile.path.endsWith('.json') ? 'json' :
                                             activeFile.path.endsWith('.css') ? 'css' :
                                             activeFile.path.endsWith('.html') ? 'html' :
                                             activeFile.path.endsWith('.md') ? 'markdown' : 'plaintext'}
                              theme="vs-dark"
                              value={fileContent}
                              options={{
                                 readOnly: fileTooLarge || isProcessing,
                                 minimap: { enabled: false },
                                 fontSize: 12,
                                 fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                                 padding: { top: 16 }
                              }}
                              onChange={(value) => {
                                 if (value !== undefined && !fileTooLarge) {
                                    setFileContent(value);
                                 }
                              }}
                           />
                        </div>
                      </div>
                   )}
                 </div>
               )}
            </div>
          </div>

          {batchFiles.length > 0 && (
            <div className="border-t border-indigo-200 bg-white shrink-0 flex flex-col max-h-48 z-20 shadow-[0_-4px_24px_rgba(0,0,0,0.05)]">
              <div className="px-3 py-2 bg-indigo-50/80 border-b border-indigo-100 flex items-center justify-between">
                 <span className="text-[10px] font-bold text-indigo-800 uppercase flex items-center gap-1.5">
                   <Code2 size={12} />
                   KI Vorschläge (Pending)
                 </span>
                 <span className="text-[9px] bg-indigo-200 text-indigo-800 font-bold px-2 py-0.5 rounded-full">{batchFiles.length} Aktionen</span>
              </div>
              <div className="overflow-y-auto p-2 flex flex-col gap-1 custom-scrollbar">
                 {batchFiles.map((bf, idx) => (
                    <div key={idx} 
                         onClick={() => {
                           setActiveFile({ path: bf.path, type: 'blob', mode: '100644', sha: '' });
                           setFileContent(bf.content || '');
                           setFileTooLarge(false);
                           addLog(`👁️ Vorschau für <code>${bf.path}</code> geöffnet.`, "info");
                         }}
                         className="flex items-center justify-between p-2.5 rounded-lg hover:bg-stone-50 border border-transparent hover:border-stone-200 cursor-pointer transition-all group hover-lift">
                       <div className="flex items-center gap-2.5 truncate">
                         {bf.isDelete ? <Trash2 size={14} className="text-red-500 shrink-0" /> : <FileText size={14} className="text-indigo-500 shrink-0" />}
                         <span className="text-[11px] font-mono font-medium text-stone-700 truncate">{bf.path} {bf.isDelete ? '(Löschen)' : ''}</span>
                       </div>
                       <span className="text-[9px] font-bold text-indigo-500 bg-indigo-50 px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity uppercase tracking-wider">Vorschau</span>
                    </div>
                 ))}
              </div>
            </div>
          )}

          <div className="h-16 border-t border-indigo-200 px-4 flex items-center justify-between bg-indigo-50 shrink-0">
              <div className="truncate mr-4 flex-1">
                  <h4 className="text-[10px] font-black text-indigo-800 uppercase">Sicherer Push</h4>
                  <p className="text-[10px] text-indigo-600 italic truncate">{batchFiles.length} Änderungen in Queue.</p>
              </div>
              <button 
                onClick={handlePush}
                disabled={batchFiles.length === 0 || isProcessing}
                className="shrink-0 flex items-center gap-1 px-4 py-2 bg-indigo-600 text-white rounded-lg font-bold text-[10px] uppercase disabled:opacity-50 disabled:cursor-not-allowed hover:bg-indigo-700 transition-all shadow-sm"
              >
                  {isProcessing ? <RefreshCw size={12} className="animate-spin"/> : <Shield size={12}/>} 
                  {isProcessing ? "PUSHING..." : "PUSH AS PR"}
              </button>
          </div>
        </div>

        {/* TAB: CHAT LOG */}
        <div className={`${activeTab === 'chat' ? 'flex' : 'hidden'} lg:flex flex-col lg:w-[350px] shrink-0 border-l border-stone-200/60 glass-panel h-full pb-14 lg:pb-0 z-10 shadow-[-4px_0_24px_rgba(0,0,0,0.02)]`}>
           <div className="p-3 bg-stone-50 border-b border-stone-200 text-[11px] font-bold text-stone-800 flex items-center gap-2 justify-between shrink-0">
               <div><span className="text-indigo-600">✨</span> SYSTEM LOG</div>
               <button onClick={() => setLogs([])} className="text-[9px] text-stone-400 hover:text-stone-600 uppercase">Leeren</button>
           </div>
           
           <div className="flex-1 overflow-y-auto p-4 bg-white text-[11px] custom-scrollbar flex flex-col gap-3">
              {logs.map((log) => (
                <div key={log.id} className={`p-3 rounded-xl rounded-tl-none border shadow-sm leading-relaxed break-words ${getLogClasses(log.type)}`} dangerouslySetInnerHTML={{ __html: log.text }} />
              ))}
              <div ref={logsEndRef} />
           </div>
        </div>

      </main>

      {/* Mobile Navigation */}
      <nav className="lg:hidden h-14 bg-white border-t border-stone-200 flex items-center justify-around shrink-0 z-50 shadow-[0_-2px_10px_rgba(0,0,0,0.05)] absolute bottom-0 left-0 w-full select-none">
         <button onClick={() => setActiveTab('explorer')} className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'explorer' ? 'text-indigo-600' : 'text-stone-400'}`}>
            <Folder size={18} />
            <span className="text-[9px] font-bold uppercase tracking-wider">Planung</span>
         </button>
         <button onClick={() => setActiveTab('editor')} className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'editor' ? 'text-indigo-600' : 'text-stone-400'}`}>
            <Code2 size={18} />
            <span className="text-[9px] font-bold uppercase tracking-wider">Code</span>
         </button>
         <button onClick={() => setActiveTab('chat')} className={`flex flex-col items-center gap-1 w-1/3 py-2 transition-colors ${activeTab === 'chat' ? 'text-indigo-600' : 'text-stone-400'}`}>
            <MessageSquare size={18} />
            <span className="text-[9px] font-bold uppercase tracking-wider">Log</span>
         </button>
      </nav>
      
      {/* Modals */}
      <PaywallModal 
        show={showPaywall} 
        onClose={() => setShowPaywall(false)} 
        onUpgrade={() => {
           setIsPro(true);
           localStorage.setItem('ss_is_pro', 'true');
           setShowPaywall(false);
           addLog("🎉 <b>Sovereign Studio Pro freigeschaltet!</b> Vielen Dank für die Unterstützung und viel Erfolg beim Entwickeln.", "success");
        }} 
      />
      
      <PrivacyModal 
        show={showPrivacy} 
        onClose={() => setShowPrivacy(false)} 
      />

      <style dangerouslySetInnerHTML={{__html:`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: #d6d3d1; border-radius: 4px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #a8a29e; }
        .hide-scrollbar::-webkit-scrollbar { display: none; }
        .hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
      `}}/>
    </div>
  );
}
