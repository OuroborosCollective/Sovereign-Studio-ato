import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  fetchDevChatRepoTree,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  fetchSovereignLlmRouteCatalog,
  parseDevChatGithubUrl,
  type DevChatWorkerMessage,
  type SovereignLlmRouteOption,
} from '../product/runtime/devChatWorkerBridge';
import { fetchSovereignDirectLlmInterpretation } from '../product/runtime/sovereignDirectLlmIntentRuntime';
import { SovereignAgentClient } from '../product/runtime/sovereignAgentClient';
import {
  isSovereignAgentTerminalStatus,
  summarizeSovereignAgentJob,
  type SovereignAgentJobSnapshot,
} from '../product/runtime/sovereignAgentRuntime';
import { formatCuteThinkingLabel } from '../product/runtime/cuteThinkingStatus';
import { evaluateInputPolicy } from '../product/runtime/secureInputGuard';
import { LoginModal } from '../user/components/LoginModal';
import { useUserStore } from '../user/useUserStore';

type ChatRole = 'user' | 'assistant' | 'system';
type ActivityTone = 'info' | 'success' | 'warning' | 'error';

interface ChatEntry {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly createdAt: number;
}

interface ActiveRepoContext {
  readonly repoUrl: string;
  readonly owner: string;
  readonly repo: string;
  readonly branch: string;
  readonly headSha?: string;
}

interface PendingRepoAction {
  readonly mission: string;
  readonly title: string;
  readonly repo: ActiveRepoContext;
}

interface ActivityEntry {
  readonly id: string;
  readonly at: number;
  readonly label: string;
  readonly tone: ActivityTone;
}

const C = {
  bg: '#0b0f14',
  surface: '#121821',
  surface2: '#171f2b',
  border: '#263244',
  text: '#edf3fa',
  sub: '#9aa9ba',
  muted: '#657487',
  accent: '#58a6ff',
  green: '#39d98a',
  amber: '#f2b84b',
  rose: '#ff6b7a',
  violet: '#b69cff',
};

function routeLabel(route: SovereignLlmRouteOption): string {
  const billing = route.billingCategory === 'free' ? 'FREE' : (route.billingCategory ?? 'STANDARD').toUpperCase();
  return `${billing} · ${route.label}`;
}

function repoLabel(repo: ActiveRepoContext): string {
  return `${repo.owner}/${repo.repo}@${repo.branch}`;
}

function shortText(value: string, max = 180): string {
  const clean = value.replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max - 1)}…` : clean;
}

function messageTextWithLinks(text: string) {
  const parts = text.split(/(https:\/\/github\.com\/[^\s]+\/pull\/[1-9][0-9]*)/g);
  return parts.map((part, index) => (
    /^https:\/\/github\.com\/[^\s]+\/pull\/[1-9][0-9]*$/.test(part)
      ? <a key={`${part}-${index}`} href={part} target="_blank" rel="noreferrer" style={{ color: C.accent, textDecoration: 'underline' }}>{part}</a>
      : <React.Fragment key={`${index}-${part.slice(0, 8)}`}>{part}</React.Fragment>
  ));
}

function Bubble({ entry }: { readonly entry: ChatEntry }) {
  const user = entry.role === 'user';
  const system = entry.role === 'system';
  return (
    <div
      data-role={entry.role}
      style={{
        display: 'flex',
        justifyContent: user ? 'flex-end' : 'flex-start',
        padding: '4px 0',
      }}
    >
      <div
        style={{
          maxWidth: system ? '92%' : 'min(86%, 760px)',
          padding: system ? '8px 11px' : '11px 13px',
          borderRadius: system ? 9 : user ? '15px 15px 4px 15px' : '15px 15px 15px 4px',
          border: `1px solid ${system ? C.amber + '55' : user ? C.accent + '55' : C.border}`,
          background: system ? C.amber + '0f' : user ? '#123054' : C.surface2,
          color: system ? C.amber : C.text,
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
          fontSize: system ? 12 : 14,
          lineHeight: 1.55,
          boxShadow: system ? 'none' : '0 5px 18px rgba(0,0,0,.16)',
        }}
      >
        {messageTextWithLinks(entry.text)}
      </div>
    </div>
  );
}

function toneColor(tone: ActivityTone): string {
  if (tone === 'success') return C.green;
  if (tone === 'warning') return C.amber;
  if (tone === 'error') return C.rose;
  return C.accent;
}

export function PlayReleaseChat() {
  const { user, refreshUser, logout } = useUserStore();
  const agentClient = useMemo(() => new SovereignAgentClient(), []);
  const [showLogin, setShowLogin] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [routes, setRoutes] = useState<readonly SovereignLlmRouteOption[]>([]);
  const [selectedRoute, setSelectedRoute] = useState('');
  const [routeError, setRouteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runtimeState, setRuntimeState] = useState<'checking' | 'ready' | 'degraded'>('checking');
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const [activeRepo, setActiveRepo] = useState<ActiveRepoContext | null>(null);
  const [showRepoInput, setShowRepoInput] = useState(false);
  const [repoInput, setRepoInput] = useState('');
  const [repoChecking, setRepoChecking] = useState(false);
  const [pendingAction, setPendingAction] = useState<PendingRepoAction | null>(null);
  const [agentJob, setAgentJob] = useState<SovereignAgentJobSnapshot | null>(null);
  const [agentStarting, setAgentStarting] = useState(false);
  const [agentFinalizing, setAgentFinalizing] = useState(false);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [thinkingTick, setThinkingTick] = useState(0);

  const listRef = useRef<HTMLDivElement>(null);
  const sequenceRef = useRef(0);
  const activitySequenceRef = useRef(0);
  const handledTerminalJobsRef = useRef(new Set<string>());
  const lastPollErrorRef = useRef('');

  const addMessage = (role: ChatRole, text: string) => {
    sequenceRef.current += 1;
    const entry: ChatEntry = {
      id: `release-chat-${sequenceRef.current}`,
      role,
      text: text.trim(),
      createdAt: Date.now(),
    };
    setMessages((current) => [...current.slice(-79), entry]);
  };

  const addActivity = (label: string, tone: ActivityTone = 'info') => {
    activitySequenceRef.current += 1;
    const entry: ActivityEntry = {
      id: `activity-${activitySequenceRef.current}`,
      at: Date.now(),
      label: shortText(label),
      tone,
    };
    setActivity((current) => [...current.slice(-11), entry]);
  };

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    if (!user) {
      setRoutes([]);
      setRouteError(null);
      setRuntimeState('checking');
      return;
    }
    const controller = new AbortController();
    let active = true;
    void Promise.allSettled([
      fetchSovereignLlmRouteCatalog(controller.signal, 'picker'),
      fetchDevChatWorkerHealth(controller.signal),
    ]).then(([catalog, health]) => {
      if (!active) return;
      if (catalog.status === 'fulfilled') {
        setRoutes(catalog.value);
        setRouteError(null);
      } else {
        setRoutes([]);
        setRouteError('Routenkatalog ist gerade nicht verfügbar.');
      }
      if (health.status === 'fulfilled' && health.value.ok) setRuntimeState('ready');
      else setRuntimeState('degraded');
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [user]);

  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, busy, activity, agentJob?.status]);

  const agentWorking = Boolean(
    agentJob?.jobId
    && !isSovereignAgentTerminalStatus(agentJob.status),
  );
  const workActive = busy || repoChecking || agentStarting || agentWorking || agentFinalizing;

  useEffect(() => {
    if (!workActive) return undefined;
    const timer = window.setInterval(() => setThinkingTick((current) => current + 1), 820);
    return () => window.clearInterval(timer);
  }, [workActive]);

  useEffect(() => {
    const jobId = agentJob?.jobId;
    if (!jobId || isSovereignAgentTerminalStatus(agentJob.status)) return undefined;

    let stopped = false;
    const poll = async () => {
      try {
        const next = await agentClient.getJob(jobId);
        if (stopped) return;
        lastPollErrorRef.current = '';
        setAgentJob(next);
      } catch (error) {
        if (stopped) return;
        const message = error instanceof Error ? error.message : 'Agent-Readback fehlgeschlagen.';
        if (message !== lastPollErrorRef.current) {
          lastPollErrorRef.current = message;
          addActivity(`Agent-Readback: ${message}`, 'warning');
        }
      }
    };

    void poll();
    const timer = window.setInterval(() => { void poll(); }, 1600);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [agentClient, agentJob?.jobId, agentJob?.status]);

  useEffect(() => {
    const snapshot = agentJob;
    const jobId = snapshot?.jobId;
    if (!snapshot || !jobId || !isSovereignAgentTerminalStatus(snapshot.status)) return;
    if (handledTerminalJobsRef.current.has(jobId)) return;
    handledTerminalJobsRef.current.add(jobId);

    if (snapshot.status === 'blocked' || snapshot.status === 'failed') {
      const detail = snapshot.lastError || summarizeSovereignAgentJob(snapshot);
      addActivity(detail, 'error');
      addMessage('system', `Codearbeit gestoppt: ${detail}`);
      return;
    }

    if (snapshot.status !== 'completed') return;

    void (async () => {
      setAgentFinalizing(true);
      try {
        if (snapshot.draftPrUrl) {
          addActivity(`Draft PR verifiziert: ${snapshot.draftPrUrl}`, 'success');
          addMessage('assistant', `Codearbeit abgeschlossen. Draft PR: ${snapshot.draftPrUrl}`);
          return;
        }

        addActivity('Änderungen abgeschlossen · Draft PR wird vorbereitet', 'info');
        const preparation = await agentClient.prepareDraftPr(jobId);
        const prep = preparation.draftPrPreparation;
        if (!prep.allowed || !prep.canCreateDraftPr) {
          const blockers = prep.blockers.length ? ` ${prep.blockers.join(' · ')}` : '';
          const detail = prep.nextAction || prep.summary || 'Draft PR ist noch nicht freigegeben.';
          addActivity(`${detail}${blockers}`, 'warning');
          addMessage('system', `Code wurde bearbeitet, aber der Draft PR ist blockiert: ${detail}${blockers}`);
          return;
        }

        addActivity('GitHub Draft PR wird erstellt und zurückgelesen', 'info');
        const created = await agentClient.createDraftPr(jobId);
        const pr = created.draftPrCreate;
        if (!pr.allowed || !pr.prUrl || !pr.readbackVerified || !pr.draftVerified) {
          const detail = pr.blocker || pr.summary || 'Draft-PR-Readback ist nicht verifiziert.';
          addActivity(detail, 'error');
          addMessage('system', `Draft PR konnte nicht verifiziert werden: ${detail}`);
          return;
        }

        addActivity(`Draft PR bereit · ${pr.prUrl}`, 'success');
        setAgentJob((current) => current ? { ...current, draftPrUrl: pr.prUrl } : current);
        addMessage(
          'assistant',
          `Codearbeit abgeschlossen und auf GitHub zurückgelesen.\n\nGeänderte Dateien: ${snapshot.changedFiles.length || 'keine gemeldet'}\nDraft PR: ${pr.prUrl}`,
        );
      } catch (error) {
        const detail = error instanceof Error ? error.message : 'Draft-PR-Finalisierung fehlgeschlagen.';
        addActivity(detail, 'error');
        addMessage('system', `Draft-PR-Finalisierung fehlgeschlagen: ${detail}`);
      } finally {
        setAgentFinalizing(false);
      }
    })();
  }, [agentClient, agentJob]);

  const model = selectedRoute || DEV_CHAT_WORKER_DEFAULT_MODEL;
  const activeRoute = useMemo(
    () => routes.find((route) => route.id === selectedRoute),
    [routes, selectedRoute],
  );

  const connectRepo = async (raw: string): Promise<ActiveRepoContext | null> => {
    const parsed = parseDevChatGithubUrl(raw.trim());
    if (!parsed) {
      addMessage('system', 'Bitte eine vollständige GitHub-Repository-URL angeben, z. B. https://github.com/owner/repo.');
      return null;
    }

    const base: ActiveRepoContext = {
      repoUrl: parsed.repoUrl,
      owner: parsed.owner,
      repo: parsed.repo,
      branch: parsed.branch,
    };
    setActiveRepo(base);
    setRepoInput(parsed.repoUrl);
    setShowRepoInput(false);
    addActivity(`Repo-Ziel gesetzt: ${repoLabel(base)}`, 'success');

    setRepoChecking(true);
    try {
      const readback = await fetchDevChatRepoTree(parsed);
      if (readback.ok && readback.snapshot) {
        const resolved: ActiveRepoContext = {
          ...base,
          branch: readback.snapshot.branch || base.branch,
          headSha: readback.snapshot.headSha,
        };
        setActiveRepo(resolved);
        addActivity(
          readback.snapshot.headSha
            ? `Repo-Readback: ${repoLabel(resolved)} · ${readback.snapshot.headSha.slice(0, 8)}`
            : `Repo-Readback: ${repoLabel(resolved)}`,
          'success',
        );
        return resolved;
      }
      addActivity('Browser-Repo-Readback nicht verfügbar · Agent-Backend prüft Zugriff beim Start', 'warning');
    } catch {
      addActivity('Browser-Repo-Readback nicht verfügbar · Agent-Backend prüft Zugriff beim Start', 'warning');
    } finally {
      setRepoChecking(false);
    }
    return base;
  };

  const startCodingAction = async (action: PendingRepoAction) => {
    if (agentWorking || agentStarting || agentFinalizing) {
      addMessage('system', 'Eine Repository-Aktion läuft bereits. Der Aktivitätsverlauf zeigt den aktuellen Stand.');
      return;
    }
    setPendingAction(null);
    setAgentStarting(true);
    addActivity(`Agentenauftrag startet: ${action.title}`, 'info');
    try {
      const snapshot = await agentClient.startJob({
        repoUrl: action.repo.repoUrl,
        branch: action.repo.branch,
        expectedHeadSha: action.repo.headSha,
        mission: action.mission,
        provisionWorkspace: true,
        cloneRepo: true,
      });
      setAgentJob(snapshot);
      addActivity(summarizeSovereignAgentJob(snapshot), 'info');
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Agentenauftrag konnte nicht gestartet werden.';
      addActivity(detail, 'error');
      addMessage('system', `Codearbeit konnte nicht gestartet werden: ${detail}`);
    } finally {
      setAgentStarting(false);
    }
  };

  const buildConversation = (text: string): DevChatWorkerMessage[] => [
    {
      role: 'system',
      content: 'Du bist Sovereign. Antworte hilfreich, klar und direkt. Behaupte keine ausgeführten Aktionen ohne echte Runtime-Evidence.',
    },
    ...messages
      .filter((entry) => entry.role === 'user' || entry.role === 'assistant')
      .slice(-18)
      .map((entry): DevChatWorkerMessage => ({
        role: entry.role as 'user' | 'assistant',
        content: entry.text,
      })),
    { role: 'user', content: text },
  ];

  const sendPlainChat = async (text: string, conversation: DevChatWorkerMessage[]) => {
    const result = await fetchDevChatWorkerReply(
      { model, messages: conversation },
      { maxRetries: 1, retryDelayMs: 700 },
    );
    if (!result.ok || !result.content) {
      const detail = result.diagnostic?.nextAction || result.error || 'Die LLM-Runtime hat keine Antwort geliefert.';
      setLastFailedText(text);
      setRuntimeState('degraded');
      addMessage('system', `LLM-Anfrage blockiert: ${detail}`);
      return;
    }
    setRuntimeState('ready');
    const fallback = result.fallbackUsed && result.actualModel
      ? `\n\nHinweis: Antwort kam über ${result.actualModel}.`
      : '';
    addMessage('assistant', `${result.content}${fallback}`);
  };

  const submit = async (override?: string) => {
    const text = (override ?? draft).trim();
    if (!text || busy) return;
    if (!user) {
      setShowLogin(true);
      return;
    }

    const inputPolicy = evaluateInputPolicy(text);
    if (inputPolicy.shouldBlock) {
      setDraft('');
      addMessage('system', 'Diese Eingabe sieht wie ein Zugangsschlüssel oder Secret aus und wurde nicht an das LLM gesendet.');
      return;
    }

    setDraft('');
    setBusy(true);
    setLastFailedText(null);
    addMessage('user', text);
    const conversation = buildConversation(text);

    try {
      const parsedRepo = parseDevChatGithubUrl(text);
      let repoForRequest = activeRepo;
      if (parsedRepo) {
        repoForRequest = {
          repoUrl: parsedRepo.repoUrl,
          owner: parsedRepo.owner,
          repo: parsedRepo.repo,
          branch: parsedRepo.branch,
        };
        setActiveRepo(repoForRequest);
        setRepoInput(parsedRepo.repoUrl);
        addActivity(`Repo-Ziel aus Nachricht erkannt: ${repoLabel(repoForRequest)}`, 'success');
        void connectRepo(parsedRepo.repoUrl);
      }

      if (!repoForRequest) {
        await sendPlainChat(text, conversation);
        return;
      }

      addActivity(`LLM interpretiert Auftrag für ${repoLabel(repoForRequest)}`, 'info');
      const interpretationResult = await fetchSovereignDirectLlmInterpretation({
        preferredModel: model,
        text,
        repoContext: `${repoLabel(repoForRequest)}${repoForRequest.headSha ? ` · HEAD ${repoForRequest.headSha}` : ''}`,
        recentMessages: conversation.slice(-6),
      });

      const interpretation = interpretationResult.interpretation;
      if (!interpretationResult.ok || !interpretation) {
        addActivity('Typisierte Aktionsinterpretation nicht verfügbar · keine Repo-Mutation', 'warning');
        await sendPlainChat(text, conversation);
        return;
      }

      if (interpretation.mode === 'chat') {
        if (interpretation.assistantText) {
          addMessage('assistant', interpretation.assistantText);
          setRuntimeState('ready');
        } else {
          await sendPlainChat(text, conversation);
        }
        return;
      }

      if (interpretation.intent === 'load_repo') {
        addMessage('assistant', `Repository aktiv: ${repoLabel(repoForRequest)}. Sag mir einfach, was ich im Code ändern soll.`);
        return;
      }

      if (interpretation.intent === 'status' || interpretation.intent === 'workflow_watch') {
        addMessage(
          'assistant',
          agentJob
            ? summarizeSovereignAgentJob(agentJob)
            : `Repository aktiv: ${repoLabel(repoForRequest)}. Aktuell läuft kein Agentenauftrag.`,
        );
        return;
      }

      if (!['direct_patch', 'code_execution', 'draft_pr', 'repair_workflow'].includes(interpretation.intent)) {
        addMessage('system', `Der erkannte Aktions-Typ „${interpretation.intent}“ ist im Play-Release nicht zur Repository-Mutation freigegeben.`);
        return;
      }

      const action: PendingRepoAction = {
        mission: interpretation.actionTitle || text,
        title: interpretation.actionTitle || 'Repository-Codearbeit',
        repo: repoForRequest,
      };

      if (agentWorking || agentStarting || agentFinalizing) {
        addMessage('system', 'Eine Repository-Aktion läuft bereits. Neue Schreibaktionen werden nicht parallel gestartet.');
        return;
      }

      if (interpretation.actionDisposition === 'execute') {
        await startCodingAction(action);
        return;
      }

      setPendingAction(action);
      addActivity(`Änderung verstanden · wartet auf Ausführung: ${action.title}`, 'warning');
      addMessage(
        'assistant',
        `Ich habe den Coding-Auftrag verstanden: „${action.title}“.\n\nRepository: ${repoLabel(repoForRequest)}\nDie Änderung startet erst nach deiner Ausführung. Kein Merge erfolgt automatisch.`,
      );
    } catch (error) {
      setLastFailedText(text);
      setRuntimeState('degraded');
      addMessage('system', `Sovereign-Verbindung fehlgeschlagen: ${error instanceof Error ? error.message : 'unbekannter Fehler'}`);
    } finally {
      setBusy(false);
    }
  };

  const runtimeColor = runtimeState === 'ready' ? C.green : runtimeState === 'degraded' ? C.amber : C.muted;
  const runtimeLabel = runtimeState === 'ready' ? 'LLM bereit' : runtimeState === 'degraded' ? 'LLM eingeschränkt' : 'LLM wird geprüft';
  const cuteStatus = agentFinalizing
    ? 'draft pr'
    : agentStarting
      ? 'agent startet'
      : agentJob?.status
        ? `agent ${agentJob.status}`
        : repoChecking
          ? 'repo readback'
          : busy
            ? 'working'
            : undefined;
  const cuteLabel = formatCuteThinkingLabel({
    index: thinkingTick,
    active: workActive || agentJob?.status === 'completed',
    status: cuteStatus,
  });

  const timeline = useMemo(() => {
    const runtimeEvents: ActivityEntry[] = (agentJob?.events ?? []).map((event, index) => ({
      id: `runtime-${agentJob?.jobId ?? 'none'}-${index}-${event.at}`,
      at: event.at,
      label: `${event.stage}: ${shortText(event.message)}`,
      tone: (event.level === 'success' ? 'success' : event.level === 'error' ? 'error' : event.level === 'warning' ? 'warning' : 'info') as ActivityTone,
    }));
    return [...activity, ...runtimeEvents]
      .sort((left, right) => left.at - right.at)
      .slice(-8);
  }, [activity, agentJob]);

  return (
    <main
      data-testid="sovereign-release-chat"
      data-layout="play-release-chat"
      aria-label="Sovereign Chat"
      style={{
        height: '100dvh',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        background: C.bg,
        color: C.text,
        fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      }}
    >
      <style>{`
        * { box-sizing: border-box; }
        .release-chat-header { padding-top: max(10px, env(safe-area-inset-top)); }
        .release-chat-shell { width: 100%; max-width: 980px; margin: 0 auto; }
        .release-chat-composer { padding-bottom: max(10px, env(safe-area-inset-bottom)); }
        @keyframes sovereign-cute-bob {
          0%, 100% { transform: translateY(0) rotate(0deg); }
          35% { transform: translateY(-2px) rotate(-1deg); }
          70% { transform: translateY(1px) rotate(1deg); }
        }
        @keyframes sovereign-cute-glow {
          0%, 100% { opacity: .82; }
          50% { opacity: 1; }
        }
        @media (max-width: 640px) {
          .release-chat-title-sub { display: none; }
          .release-chat-route { max-width: 122px !important; }
          .release-agent-timeline-row:nth-last-child(n+5) { display: none; }
        }
      `}</style>

      <header
        className="release-chat-header"
        style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.surface }}
      >
        <div className="release-chat-shell" style={{ minHeight: 58, display: 'flex', alignItems: 'center', gap: 9, padding: '8px 12px' }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, display: 'grid', placeItems: 'center', background: C.accent + '18', border: `1px solid ${C.accent}44`, color: C.accent, fontWeight: 800 }}>S</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 750, fontSize: 15 }}>Sovereign</div>
            <div className="release-chat-title-sub" style={{ color: C.sub, fontSize: 10.5 }}>
              Chat + GitHub Coding Agent
            </div>
          </div>

          {user && (
            <button
              type="button"
              aria-label="Repository verbinden"
              onClick={() => setShowRepoInput((current) => !current)}
              title={activeRepo ? repoLabel(activeRepo) : 'GitHub Repository verbinden'}
              style={{
                minHeight: 40,
                maxWidth: 170,
                padding: '0 10px',
                borderRadius: 8,
                border: `1px solid ${activeRepo ? C.green + '66' : C.border}`,
                background: activeRepo ? C.green + '0e' : C.bg,
                color: activeRepo ? C.green : C.sub,
                cursor: 'pointer',
                fontSize: 10.5,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {activeRepo ? `⌘ ${activeRepo.repo}` : '⌘ Repo'}
            </button>
          )}

          {user && (
            <select
              className="release-chat-route"
              aria-label="LLM Route"
              value={selectedRoute}
              onChange={(event) => setSelectedRoute(event.target.value)}
              style={{
                maxWidth: 210,
                minHeight: 40,
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                padding: '0 8px',
                fontSize: 11,
              }}
            >
              <option value="">Auto · FreeLLM zuerst</option>
              {routes.map((route) => <option key={route.id} value={route.id}>{routeLabel(route)}</option>)}
            </select>
          )}

          <span title={routeError ?? runtimeLabel} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: runtimeColor, fontSize: 10, whiteSpace: 'nowrap' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: runtimeColor }} />
            <span className="release-chat-title-sub">{runtimeLabel}</span>
          </span>

          {user ? (
            <button
              type="button"
              onClick={() => { void logout(); }}
              title={user.email}
              aria-label="Abmelden"
              style={{ minWidth: 44, minHeight: 44, borderRadius: 9, border: `1px solid ${C.border}`, background: C.bg, color: C.sub, cursor: 'pointer' }}
            >
              ↪
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowLogin(true)}
              style={{ minHeight: 44, padding: '0 14px', borderRadius: 9, border: `1px solid ${C.accent}66`, background: C.accent + '16', color: C.accent, fontWeight: 700, cursor: 'pointer' }}
            >
              Anmelden
            </button>
          )}
        </div>

        {user && showRepoInput && (
          <div className="release-chat-shell" style={{ padding: '0 12px 9px', display: 'flex', gap: 7 }}>
            <input
              aria-label="GitHub Repository URL"
              value={repoInput}
              onChange={(event) => setRepoInput(event.target.value)}
              placeholder="https://github.com/owner/repo"
              style={{
                flex: 1,
                minWidth: 0,
                minHeight: 42,
                borderRadius: 8,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                padding: '0 11px',
                outline: 'none',
              }}
            />
            <button
              type="button"
              disabled={!repoInput.trim() || repoChecking}
              onClick={() => { void connectRepo(repoInput); }}
              style={{
                minHeight: 42,
                padding: '0 13px',
                borderRadius: 8,
                border: 'none',
                background: C.accent,
                color: '#07111c',
                fontWeight: 750,
                cursor: !repoInput.trim() || repoChecking ? 'not-allowed' : 'pointer',
                opacity: !repoInput.trim() || repoChecking ? .55 : 1,
              }}
            >
              {repoChecking ? 'Prüfe…' : 'Verbinden'}
            </button>
          </div>
        )}
      </header>

      {(activeRepo || workActive || timeline.length > 0) && (
        <section
          className="release-chat-shell"
          aria-label="Sovereign Aktivitätsverlauf"
          style={{
            flexShrink: 0,
            borderBottom: `1px solid ${C.border}`,
            background: '#0e141c',
            padding: '8px 12px',
          }}
        >
          <div
            role="status"
            aria-label="Sovereign arbeitet"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 9,
              minHeight: 31,
              color: workActive ? C.text : C.sub,
              fontSize: 11.5,
            }}
          >
            <span
              aria-hidden="true"
              style={{
                display: 'inline-block',
                minWidth: 28,
                textAlign: 'center',
                fontSize: 16,
                animation: workActive ? 'sovereign-cute-bob .9s ease-in-out infinite, sovereign-cute-glow 1.6s ease-in-out infinite' : undefined,
              }}
            >
              {cuteLabel.split(' ')[0]}
            </span>
            <span style={{ minWidth: 0, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {cuteLabel}
            </span>
            {activeRepo && (
              <span style={{ color: C.green, fontSize: 9.5, whiteSpace: 'nowrap' }}>
                {repoLabel(activeRepo)}
                {activeRepo.headSha ? ` · ${activeRepo.headSha.slice(0, 7)}` : ''}
              </span>
            )}
          </div>

          {timeline.length > 0 && (
            <div style={{ maxHeight: 98, overflowY: 'auto', marginTop: 3, paddingLeft: 37 }}>
              {timeline.map((entry) => (
                <div
                  key={entry.id}
                  className="release-agent-timeline-row"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '58px 7px minmax(0, 1fr)',
                    alignItems: 'center',
                    gap: 7,
                    minHeight: 21,
                    color: C.sub,
                    fontSize: 9.5,
                  }}
                >
                  <span>{new Date(entry.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: toneColor(entry.tone) }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.label}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <div ref={listRef} className="release-chat-shell" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 14px 20px', scrollBehavior: 'smooth' }}>
        {messages.length === 0 ? (
          <div style={{ minHeight: '52vh', display: 'grid', placeItems: 'center', textAlign: 'center', padding: 20 }}>
            <div style={{ maxWidth: 560 }}>
              <div
                style={{
                  width: 58,
                  height: 58,
                  margin: '0 auto 16px',
                  borderRadius: 18,
                  display: 'grid',
                  placeItems: 'center',
                  color: C.accent,
                  background: C.accent + '12',
                  border: `1px solid ${C.accent}33`,
                  fontSize: 25,
                  fontWeight: 800,
                  animation: 'sovereign-cute-bob 2.8s ease-in-out infinite',
                }}
              >
                🐣
              </div>
              <h1 style={{ margin: 0, fontSize: 22, letterSpacing: '-.02em' }}>Chatten oder direkt im Repository arbeiten</h1>
              <p style={{ color: C.sub, fontSize: 13, lineHeight: 1.65, margin: '10px auto 0' }}>
                Repository verbinden, Auftrag in normaler Sprache beschreiben und Sovereign kann Code bearbeiten, testen und einen verifizierten Draft PR erstellen.
              </p>
              {!user && <button type="button" onClick={() => setShowLogin(true)} style={{ marginTop: 18, minHeight: 44, padding: '0 18px', borderRadius: 10, border: 'none', background: C.accent, color: '#07111c', fontWeight: 800, cursor: 'pointer' }}>Mit E-Mail anmelden</button>}
            </div>
          </div>
        ) : messages.map((entry) => <Bubble key={entry.id} entry={entry} />)}
        {busy && (
          <div role="status" style={{ color: C.sub, fontSize: 12, padding: '8px 3px' }}>Sovereign versteht den Auftrag…</div>
        )}
      </div>

      <footer className="release-chat-composer" style={{ flexShrink: 0, borderTop: `1px solid ${C.border}`, background: C.surface }}>
        <div className="release-chat-shell" style={{ padding: '10px 12px 0' }}>
          {activeRoute && <div style={{ color: C.muted, fontSize: 9.5, marginBottom: 5 }}>Route fixiert: {routeLabel(activeRoute)} · kein stiller Routenwechsel</div>}

          {pendingAction && !agentWorking && !agentStarting && (
            <div style={{ marginBottom: 8, padding: 9, borderRadius: 9, border: `1px solid ${C.violet}55`, background: C.violet + '0c' }}>
              <div style={{ color: C.text, fontSize: 11.5, fontWeight: 650, marginBottom: 6 }}>{pendingAction.title}</div>
              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                <button
                  type="button"
                  aria-label="Änderung jetzt ausführen"
                  onClick={() => { void startCodingAction(pendingAction); }}
                  style={{ minHeight: 38, padding: '0 12px', borderRadius: 8, border: 'none', background: C.green, color: '#06150f', fontWeight: 800, cursor: 'pointer' }}
                >
                  Änderung jetzt ausführen
                </button>
                <button
                  type="button"
                  onClick={() => setPendingAction(null)}
                  style={{ minHeight: 38, padding: '0 12px', borderRadius: 8, border: `1px solid ${C.border}`, background: C.bg, color: C.sub, cursor: 'pointer' }}
                >
                  Verwerfen
                </button>
              </div>
            </div>
          )}

          {lastFailedText && !busy && (
            <button type="button" onClick={() => { void submit(lastFailedText); }} style={{ marginBottom: 7, minHeight: 36, padding: '0 11px', borderRadius: 8, border: `1px solid ${C.amber}55`, background: C.amber + '10', color: C.amber, cursor: 'pointer' }}>
              Letzte Anfrage erneut versuchen
            </button>
          )}

          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              aria-label="Nachricht an Sovereign"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  void submit();
                }
              }}
              disabled={busy}
              placeholder={user ? (activeRepo ? `Auftrag für ${activeRepo.repo}…` : 'Nachricht an Sovereign…') : 'Zum Chatten bitte anmelden…'}
              rows={1}
              style={{
                flex: 1,
                minWidth: 0,
                minHeight: 46,
                maxHeight: 150,
                resize: 'vertical',
                borderRadius: 12,
                border: `1px solid ${C.border}`,
                background: C.bg,
                color: C.text,
                padding: '12px 13px',
                font: '14px/1.45 inherit',
                outline: 'none',
              }}
            />
            <button
              type="button"
              aria-label="Senden"
              disabled={busy || !draft.trim()}
              onClick={() => { void submit(); }}
              style={{ width: 46, height: 46, flexShrink: 0, borderRadius: 12, border: 'none', background: busy || !draft.trim() ? C.border : C.accent, color: '#07111c', fontSize: 18, fontWeight: 800, cursor: busy || !draft.trim() ? 'not-allowed' : 'pointer' }}
            >
              ↑
            </button>
          </div>

          <div style={{ minHeight: 25, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, color: C.muted, fontSize: 9.5 }}>
            <span>{user ? user.email : 'E-Mail/Passwort-Anmeldung erforderlich'}</span>
            <span>
              {agentWorking
                ? 'Agent arbeitet · keine parallele Schreibaktion'
                : activeRepo
                  ? 'Repo aktiv · Codearbeit endet als Draft PR'
                  : routeError ?? 'Repo verbinden für Codearbeit'}
            </span>
          </div>
        </div>
      </footer>

      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
    </main>
  );
}

export default PlayReleaseChat;
