import React, { useEffect, useMemo, useReducer, useState } from 'react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'motion/react';
import { Code, Cpu, FolderGit2, GitMerge, Lock, Server, Terminal, Volume2, VolumeX } from 'lucide-react';
import { useUserStore } from '../user/useUserStore';
import { SovereignAdapterProvider, useSovereignAdapter } from './adapter/context';
import type { SovereignBackendAdapter } from './adapter/interface';
import { ArchitectureModal } from './components/Architecture/ArchitectureModal';
import { OperatorAuthModal } from './components/Auth/OperatorAuthModal';
import { ChatSurface } from './components/ChatSurface/ChatSurface';
import { CyborgOcularMatrix } from './components/CyborgOcularMatrix/CyborgOcularMatrix';
import { IntegrationModal } from './components/IntegrationPlus/IntegrationModal';
import { OwnerInteractionModal } from './components/OwnerInteraction/OwnerInteractionModal';
import { PublicationInspector } from './components/PublicationInspector/PublicationInspector';
import { NeuralLoadMonitor } from './components/RuntimeMonitor/NeuralLoadMonitor';
import { RuntimeMonitor } from './components/RuntimeMonitor/RuntimeMonitor';
import { SkillRegistryDrawer } from './components/Skills/SkillRegistryDrawer';
import { ToolchainDock } from './components/Toolchain/ToolchainDock';
import { WorkspaceProjection } from './components/WorkspaceProjection/WorkspaceProjection';
import { INITIAL_FSM_STATE, jobStateReducer } from './fsm/jobStateMachine';
import { useOwnerInteraction } from './hooks/useOwnerInteraction';
import { useSovereignJob } from './hooks/useSovereignJob';
import { useSwarmRun } from './hooks/useSwarmRun';
import './theme/biomodular.css';
import type { ChatMessage, OwnerInteractionResponse } from './types/domain';
import { getAudioMuted, playKeystrokeChirp, toggleAudioMute } from './utils/audio';
import { cx } from './utils/cx';

const MOBILE_TABS = ['chat', 'monitor', 'workspace', 'publication'] as const;
type MobileTab = (typeof MOBILE_TABS)[number];

function currentDesktopLayout(): boolean {
  if (typeof window === 'undefined') return true;
  if (typeof window.matchMedia === 'function') {
    return window.matchMedia('(min-width: 768px)').matches;
  }
  return window.innerWidth >= 768;
}

function useDesktopLayout(): boolean {
  const [isDesktop, setIsDesktop] = useState(currentDesktopLayout);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const media = typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 768px)')
      : null;
    const update = () => setIsDesktop(media ? media.matches : window.innerWidth >= 768);

    update();
    media?.addEventListener('change', update);
    window.addEventListener('resize', update);
    return () => {
      media?.removeEventListener('change', update);
      window.removeEventListener('resize', update);
    };
  }, []);

  return isDesktop;
}

function Dashboard() {
  const adapter = useSovereignAdapter();
  const { user, ensureGuestSession } = useUserStore();
  const [sessionReady, setSessionReady] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [audioMuted, setAudioMuted] = useState(getAudioMuted());
  const [authOpen, setAuthOpen] = useState(false);
  const [architectureOpen, setArchitectureOpen] = useState(false);
  const [toolchainOpen, setToolchainOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);
  const [integrationsOpen, setIntegrationsOpen] = useState(false);
  const [mobileTab, setMobileTab] = useState<MobileTab>('chat');
  const [fsmState, dispatchFsm] = useReducer(jobStateReducer, INITIAL_FSM_STATE);
  const isDesktopLayout = useDesktopLayout();

  useEffect(() => {
    let mounted = true;
    void ensureGuestSession().finally(() => { if (mounted) setSessionReady(true); });
    return () => { mounted = false; };
  }, [ensureGuestSession]);

  const manifestsEnabled = sessionReady && Boolean(user);
  const toolchains = useQuery({ queryKey: ['vnext-toolchains'], queryFn: () => adapter.getToolchains(), enabled: manifestsEnabled, retry: false });
  const skills = useQuery({ queryKey: ['vnext-skills'], queryFn: () => adapter.getSkills(), enabled: manifestsEnabled, retry: false });
  const integrations = useQuery({ queryKey: ['vnext-integrations'], queryFn: () => adapter.getIntegrations(), enabled: manifestsEnabled, retry: false });
  const activeSkillIds = useMemo(() => (skills.data ?? []).map((item) => item.id), [skills.data]);
  const selectedToolchain = toolchains.data?.find((item) => item.status === 'active') ?? toolchains.data?.[0];

  const {
    job,
    isPolling,
    abort,
    workspace,
    publication,
    prepareDraftPr,
    isPreparingDraftPr,
    draftPrPreparation,
    prepareError,
    publishDraftPr,
    isPublishing,
    publishError,
  } = useSovereignJob(activeRunId);
  const swarmRun = useSwarmRun();
  const { submitInteraction, isSubmitting: isInteracting } = useOwnerInteraction(activeRunId);

  const [messages, setMessages] = useState<ChatMessage[]>([{
    id: 'vnext-loaded',
    role: 'system',
    sender: 'SYSTEM',
    content: 'SOVEREIGN CONTROL SURFACE vNEXT LOADED.\nNo runtime success is implied by UI startup. Waiting for authenticated server session and live manifest/readback evidence.',
    timestamp: new Date().toISOString(),
  }]);

  useEffect(() => {
    if (job?.phase) dispatchFsm({ type: 'BACKEND_PHASE_UPDATE', payload: { phase: job.phase } });
  }, [job?.phase]);

  useEffect(() => {
    const pr = job?.draftPR;
    if (!pr || job?.phase !== 'COMPLETED') return;
    setMessages((current) => {
      if (current.some((message) => message.content.includes(pr.url))) return current;
      return [...current, {
        id: `pr-${pr.pullRequestNumber}`,
        role: 'assistant',
        sender: 'SOVEREIGN_SWARM',
        content: `DRAFT PR CREATED AND INDEPENDENTLY READ BACK.\n${pr.url}\nReadback head: ${pr.readbackHeadSha}\nCI: ${pr.ciState}. No merge was performed.`,
        evidenceBadge: `#${pr.pullRequestNumber} GITHUB READBACK`,
        timestamp: new Date().toISOString(),
      }];
    });
  }, [job?.draftPR, job?.phase]);

  const currentPhase = job?.phase ?? fsmState.currentPhase;
  const publishFailure = publishError instanceof Error ? publishError.message : prepareError instanceof Error ? prepareError.message : undefined;

  const submitMission = async (mission: string) => {
    if (!sessionReady || !user || user.isGuest) {
      setMessages((current) => [...current, {
        id: `auth-${Date.now()}`,
        role: 'system',
        sender: 'SYSTEM',
        content: !sessionReady ? 'Backend session readback is still pending. No mission was sent.' : 'Repository execution requires an authenticated account. No mission was sent.',
        timestamp: new Date().toISOString(),
      }]);
      setAuthOpen(true);
      return;
    }

    dispatchFsm({ type: 'SUBMIT_ORDER', payload: { objective: mission } });
    setMessages((current) => [...current, { id: `owner-${Date.now()}`, role: 'human', sender: 'HUMAN', content: mission, timestamp: new Date().toISOString() }]);
    try {
      const accepted = await swarmRun.mutateAsync({ prompt: mission, toolchains: selectedToolchain ? [selectedToolchain.id] : [], activeSkillIds });
      setActiveRunId(accepted.jobId);
      dispatchFsm({ type: 'BACKEND_ACCEPTED', payload: { jobId: accepted.jobId } });
      setMessages((current) => [...current, {
        id: `accepted-${accepted.jobId}`,
        role: 'assistant',
        sender: 'SOVEREIGN_SWARM',
        content: `PERSISTED RUN ACCEPTED :: [${accepted.jobId}].\nAwaiting exact run/job/evidence readback. No completion or publication is implied.`,
        timestamp: new Date().toISOString(),
      }]);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      dispatchFsm({ type: 'EXECUTION_FAILED', payload: { error: message } });
      setMessages((current) => [...current, { id: `failed-${Date.now()}`, role: 'system', sender: 'SYSTEM', content: `EXECUTION START FAILED :: ${message}`, timestamp: new Date().toISOString() }]);
    }
  };

  const respondToOwner = async (response: OwnerInteractionResponse | string, extra?: string) => {
    if (!job?.pendingInteraction) return;
    const value = typeof response === 'object' ? response : { interactionId: job.pendingInteraction.id, response: extra ?? response };
    if (!value.response.trim()) return;
    await submitInteraction(value);
    dispatchFsm({ type: 'OWNER_INPUT_SUBMITTED' });
    setMessages((current) => [...current, { id: `owner-response-${Date.now()}`, role: 'human', sender: 'HUMAN', content: `[OWNER RESPONSE SENT TO RUN]: ${value.response}`, timestamp: new Date().toISOString() }]);
  };

  const command = (
    <ChatSurface
      messages={messages}
      onSendMessage={submitMission}
      jobPhase={currentPhase}
      activeJob={job}
      onAbortJob={activeRunId ? () => void abort() : undefined}
      onTypingStateChange={setIsTyping}
      onOpenToolchain={() => setToolchainOpen(true)}
      onOpenSkills={() => setSkillsOpen(true)}
      onOpenIntegrations={() => setIntegrationsOpen(true)}
      activeToolchainName={selectedToolchain?.name ?? 'MANIFEST NOT YET VERIFIED'}
      activeSkillsCount={activeSkillIds.length}
      activeIntegrationsCount={(integrations.data ?? []).length}
    />
  );
  const monitor = <><NeuralLoadMonitor job={job} phase={currentPhase} /><RuntimeMonitor job={job} isPolling={isPolling} /></>;
  const workspacePanel = <WorkspaceProjection workspace={workspace} />;
  const publicationPanel = (
    <PublicationInspector
      publication={publication}
      draftPR={job?.draftPR}
      jobPhase={currentPhase}
      preparation={draftPrPreparation}
      onPrepare={prepareDraftPr}
      onPublish={publishDraftPr}
      isPreparing={isPreparingDraftPr}
      isPublishing={isPublishing}
      publishError={publishFailure}
    />
  );

  return (
    <div className="flex flex-col h-[100dvh] w-full overflow-hidden bg-[var(--bg-void)] text-[var(--text-main)] selection:bg-[var(--red-pulse)] selection:text-white font-sans carbon-mesh-bg" data-testid="sovereign-control-surface-vnext">
      <header className="h-14 sm:h-16 md:h-20 bg-[var(--carbon-deep)] border-b border-[rgba(255,30,56,0.22)] px-2.5 sm:px-4 md:px-6 flex items-center justify-between shrink-0 z-30 shadow-[0_4px_20px_rgba(0,0,0,0.8)] relative">
        <div className="absolute top-0 left-0 right-0 h-[1.5px] bg-gradient-to-r from-transparent via-[var(--red-laser)] to-transparent" />
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg bg-[var(--carbon-surface)] border border-[var(--red-laser)] flex items-center justify-center text-[var(--red-laser)] shadow-[0_0_15px_rgba(255,30,56,0.4)] theme-diamond-cut shrink-0"><Cpu size={20} className="animate-pulse" /></div>
          <div className="min-w-0"><div className="flex items-center gap-2"><span className="font-mono text-[11px] sm:text-sm font-black tracking-widest text-white truncate">SOVEREIGN STUDIO ATO</span><span className="hidden sm:inline px-1.5 rounded bg-[rgba(255,30,56,0.15)] text-[var(--red-laser)] border border-[rgba(255,30,56,0.3)] font-mono text-[9px] font-bold">vNEXT</span></div><div className="hidden sm:block text-[9px] font-mono text-[var(--text-dim)]">CYBERNETIC CONTROL SURFACE // RUNTIME TRUTH BOUND</div></div>
        </div>

        <div className="flex items-center gap-1.5 sm:gap-3">
          <CyborgOcularMatrix isTyping={isTyping} jobPhase={currentPhase} />
          <button type="button" data-testid="operator-auth-btn" onClick={() => setAuthOpen(true)} className={cx('min-h-9 px-2 rounded border font-mono text-[9px] sm:text-[10px] font-bold flex items-center gap-1.5', user && !user.isGuest ? 'bg-[var(--carbon-surface)] border-[rgba(16,185,129,0.35)] text-white' : 'bg-[rgba(255,30,56,0.12)] border-[var(--red-laser)] text-white')}><Lock size={11} className={user && !user.isGuest ? 'text-[var(--emerald-seal)]' : 'text-[var(--red-laser)]'} /><span className="hidden sm:inline max-w-24 truncate">{user && !user.isGuest ? user.displayName : sessionReady ? 'AUTH' : 'SESSION…'}</span></button>
          <button type="button" data-testid="open-architecture-btn" onClick={() => setArchitectureOpen(true)} className="min-h-9 px-2 rounded border border-white/10 bg-[var(--carbon-surface)] text-[var(--text-muted)] hover:text-white hover:border-[var(--red-laser)] font-mono text-[9px] flex items-center gap-1"><Server size={12} className="text-[var(--red-laser)]" /><span className="hidden md:inline">SPEC</span></button>
          <button type="button" onClick={() => setAudioMuted(toggleAudioMute())} className="min-h-9 px-2 rounded border border-white/10 bg-[var(--carbon-surface)] text-[var(--text-muted)] hover:text-white">{audioMuted ? <VolumeX size={12} /> : <Volume2 size={12} />}</button>
        </div>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden">
        {isDesktopLayout ? (
          <div className="flex w-full h-full" data-testid="vnext-desktop-layout">
            <div className="w-3/5 lg:w-3/4 min-w-0 h-full">{command}</div>
            <aside className="w-2/5 lg:w-1/4 min-w-[290px] max-w-[460px] h-full bg-[var(--carbon-deep)] border-l border-[rgba(255,30,56,0.18)] flex flex-col overflow-hidden">
              <div className="shrink-0"><NeuralLoadMonitor job={job} phase={currentPhase} /></div>
              <div className="flex-1 min-h-0 border-b border-white/5"><RuntimeMonitor job={job} isPolling={isPolling} /></div>
              <div className="h-[28%] min-h-[130px] border-b border-white/5">{workspacePanel}</div>
              <div className="h-[31%] min-h-[150px]">{publicationPanel}</div>
            </aside>
          </div>
        ) : (
          <div className="flex flex-col w-full h-full" data-testid="vnext-mobile-layout">
            <div className="flex-1 min-h-0 relative overflow-hidden">
              <AnimatePresence mode="wait">
                <motion.div key={mobileTab} initial={{ opacity: 0, x: 18 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -18 }} transition={{ duration: 0.18 }} className="absolute inset-0 overflow-hidden">
                  {mobileTab === 'chat' ? command : mobileTab === 'monitor' ? <div className="h-full flex flex-col">{monitor}</div> : mobileTab === 'workspace' ? workspacePanel : publicationPanel}
                </motion.div>
              </AnimatePresence>
            </div>
            <nav className="grid grid-cols-4 bg-[var(--carbon-surface)] border-t border-[rgba(255,30,56,0.2)] px-1 py-1 pb-[max(.25rem,env(safe-area-inset-bottom))] shrink-0" data-testid="mobile-bottom-nav">
              {[{ id: 'chat', label: 'COMMAND', icon: Terminal }, { id: 'monitor', label: 'EVIDENCE', icon: Code }, { id: 'workspace', label: 'WORKSPACE', icon: FolderGit2 }, { id: 'publication', label: 'PUBLISH', icon: GitMerge }].map(({ id, label, icon: Icon }) => <button key={id} type="button" onClick={() => { playKeystrokeChirp(); setMobileTab(id as MobileTab); }} className={cx('relative min-h-12 rounded-lg flex flex-col items-center justify-center gap-0.5 font-mono text-[8px] font-bold', mobileTab === id ? 'text-[var(--red-laser)] bg-[rgba(255,30,56,0.1)] border border-[rgba(255,30,56,0.25)]' : 'text-[var(--text-muted)]')}><Icon size={15} /><span>{label}</span></button>)}
            </nav>
          </div>
        )}
      </main>

      <ToolchainDock isOpen={toolchainOpen} onClose={() => setToolchainOpen(false)} toolchains={toolchains.data ?? []} selectedToolchainId={selectedToolchain?.id} />
      <SkillRegistryDrawer isOpen={skillsOpen} onClose={() => setSkillsOpen(false)} skills={skills.data ?? []} activeSkillIds={activeSkillIds} />
      <IntegrationModal isOpen={integrationsOpen} onClose={() => setIntegrationsOpen(false)} integrations={integrations.data ?? []} />
      <OperatorAuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} />
      <ArchitectureModal isOpen={architectureOpen} onClose={() => setArchitectureOpen(false)} />
      <OwnerInteractionModal interaction={job?.pendingInteraction} onSubmit={respondToOwner} isSubmitting={isInteracting} />
    </div>
  );
}

export default function SovereignControlSurfaceVNext({ adapter }: { adapter?: SovereignBackendAdapter }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } } }));
  return (
    <QueryClientProvider client={queryClient}>
      <SovereignAdapterProvider adapter={adapter}>
        <Dashboard />
      </SovereignAdapterProvider>
    </QueryClientProvider>
  );
}
