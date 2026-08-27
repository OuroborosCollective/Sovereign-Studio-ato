import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  DEV_CHAT_WORKER_DEFAULT_MODEL,
  fetchDevChatWorkerHealth,
  fetchDevChatWorkerReply,
  fetchSovereignLlmRouteCatalog,
  parseDevChatGithubUrl,
  type DevChatWorkerMessage,
  type SovereignLlmRouteOption,
} from '../product/runtime/devChatWorkerBridge';
import { evaluateInputPolicy } from '../product/runtime/secureInputGuard';
import { deriveReleaseGuideState } from '../product/runtime/sovereignReleaseGuide';
import { fetchSovereignDirectLlmInterpretation } from '../product/runtime/sovereignDirectLlmIntentRuntime';
import { createSovereignAgentClient } from '../product/runtime/sovereignAgentClient';
import {
  isSovereignAgentTerminalStatus,
  resolveSovereignAgentConfig,
  summarizeSovereignAgentJob,
  type SovereignAgentJobSnapshot,
} from '../product/runtime/sovereignAgentRuntime';
import { LoginModal } from '../user/components/LoginModal';
import { useUserStore } from '../user/useUserStore';

type ChatRole = 'user' | 'assistant' | 'system';
type ReleaseMenuKey = 'chat' | 'github' | 'models' | 'account';

interface ChatEntry {
  readonly id: string;
  readonly role: ChatRole;
  readonly text: string;
  readonly createdAt: number;
}

interface ReleaseRepoTarget {
  readonly repoUrl: string;
  readonly branch: string;
  readonly label: string;
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
};

function routeLabel(route: SovereignLlmRouteOption): string {
  const billing = route.billingCategory === 'free' ? 'FREE' : (route.billingCategory ?? 'STANDARD').toUpperCase();
  return `${billing} · ${route.label}`;
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
        {entry.text}
      </div>
    </div>
  );
}

export function PlayReleaseChat() {
  const { user, refreshUser, logout } = useUserStore();
  const [showLogin, setShowLogin] = useState(false);
  const [draft, setDraft] = useState('');
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [routes, setRoutes] = useState<readonly SovereignLlmRouteOption[]>([]);
  const [selectedRoute, setSelectedRoute] = useState('');
  const [routeError, setRouteError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runtimeState, setRuntimeState] = useState<'checking' | 'ready' | 'degraded'>('checking');
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const [activeMenu, setActiveMenu] = useState<ReleaseMenuKey>('chat');
  const [repoTarget, setRepoTarget] = useState<ReleaseRepoTarget | null>(null);
  const [agentJob, setAgentJob] = useState<SovereignAgentJobSnapshot | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const routeSelectRef = useRef<HTMLSelectElement>(null);
  const sequenceRef = useRef(0);
  const agentClient = useMemo(() => createSovereignAgentClient({
    config: resolveSovereignAgentConfig(),
  }), []);

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
  }, [messages, busy]);

  const model = selectedRoute || DEV_CHAT_WORKER_DEFAULT_MODEL;
  const activeRoute = useMemo(
    () => routes.find((route) => route.id === selectedRoute),
    [routes, selectedRoute],
  );
  const githubConnected = Boolean(user?.githubId || user?.githubUsername);
  const runtimeLamp = runtimeState === 'ready' ? 'green' : runtimeState === 'checking' ? 'yellow' : 'red';
  const guide = useMemo(() => deriveReleaseGuideState({
    lamp: runtimeLamp,
    title: 'Sovereign Play Release',
    message: runtimeState === 'ready' ? 'LLM Runtime bereit' : runtimeState === 'checking' ? 'Runtime wird geprüft' : 'Runtime eingeschränkt',
    action: busy ? 'Auftrag wird analysiert' : 'Chat bereit',
    thinking: busy,
    source: 'play-release-chat',
  }), [busy, runtimeLamp, runtimeState]);

  const activateMenu = (menu: ReleaseMenuKey) => {
    setActiveMenu(menu);
    window.setTimeout(() => {
      if (menu === 'chat') composerRef.current?.focus();
      if (menu === 'models') routeSelectRef.current?.focus();
      if (menu === 'account' && !user) setShowLogin(true);
    }, 0);
  };

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

  const waitForRepositoryJob = async (initial: SovereignAgentJobSnapshot): Promise<SovereignAgentJobSnapshot> => {
    let snapshot = initial;
    if (!snapshot.jobId) throw new Error('Repository-Ausführung lieferte keine Job-ID.');
    for (let attempt = 0; attempt < 24; attempt += 1) {
      if (isSovereignAgentTerminalStatus(snapshot.status) || snapshot.status === 'waiting-for-user') return snapshot;
      await new Promise((resolve) => window.setTimeout(resolve, 1250));
      snapshot = await agentClient.getJob(snapshot.jobId);
      setAgentJob(snapshot);
    }
    return snapshot;
  };

  const publishDraftForJob = async (snapshot: SovereignAgentJobSnapshot): Promise<void> => {
    if (!snapshot.jobId) throw new Error('Draft-PR-Pfad benötigt eine bestätigte Job-ID.');
    const preparation = await agentClient.prepareDraftPr(snapshot.jobId);
    if (!preparation.ok || !preparation.draftPrPreparation.allowed || preparation.draftPrPreparation.canCreateDraftPr === false) {
      const blocker = preparation.draftPrPreparation.blockers.join('; ')
        || preparation.draftPrPreparation.summary
        || preparation.draftPrPreparation.nextAction
        || 'Draft-PR-Gate hat die Veröffentlichung nicht freigegeben.';
      addMessage('system', `Änderungen liegen im Runtime-Workspace, aber Draft PR ist blockiert: ${blocker}`);
      return;
    }
    const created = await agentClient.createDraftPr(snapshot.jobId);
    setAgentJob({ ...snapshot, draftPrUrl: created.draftPrCreate.prUrl });
    addMessage(
      'assistant',
      `Draft PR erstellt und von GitHub zurückgelesen:\n${created.draftPrCreate.prUrl}\nHead: ${created.draftPrCreate.readbackHeadSha.slice(0, 12)} · CI: ${created.draftPrCreate.ciState}`,
    );
  };

  const executeRepositoryAction = async (args: {
    readonly text: string;
    readonly actionTitle: string;
    readonly intent: string;
    readonly target: ReleaseRepoTarget;
  }): Promise<void> => {
    setActiveMenu('github');
    addMessage('system', `GitHub-Auftrag erkannt · ${args.target.label} · Start nur über die revisionsgebundene Agent-Runtime.`);
    let snapshot = await agentClient.startRepositoryExecution({
      repoUrl: args.target.repoUrl,
      branch: args.target.branch,
      mission: args.actionTitle || args.text,
      evidenceText: args.text,
    });
    setAgentJob(snapshot);
    snapshot = await waitForRepositoryJob(snapshot);
    setAgentJob(snapshot);

    if (snapshot.status === 'waiting-for-user') {
      addMessage('system', 'GitHub-Ausführung wartet auf eine Nutzerentscheidung. Es wurde kein Erfolg behauptet.');
      return;
    }
    if (snapshot.status === 'blocked' || snapshot.status === 'failed') {
      addMessage('system', `GitHub-Ausführung blockiert: ${snapshot.lastError || summarizeSovereignAgentJob(snapshot)}`);
      return;
    }
    if (!isSovereignAgentTerminalStatus(snapshot.status)) {
      addMessage('system', `GitHub-Ausführung läuft weiter (${snapshot.status}). Noch kein Abschluss-Readback vorhanden.`);
      return;
    }
    if (snapshot.draftPrUrl) {
      addMessage('assistant', `GitHub-Änderung ist als Draft PR belegt:\n${snapshot.draftPrUrl}`);
      return;
    }
    if (snapshot.changedFiles.length === 0) {
      addMessage('system', 'Agent-Run ist abgeschlossen, aber es sind keine geänderten Dateien belegt. Kein Draft PR wurde erzeugt.');
      return;
    }

    if (args.intent !== 'draft_pr') {
      addMessage('assistant', `Repository-Run abgeschlossen · ${snapshot.changedFiles.length} geänderte Datei(en) im Runtime-Readback. Kein externer GitHub-Write wurde ausgeführt. Für Veröffentlichung ausdrücklich „Draft PR erstellen“ beauftragen.`);
      return;
    }
    await publishDraftForJob(snapshot);
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

    const conversation: DevChatWorkerMessage[] = [
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

    try {
      const parsedRepo = parseDevChatGithubUrl(text);
      const nextRepoTarget = parsedRepo
        ? {
            repoUrl: parsedRepo.repoUrl,
            branch: parsedRepo.branch,
            label: `${parsedRepo.owner}/${parsedRepo.repo}`,
          }
        : repoTarget;
      if (parsedRepo) setRepoTarget(nextRepoTarget);

      if (nextRepoTarget) {
        const recentMessages = messages
          .filter((entry) => entry.role === 'user' || entry.role === 'assistant')
          .slice(-6)
          .map((entry): DevChatWorkerMessage => ({
            role: entry.role as 'user' | 'assistant',
            content: entry.text,
          }));
        const interpreted = await fetchSovereignDirectLlmInterpretation({
          preferredModel: model,
          text,
          repoContext: `${nextRepoTarget.label} · ${nextRepoTarget.branch}`,
          runtimeContext: agentJob
            ? `Letzter belegter Agent-Status: ${agentJob.status}; Draft PR: ${agentJob.draftPrUrl || 'none'}`
            : 'Noch kein Agent-Run in diesem Chat.',
          recentMessages,
        });

        if (interpreted.ok && interpreted.interpretation) {
          const interpretation = interpreted.interpretation;
          setRuntimeState('ready');
          if (interpretation.mode === 'chat') {
            addMessage('assistant', interpretation.assistantText);
            return;
          }
          if (interpretation.intent === 'load_repo') {
            addMessage('assistant', `Repository-Ziel gebunden: ${nextRepoTarget.label} · ${nextRepoTarget.branch}. Noch keine Änderung ausgeführt.`);
            setActiveMenu('github');
            return;
          }
          if (interpretation.intent === 'status') {
            if (!agentJob?.jobId) {
              addMessage('assistant', 'Für dieses Chat-Repository gibt es noch keinen belegten Agent-Run.');
              return;
            }
            const current = await agentClient.getJob(agentJob.jobId);
            setAgentJob(current);
            addMessage('assistant', summarizeSovereignAgentJob(current));
            return;
          }
          if (interpretation.actionDisposition !== 'execute') {
            addMessage(
              'assistant',
              interpretation.assistantText
                || `Änderungsauftrag erkannt: ${interpretation.actionTitle}. Für eine GitHub-Ausführung bitte ausdrücklich die Ausführung beauftragen.`,
            );
            return;
          }
          if (interpretation.intent === 'draft_pr' && agentJob?.jobId && agentJob.changedFiles.length > 0 && !agentJob.draftPrUrl) {
            await publishDraftForJob(agentJob);
            return;
          }
          if (['direct_patch', 'code_execution', 'draft_pr', 'repair_workflow'].includes(interpretation.intent)) {
            await executeRepositoryAction({
              text,
              actionTitle: interpretation.actionTitle,
              intent: interpretation.intent,
              target: nextRepoTarget,
            });
            return;
          }
          addMessage('assistant', interpretation.assistantText || 'Der erkannte Auftrag ist für die Play-Release-GitHub-Lane nicht freigegeben.');
          return;
        }

        if (interpreted.rawContent) {
          addMessage('system', 'Die LLM-Antwort war kein gültiger Aktionsvertrag. Sie wurde nicht zur GitHub-Ausführung verwendet.');
        }
      }

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
    } catch (error) {
      setLastFailedText(text);
      setRuntimeState('degraded');
      addMessage('system', `LLM-Verbindung fehlgeschlagen: ${error instanceof Error ? error.message : 'unbekannter Fehler'}`);
    } finally {
      setBusy(false);
    }
  };

  const runtimeColor = runtimeState === 'ready' ? C.green : runtimeState === 'degraded' ? C.rose : C.amber;
  const runtimeLabel = runtimeState === 'ready' ? 'LLM bereit' : runtimeState === 'degraded' ? 'LLM eingeschränkt' : 'LLM wird geprüft';
  const sessionColor = user ? C.green : C.amber;
  const githubColor = githubConnected ? C.green : user ? C.amber : C.muted;

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
        .release-chat-header { padding-top: max(8px, env(safe-area-inset-top)); }
        .release-chat-shell { width: 100%; max-width: 1120px; margin: 0 auto; }
        .release-chat-composer { padding-bottom: max(10px, env(safe-area-inset-bottom)); }
        .release-chat-menu-scroll { scrollbar-width: none; }
        .release-chat-menu-scroll::-webkit-scrollbar { display: none; }
        @media (max-width: 720px) {
          .release-chat-title-sub { display: none; }
          .release-chat-status-label { display: none; }
          .release-chat-route { min-width: 168px !important; max-width: 210px !important; }
        }
      `}</style>

      <header
        className="release-chat-header"
        style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.surface }}
      >
        <div className="release-chat-shell" style={{ minHeight: 58, display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px' }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, display: 'grid', placeItems: 'center', background: C.accent + '18', border: `1px solid ${C.accent}44`, color: C.accent, fontWeight: 800 }}>S</div>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 750, fontSize: 15 }}>Sovereign</div>
            <div className="release-chat-title-sub" style={{ color: C.sub, fontSize: 10.5 }}>Chat · stabiler Play-Release-Modus</div>
          </div>
          <span
            data-testid="release-guide-mood"
            title={guide.helperMessage}
            aria-label={`Sovereign Status ${guide.mood}`}
            style={{ fontSize: 19, lineHeight: 1, whiteSpace: 'nowrap' }}
          >
            {guide.mood}
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
      </header>

      <nav
        data-testid="play-release-menu-frame"
        aria-label="Sovereign Hauptmenü"
        style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: '#0f151e' }}
      >
        <div
          className="release-chat-shell release-chat-menu-scroll"
          style={{ minHeight: 52, display: 'flex', alignItems: 'center', gap: 7, padding: '6px 10px', overflowX: 'auto' }}
        >
          {([
            ['chat', '💬', 'Chat'],
            ['github', '⌘', 'GitHub'],
            ['models', '◫', 'Modelle'],
            ['account', '◉', 'Konto'],
          ] as const).map(([key, icon, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={activeMenu === key}
              onClick={() => activateMenu(key)}
              style={{
                minHeight: 38,
                minWidth: 42,
                padding: '0 10px',
                borderRadius: 9,
                border: `1px solid ${activeMenu === key ? C.accent + '77' : C.border}`,
                background: activeMenu === key ? C.accent + '12' : C.bg,
                color: activeMenu === key ? C.accent : C.sub,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              <span aria-hidden="true">{icon}</span>
              <span className="release-chat-nav-label">{label}</span>
            </button>
          ))}

          <select
            ref={routeSelectRef}
            className="release-chat-route"
            aria-label="LLM Route"
            value={selectedRoute}
            onFocus={() => setActiveMenu('models')}
            onChange={(event) => setSelectedRoute(event.target.value)}
            disabled={!user}
            style={{
              marginLeft: 2,
              minWidth: 205,
              maxWidth: 280,
              minHeight: 38,
              borderRadius: 9,
              border: `1px solid ${activeMenu === 'models' ? C.accent + '77' : C.border}`,
              background: C.bg,
              color: user ? C.text : C.muted,
              padding: '0 9px',
              fontSize: 11,
            }}
          >
            <option value="">{user ? 'Auto · FreeLLM zuerst' : 'Modelle · nach Anmeldung'}</option>
            {routes.map((route) => <option key={route.id} value={route.id}>{routeLabel(route)}</option>)}
          </select>

          <span style={{ flex: 1, minWidth: 6 }} />
          <span title={runtimeLabel} aria-label={runtimeLabel} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: C.sub, fontSize: 9.5, whiteSpace: 'nowrap' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: runtimeColor, boxShadow: `0 0 7px ${runtimeColor}88` }} />
            <span className="release-chat-status-label">LLM</span>
          </span>
          <span title={githubConnected ? `GitHub ${user?.githubUsername ? `@${user.githubUsername}` : 'verbunden'}` : 'GitHub noch nicht verbunden'} aria-label={githubConnected ? 'GitHub verbunden' : 'GitHub nicht verbunden'} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: C.sub, fontSize: 9.5, whiteSpace: 'nowrap' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: githubColor, boxShadow: githubConnected ? `0 0 7px ${githubColor}88` : undefined }} />
            <span className="release-chat-status-label">GitHub</span>
          </span>
          <span title={user ? 'Session bestätigt' : 'Nicht angemeldet'} aria-label={user ? 'Session bestätigt' : 'Session nicht bestätigt'} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: C.sub, fontSize: 9.5, whiteSpace: 'nowrap' }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: sessionColor, boxShadow: user ? `0 0 7px ${sessionColor}88` : undefined }} />
            <span className="release-chat-status-label">Session</span>
          </span>
        </div>
      </nav>

      {activeMenu !== 'chat' && (
        <div style={{ flexShrink: 0, borderBottom: `1px solid ${C.border}`, background: C.surface }}>
          <div className="release-chat-shell" style={{ minHeight: 34, display: 'flex', alignItems: 'center', padding: '5px 12px', color: C.sub, fontSize: 10.5 }}>
            {activeMenu === 'github' && (
              <span>
                {repoTarget ? `Repo: ${repoTarget.label} · ${repoTarget.branch}` : 'Noch kein Repository-Ziel im Chat gebunden.'}
                {agentJob ? ` · Agent: ${agentJob.status}${agentJob.draftPrUrl ? ' · Draft PR belegt' : ''}` : ''}
                {githubConnected
                  ? ` · GitHub${user?.githubUsername ? ` @${user.githubUsername}` : ''} verbunden.`
                  : ' · User-GitHub-Identität nicht bestätigt; Backend-Gates entscheiden fail-closed.'}
              </span>
            )}
            {activeMenu === 'models' && (activeRoute ? `Aktiv: ${routeLabel(activeRoute)}` : 'Automatische Free-first-Routenwahl. Eine manuell gewählte Route bleibt hart fixiert.')}
            {activeMenu === 'account' && (user ? `${user.email} · ${user.credits} Credits` : 'Für Runtime- und GitHub-Aktionen bitte anmelden.')}
          </div>
        </div>
      )}

      <div ref={listRef} className="release-chat-shell" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '16px 14px 20px', scrollBehavior: 'smooth' }}>
        {messages.length === 0 ? (
          <div style={{ minHeight: '55vh', display: 'grid', placeItems: 'center', textAlign: 'center', padding: 20 }}>
            <div style={{ maxWidth: 520 }}>
              <div style={{ width: 54, height: 54, margin: '0 auto 16px', borderRadius: 16, display: 'grid', placeItems: 'center', color: C.accent, background: C.accent + '12', border: `1px solid ${C.accent}33`, fontSize: 22, fontWeight: 800 }}>S</div>
              <h1 style={{ margin: 0, fontSize: 22, letterSpacing: '-.02em' }}>Was möchtest du wissen oder erledigen?</h1>
              <p style={{ color: C.sub, fontSize: 13, lineHeight: 1.6, margin: '10px auto 0' }}>
                Sovereign nutzt den aktuellen serverseitigen LLM-Routenkatalog. Zugangsdaten bleiben außerhalb des Chats.
              </p>
              {!user && <button type="button" onClick={() => setShowLogin(true)} style={{ marginTop: 18, minHeight: 44, padding: '0 18px', borderRadius: 10, border: 'none', background: C.accent, color: '#07111c', fontWeight: 800, cursor: 'pointer' }}>Mit E-Mail anmelden</button>}
            </div>
          </div>
        ) : messages.map((entry) => <Bubble key={entry.id} entry={entry} />)}
        {busy && (
          <div role="status" style={{ color: C.sub, fontSize: 12, padding: '8px 3px' }}>Sovereign antwortet…</div>
        )}
      </div>

      <footer className="release-chat-composer" style={{ flexShrink: 0, borderTop: `1px solid ${C.border}`, background: C.surface }}>
        <div className="release-chat-shell" style={{ padding: '10px 12px 0' }}>
          {activeRoute && <div style={{ color: C.muted, fontSize: 9.5, marginBottom: 5 }}>Route fixiert: {routeLabel(activeRoute)} · kein stiller Routenwechsel</div>}
          {lastFailedText && !busy && (
            <button type="button" onClick={() => { void submit(lastFailedText); }} style={{ marginBottom: 7, minHeight: 36, padding: '0 11px', borderRadius: 8, border: `1px solid ${C.amber}55`, background: C.amber + '10', color: C.amber, cursor: 'pointer' }}>
              Letzte Anfrage erneut versuchen
            </button>
          )}
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <textarea
              ref={composerRef}
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
              placeholder={user ? 'Nachricht an Sovereign…' : 'Zum Chatten bitte anmelden…'}
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
            <span>{routeError ?? 'Enter sendet · Shift+Enter neue Zeile'}</span>
          </div>
        </div>
      </footer>

      {showLogin && <LoginModal onClose={() => setShowLogin(false)} />}
    </main>
  );
}

export default PlayReleaseChat;
