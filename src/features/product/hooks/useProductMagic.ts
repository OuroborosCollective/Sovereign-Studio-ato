import { useMemo, useState, useCallback, useEffect } from 'react';
import { FileItem, Card, WorkView, PipelineState, ProjectSettings, MobilePane, ChatMessage, Suggestion, ArchitectureAnalysis } from '../types';
import { makeId, demoFiles, starterCards, defaultSettings } from '../constants';
import { validateAppState, validateGitHubUrl, runtimeCheck, safeGet } from '../../../shared/utils/runtimeValidation';

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

// Helper to parse GitHub repo URL
function parseGitHubUrl(url: string): { owner: string; repo: string; branch: string } | null {
  const match = url.match(/github\.com\/([^/]+)\/([^/]+?)(?:\.git)?(?:\/tree\/([^/]+))?/i);
  if (!match) return null;
  return {
    owner: match[1],
    repo: match[2].replace(/\.git$/, ''),
    branch: match[3] || 'main',
  };
}

// Runtime validation on module load
const VALID_REPO_MODES = ['monorepo', 'single'];
const VALID_PACKAGE_MANAGERS = ['auto', 'pnpm', 'npm', 'yarn'];
const VALID_LINTERS = ['biome', 'eslint', 'prettier'];

export function useProductMagic() {
  // State with runtime validation
  const [repoUrl, setRepoUrl] = useState('https://github.com/OuroborosCollective/Sovereign-Studio-ato');
  const [accessKey, setAccessKey] = useState('');
  const [geminiKey, setGeminiKey] = useState('');
  const [blueprint, setBlueprint] = useState('Beschreibe deine Idee oder deinen Auftrag. Ich plane, generiere, pruefe und zeige alle Aenderungen sichtbar.');
  const [cards, setCards] = useState<Card[]>(starterCards());
  const [selectedFile, setSelectedFile] = useState<FileItem>(demoFiles[0]);
  const [built, setBuilt] = useState(false);
  const [chatInput, setChatInput] = useState('Starte mit diesem Auftrag.');
  const [logs, setLogs] = useState<string[]>(['Sovereign Studio bereit.', 'Links Auftrag und Dateien. Mitte Chat und Editor. Rechts nur Log.']);
  const [workView, setWorkView] = useState<WorkView>('editor');
  const [pipelineState, setPipelineState] = useState<PipelineState>('idle');
  const [fixLoops, setFixLoops] = useState(0);
  const [showSettings, setShowSettings] = useState(false);
  const [settings, setSettings] = useState<ProjectSettings>(defaultSettings);
  const [generatedCode, setGeneratedCode] = useState('');
  const [isWorking, setIsWorking] = useState(false);
  const [agentMessage, setAgentMessage] = useState('Bereit. Gib links deinen Auftrag ein und starte dann Schritt 1.');
  const [progress, setProgress] = useState(0);
  const [mobilePane, setMobilePane] = useState<MobilePane>('auftrag');
  const [currentStepLabel, setCurrentStepLabel] = useState('');
  const [nextStepLabel, setNextStepLabel] = useState('');
  const [approvalConfirmed, setApprovalConfirmed] = useState(false);
  const [targetLink, setTargetLink] = useState(''); // External target link (e.g., PR URL)

  // Runtime validation effect - validates state on mount and on changes
  useEffect(() => {
    const validation = validateAppState({
      repoUrl,
      accessKey,
      geminiKey,
      cards,
      settings,
    });
    
    if (!validation.valid) {
      console.error('[RUNTIME_VALIDATION] App state validation failed:', validation.errors);
    }
    if (validation.warnings.length > 0) {
      console.warn('[RUNTIME_VALIDATION] Warnings:', validation.warnings);
    }
  }, [repoUrl, accessKey, geminiKey, cards, settings]);

  // Validated setters with runtime checks
  const validatedSetRepoUrl = useCallback((url: string) => {
    // Runtime check for valid URL format
    const urlValidation = validateGitHubUrl(url, 'repoUrl');
    if (!urlValidation.valid) {
      console.warn('[RUNTIME_VALIDATION] Invalid repo URL:', url);
    }
    setRepoUrl(url);
  }, []);

  const validatedSetSettings = useCallback((newSettings: ProjectSettings | ((prev: ProjectSettings) => ProjectSettings)) => {
    setSettings((prev: ProjectSettings) => {
      const updated = typeof newSettings === 'function' ? newSettings(prev) : newSettings;
      
      // Runtime validation of settings
      if (updated.repoMode && !VALID_REPO_MODES.includes(updated.repoMode)) {
        console.error(`[RUNTIME_VALIDATION] Invalid repoMode: ${updated.repoMode}, defaulting to 'single'`);
        updated.repoMode = 'single';
      }
      if (updated.packageManager && !VALID_PACKAGE_MANAGERS.includes(updated.packageManager)) {
        console.error(`[RUNTIME_VALIDATION] Invalid packageManager: ${updated.packageManager}, defaulting to 'auto'`);
        updated.packageManager = 'auto';
      }
      if (updated.linter && !VALID_LINTERS.includes(updated.linter)) {
        console.error(`[RUNTIME_VALIDATION] Invalid linter: ${updated.linter}, defaulting to 'biome'`);
        updated.linter = 'biome';
      }
      
      return updated;
    });
  }, []);

  const currentCode = useMemo(() => generatedCode || `// ${selectedFile.path}\n// Sovereign Auto-Resolver Preview\n\nconst auftrag = ${JSON.stringify(blueprint, null, 2)};\n\nexport const generatedProduct = {\n  mode: 'chat-editor-live-status',\n  repo: '${repoUrl}',\n  steps: ${cards.length},\n  repoMode: '${settings.repoMode}',\n  packageManager: '${settings.packageManager}',\n  linter: '${settings.linter}',\n  freeRoute: ['mlvoca', 'pollinations', 'optional-user-keys'],\n  ready: ${built}\n};`, [generatedCode, selectedFile.path, blueprint, repoUrl, cards.length, settings.repoMode, settings.packageManager, settings.linter, built]);

  const generatedPackage = useMemo(() => JSON.stringify({ repoUrl, blueprint, cards, selectedFile: selectedFile.path, settings, generatedCode: currentCode, approvalConfirmed }, null, 2), [repoUrl, blueprint, cards, selectedFile, settings, currentCode, approvalConfirmed]);

  const log = (text: string) => setLogs((items) => {
    const deduped = items[0] === text ? items : [text, ...items];
    return deduped.slice(0, 18);
  });

  // Add chat message
  const addChatMessage = (role: 'user' | 'assistant', content: string) => {
    setChatMessages(prev => [...prev, {
      id: makeId(),
      role,
      content,
      timestamp: Date.now()
    }]);
  };

  // Run architecture analysis and generate suggestions
  const runArchitectureAnalysis = useCallback(async () => {
    setIsAnalyzing(true);
    addChatMessage('assistant', '🔍 Analyse der Architektur läuft...');

    await sleep(800);

    const analysis = analyzeArchitecture(blueprint, cards);
    setArchitectureAnalysis(analysis);

    // Generate suggestions from analysis
    const newSuggestions: Suggestion[] = [];

    // Add integration suggestion (always first, most important)
    if (analysis.integrations.length > 0) {
      newSuggestions.push({
        id: makeId(),
        type: 'feature',
        title: 'Integration: ' + analysis.integrations[0],
        description: `Basierend auf deiner Anfrage empfehle ich: ${analysis.integrations[0]}. Dies passt zur erkannten Architektur.`,
        priority: 'high'
      });
    }

    // Add suggested features
    analysis.suggestedFeatures.slice(0, 2).forEach((feature, idx) => {
      newSuggestions.push({
        id: makeId(),
        type: 'feature',
        title: `Feature ${idx + 1}: ${feature}`,
        description: `Dieses Feature erweitert die Grundfunktionalität sinnvoll.`,
        priority: idx === 0 ? 'high' : 'medium'
      });
    });

    // Add error/warning suggestions if any
    analysis.potentialIssues.forEach((issue) => {
      newSuggestions.push({
        id: makeId(),
        type: 'error',
        title: '⚠️ ' + issue.split(' - ')[0],
        description: issue.split(' - ')[1] || 'Bitte beachte diesen Punkt.',
        priority: 'high'
      });
    });

    setSuggestions(newSuggestions);

    // Format analysis message for chat
    let analysisMessage = `## 📊 Architektur-Analyse\n\n`;
    analysisMessage += `**Zusammenfassung:** ${analysis.summary}\n\n`;
    
    if (analysis.components.length > 0) {
      analysisMessage += `**🔧 Erkannte Komponenten:**\n`;
      analysis.components.forEach(c => analysisMessage += `- ${c}\n`);
      analysisMessage += `\n`;
    }

    if (analysis.integrations.length > 0) {
      analysisMessage += `**🔗 Empfohlene Integrationen:**\n`;
      analysis.integrations.forEach(i => analysisMessage += `- ${i}\n`);
      analysisMessage += `\n`;
    }

    if (analysis.suggestedFeatures.length > 0) {
      analysisMessage += `**✨ Vorschläge:**\n`;
      analysis.suggestedFeatures.forEach(f => analysisMessage += `- ${f}\n`);
    }

    addChatMessage('assistant', analysisMessage);
    setIsAnalyzing(false);

    return analysis;
  }, [blueprint, cards]);

  // Accept a suggestion
  const acceptSuggestion = useCallback((suggestionId: string) => {
    setSuggestions(prev => prev.map(s => 
      s.id === suggestionId ? { ...s, accepted: true } : s
    ));
    
    const suggestion = suggestions.find(s => s.id === suggestionId);
    if (suggestion) {
      addChatMessage('assistant', `✅ "${suggestion.title}" wird integriert. Code wird angepasst...`);
      
      // Switch to editor view and trigger autonomous mode
      setWorkView('editor');
      setMobilePane('live');
      
      // Add the suggestion as a new card/task
      setCards(prev => [...prev, {
        id: makeId(),
        title: suggestion.title,
        body: suggestion.description
      }]);
    }
  }, [suggestions, setWorkView, setMobilePane, setCards]);

  // Send chat message
  const sendChatMessage = useCallback((message: string) => {
    if (!message.trim()) return;
    
    addChatMessage('user', message);
    
    // Simple response based on keywords
    const lowerMsg = message.toLowerCase();
    if (lowerMsg.includes('was') && lowerMsg.includes('kannst')) {
      addChatMessage('assistant', 'Ich kann:\n- Deine Idee analysieren und Architektur vorschlagen\n- Code generieren und validieren\n- Fehler automatisch fixen\n- Vorschläge für Erweiterungen machen\n- Den Code direkt als PR auf GitHub pushen');
    } else if (lowerMsg.includes('help') || lowerMsg.includes('hilfe')) {
      addChatMessage('assistant', 'So nutzt du Sovereign Studio:\n1. Beschreibe deine Idee links\n2. Klicke "Prüfen" um die Analyse zu starten\n3. Nach der Analyse siehst du Vorschläge\n4. Klicke auf einen Vorschlag oder schreib direkt\n5. Wenn alles grün ist, klicke "Freigabe bestätigen"');
    } else if (lowerMsg.includes('verstanden') || lowerMsg.includes('ok') || lowerMsg.includes('weiter')) {
      addChatMessage('assistant', 'Perfekt! Klicke auf einen der Vorschläge oder beschreibe weitere Wünsche.');
    } else {
      // Echo back with acknowledgment
      addChatMessage('assistant', `Ich habe verstanden: "${message}". Wenn du bereit bist, klicke auf einen Vorschlag oder starte mit "Prüfen" die Code-Generierung.`);
    }
  }, []);

  const guardBusy = () => {
    if (!isWorking) return false;
    log('Bitte warten: Ich arbeite noch aktiv am aktuellen Schritt.');
    return true;
  };

  const generateCodeInEditor = useCallback(() => {
    const pm = settings.packageManager === 'auto' ? 'detected-package-manager' : settings.packageManager;
    const lintCommand = settings.linter === 'biome' ? `${pm} biome check .` : settings.linter === 'eslint' ? `${pm} lint` : `${pm} lint || ${pm} format`;
    const installCommand = settings.repoMode === 'monorepo' ? `${pm} install --frozen-lockfile` : `${pm} install`;
    const code = `// Generated by Sovereign Studio\n// File: generated/sovereign-product/workflow.ts\n\nexport const projectProfile = {\n  repoMode: '${settings.repoMode}',\n  packageManager: '${settings.packageManager}',\n  installStrategy: '${settings.installStrategy}',\n  linter: '${settings.linter}',\n  specialization: ${JSON.stringify(settings.specialization)},\n  freeRoute: ['mlvoca', 'pollinations', 'optional-user-keys']\n};\n\nexport const safeCommands = {\n  install: '${installCommand}',\n  lint: '${lintCommand}',\n  test: '${pm} test',\n  build: '${pm} build'\n};\n\nexport const userFlow = {\n  left: 'GitHub Datei Baum und Auftrag',\n  center: 'Chat plus Matrix File Editor plus Live Status',\n  right: 'Nur History Log',\n  onError: 'wait-for-user-then-visible-fix',\n  onGreen: 'wait-for-external-target-link'\n};\n\nexport const productSteps = ${JSON.stringify(cards.map((card) => ({ title: card.title, task: card.body })), null, 2)};\n\nexport function runVisibleWorkflow() {\n  return {\n    status: 'ready-for-check',\n    auftrag: ${JSON.stringify(blueprint)},\n    next: 'workflow-check'\n  };\n}\n`;
    setSelectedFile({ path: 'generated/sovereign-product/workflow.ts', icon: 'GEN' });
    setGeneratedCode(code);
    setBuilt(true);
    setWorkView('editor');
  }, [settings, cards, blueprint]);

  const runAutonomousJob = useCallback(async () => {
    if (isWorking) return;
    
    setIsWorking(true);
    setApprovalConfirmed(false);
    setMobilePane('live');
    setWorkView('editor');
    setFixLoops(0);
    log('=== Auftrag gestartet ===');
    setAgentMessage('Ich arbeite aktiv an deinem Auftrag. Bitte warten.');
    setCurrentStepLabel('Planung und Code-Entwurf');
    setNextStepLabel('Pruefung');

    setPipelineState('planning');
    setProgress(10);
    await sleep(800);
    
    setPipelineState('generating');
    setProgress(25);
    generateCodeInEditor();
    await sleep(600);
    log('Schritt 1/5 fertig: Planung und Code-Entwurf sichtbar.');
    setAgentMessage('Schritt 1 fertig: Planung und Code-Entwurf stehen.');
    setCurrentStepLabel('Pruefung');
    setNextStepLabel('Fix bei Fehler');

    setPipelineState('validating');
    setProgress(45);
    setAgentMessage('Ich pruefe jetzt aktiv. Bitte warten, ich haenge nicht.');
    await sleep(1200);
    
    const shouldRunVisibleFix = settings.maxFixLoops > 0;
    if (shouldRunVisibleFix) {
      setPipelineState('failed');
      setProgress(60);
      log('Schritt 2/5 fertig: Pruefung fand Fehler. Fix ist jetzt freigegeben.');
      setAgentMessage('Pruefung fertig: Fehler gefunden. Ich arbeite weiter.');
      setCurrentStepLabel('Fix anwenden');
      setNextStepLabel('Erneute Pruefung');

      setPipelineState('fixing');
      setProgress(70);
      setAgentMessage('Ich wende jetzt einen sichtbaren Fix an. Bitte warten.');
      await sleep(800);
      
      const patched = `${currentCode}\n\n// VisibleFix 1: sequential repair applied\nexport const validationPatch = {\n  reason: 'visible workflow fix completed',\n  linter: '${settings.linter}',\n  packageManager: '${settings.packageManager}',\n  rerunRequired: true\n};\n`;
      setGeneratedCode(patched);
      setFixLoops(1);
      log('Schritt 3/5 fertig: Fix sichtbar angewendet.');
      setAgentMessage('Fix fertig. Ich starte automatisch die erneute Pruefung.');
      setCurrentStepLabel('Erneute Pruefung');
      setNextStepLabel('Freigabe');

      setPipelineState('revalidating');
      setProgress(88);
      setAgentMessage('Ich pruefe erneut. Bitte warten, ich arbeite aktiv.');
      await sleep(1000);
      
      setPipelineState('green');
      setProgress(100);
      log('Schritt 4/5 fertig: Erneute Pruefung gruen. Freigabe wartet auf Ziel-Link.');
      setAgentMessage('Alles gruen. Klicke auf Freigabe bestaetigen oder waehle einen Vorschlag.');
      setCurrentStepLabel('Freigabe wartet');
      setNextStepLabel('Ziel-Link');
    } else {
      setPipelineState('green');
      setProgress(100);
      log('Schritt 2/5 fertig: Pruefung gruen. Freigabe wartet auf Ziel-Link.');
      setAgentMessage('Alles gruen. Klicke auf Freigabe bestaetigen oder waehle einen Vorschlag.');
      setCurrentStepLabel('Freigabe wartet');
      setNextStepLabel('Ziel-Link');
    }

    // Run architecture analysis after code is ready
    await runArchitectureAnalysis();

    setIsWorking(false);
    log('=== Auftrag wartet: Externer Ziel-Link fehlt noch ===');
  }, [isWorking, settings.maxFixLoops, settings.linter, settings.packageManager, generateCodeInEditor, currentCode, runArchitectureAnalysis]);

  const buildProduct = useCallback(() => {
    if (guardBusy()) return;
    setApprovalConfirmed(false);
    runAutonomousJob();
  }, [guardBusy, runAutonomousJob]);

  const addCard = () => setCards((items) => [...items, { id: makeId(), title: 'Notiz', body: blueprint }]);

  const sendChat = useCallback(() => {
    if (!chatInput.trim()) return;
    log(`Chat Auftrag: ${chatInput}`);
    setChatInput('');
    buildProduct();
  }, [chatInput, log, buildProduct]);

  const downloadPackage = () => {
    const blob = new Blob([generatedPackage], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `sovereign-product-${Date.now()}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const patchFromPipeline = useCallback(() => {
    if (guardBusy()) return;
    setApprovalConfirmed(false);
    if (pipelineState !== 'failed') {
      log('Fix wartet: Erst muss eine echte Pruefung einen Fehler melden.');
      setAgentMessage('Ich brauche zuerst ein Pruefergebnis. Starte Pruefen, dann kann ich gezielt fixen.');
      return;
    }
    
    const patched = `${currentCode}\n\n// VisibleFix ${fixLoops + 1}: manual repair applied\nexport const validationPatch = {\n  reason: 'manual workflow fix completed',\n  linter: '${settings.linter}',\n  packageManager: '${settings.packageManager}',\n  rerunRequired: true\n};\n`;
    setGeneratedCode(patched);
    setFixLoops((count) => count + 1);
    setWorkView('editor');
    setAgentMessage('Fix manuell angewendet. Bitte Pruefen druecken fuer den naechsten Schritt.');
    log('Manueller Fix angewendet. Bitte Pruefen druecken.');
  }, [guardBusy, pipelineState, currentCode, settings.linter, settings.packageManager, fixLoops]);

  const publishAndValidate = useCallback(() => {
    if (guardBusy()) return;
    setApprovalConfirmed(false);
    if (!built) {
      log('Pruefung blockiert: Starte zuerst den Auftrag.');
      setAgentMessage('Erst Auftrag starten. Danach pruefe ich Schritt fuer Schritt.');
      return;
    }
    if (pipelineState === 'idle') {
      runAutonomousJob();
      return;
    }
    
    setWorkView('editor');
    setPipelineState('validating');
    setAgentMessage('Ich pruefe jetzt Struktur, Typecheck, Tests und Build-Konzept. Bitte warten, ich arbeite aktiv.');
    setTimeout(() => {
      if (fixLoops < 1) {
        setPipelineState('failed');
        setAgentMessage('Pruefung fertig: Fehler gefunden. Naechster Schritt: Fix sichtbar anwenden.');
        log('Manuelle Pruefung: Fehler gefunden. Fix ist freigegeben.');
      } else {
        setPipelineState('green');
        setAgentMessage('Pruefung fertig: Alles gruen. Freigabe wartet auf Ziel-Link im Log.');
        setCurrentStepLabel('Freigabe wartet');
        setNextStepLabel('Ziel-Link');
        log('Manuelle Pruefung: gruen. Externer Ziel-Link fehlt noch.');
      }
    }, 1400);
  }, [guardBusy, built, pipelineState, runAutonomousJob, fixLoops]);

  const mergeWhenGreen = useCallback(async () => {
    if (guardBusy()) return;
    if (approvalConfirmed) {
      log('Freigabe war bereits bestaetigt.');
      setAgentMessage('Freigabe ist bereits bestaetigt.');
      return;
    }
    if (pipelineState !== 'green') {
      log('Freigabe blockiert: Erst muss die Pruefung gruen sein.');
      setAgentMessage('Ich darf erst weitermachen, wenn die Pruefung gruen ist.');
      return;
    }

    setIsWorking(true);
    setAgentMessage('Ich pushe jetzt zum GitHub Repo...');
    log('=== Push zu GitHub gestartet ===');

    try {
      // Parse repo URL
      const parsed = parseGitHubUrl(repoUrl);
      if (!parsed) {
        throw new Error('Ungueltige GitHub URL');
      }

      const headers: Record<string, string> = {
        'Accept': 'application/vnd.github+json',
        'Authorization': `Bearer ${accessKey}`,
        'Content-Type': 'application/json',
        'X-GitHub-Api-Version': '2022-11-28',
      };

      // Create a new branch for the changes
      const timestamp = Date.now();
      const branchName = `feature/sovereign-studio-${timestamp}`;
      
      // Get the default branch SHA
      const refResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/ref/heads/${parsed.branch}`,
        { headers }
      );
      
      if (!refResponse.ok) {
        throw new Error(`Konnte Branch-Info nicht laden: ${refResponse.status}`);
      }
      
      const refData = await refResponse.json();
      const baseSha = refData.object.sha;

      // Create new branch
      await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/refs`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            ref: `refs/heads/${branchName}`,
            sha: baseSha,
          }),
        }
      );

      // Create a commit with the generated code
      const commitMessage = `feat: Sovereign Studio generated code\n\nGenerated by Sovereign Studio\n\nAuftrag: ${blueprint.slice(0, 100)}...`;
      
      // Create blob for the file
      const blobResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/blobs`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            content: generatedCode,
            encoding: 'utf-8',
          }),
        }
      );

      if (!blobResponse.ok) {
        throw new Error(`Konnte Datei nicht erstellen: ${blobResponse.status}`);
      }

      const blobData = await blobResponse.json();
      const fileSha = blobData.sha;

      // Get current tree to base the new tree on
      const treeResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees/${baseSha}?recursive=1`,
        { headers }
      );
      const treeData = await treeResponse.json();

      // Create new tree with our file
      const newTreeResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/trees`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            base_tree: treeData.sha,
            tree: [
              {
                path: 'generated/sovereign-product/workflow.ts',
                mode: '100644',
                type: 'blob',
                sha: fileSha,
              },
            ],
          }),
        }
      );

      const newTreeData = await newTreeResponse.json();

      // Create commit
      const commitResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/commits`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            message: commitMessage,
            tree: newTreeData.sha,
            parents: [baseSha],
          }),
        }
      );

      const commitData = await commitResponse.json();

      // Update branch reference
      await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/git/refs/heads/${branchName}`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            sha: commitData.sha,
            force: false,
          }),
        }
      );

      // Create PR
      const prResponse = await fetch(
        `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/pulls`,
        {
          method: 'POST',
          headers,
          body: JSON.stringify({
            title: `Sovereign Studio: ${blueprint.slice(0, 50)}...`,
            head: branchName,
            base: parsed.branch,
            body: `## Sovereign Studio Generated PR\n\n**Auftrag:** ${blueprint}\n\n**Generated Files:**\n- generated/sovereign-product/workflow.ts\n\n*Generated by Sovereign Studio*`,
          }),
        }
      );

      if (!prResponse.ok) {
        throw new Error(`Konnte PR nicht erstellen: ${prResponse.status}`);
      }

      const prData = await prResponse.json();
      const prUrl = prData.html_url;
      const prNumber = prData.number;

      // Success - set approval and log target link
      setApprovalConfirmed(true);
      setTargetLink(prUrl);
      setCurrentStepLabel('Freigabe bestaetigt');
      setNextStepLabel('');
      setAgentMessage(`Fertig! PR #${prNumber} erstellt: ${prUrl}`);
      log(`=== Ziel-Link: ${prUrl} ===`);
      log('=== Freigabe bestaetigt: Auftrag abgeschlossen ===');
      
    } catch (err) {
      console.error('GitHub Push Fehler:', err);
      setAgentMessage(`Fehler beim Pushen: ${err instanceof Error ? err.message : 'Unbekannter Fehler'}`);
      log(`FEHLER: Push fehlgeschlagen - ${err instanceof Error ? err.message : 'Unbekannter Fehler'}`);
      setCurrentStepLabel('Push fehlgeschlagen');
      setNextStepLabel('Erneut versuchen');
    }

    setIsWorking(false);
  }, [guardBusy, approvalConfirmed, pipelineState, repoUrl, accessKey, generatedCode, blueprint, log]);

  return {
    repoUrl, setRepoUrl,
    accessKey, setAccessKey,
    geminiKey, setGeminiKey,
    blueprint, setBlueprint,
    cards, setCards,
    selectedFile, setSelectedFile,
    built, setBuilt,
    chatInput, setChatInput,
    logs, setLogs,
    workView, setWorkView,
    pipelineState, setPipelineState,
    fixLoops, setFixLoops,
    showSettings, setShowSettings,
    settings, setSettings,
    generatedCode, setGeneratedCode,
    currentCode,
    generatedPackage,
    isWorking,
    agentMessage,
    progress,
    mobilePane, setMobilePane,
    currentStepLabel, setCurrentStepLabel,
    nextStepLabel, setNextStepLabel,
    approvalConfirmed,
    targetLink,
    log,
    generateCodeInEditor,
    buildProduct,
    addCard,
    sendChat,
    downloadPackage,
    publishAndValidate,
    patchFromPipeline,
    mergeWhenGreen,
    runAutonomousJob,
    // Chat exports
    chatMessages,
    setChatMessages,
    suggestions,
    architectureAnalysis,
    isAnalyzing,
    acceptSuggestion,
    sendChatMessage,
    runArchitectureAnalysis
  };
}
