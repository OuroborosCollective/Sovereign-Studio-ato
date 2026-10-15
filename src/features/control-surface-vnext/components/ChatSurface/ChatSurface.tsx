import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Blocks, Bot, BrainCircuit, Cpu, Loader2, Send, Square, Terminal, User, Wrench } from 'lucide-react';
import type { AgentMode, ChatMessage, ControlSurfaceReadback, ExecutionMode, JobPhase, SovereignJob } from '../../types/domain';
import { RegistryReadbackStatus } from '../RegistryReadbackStatus';
import { ChatMarkdown } from '../../../product/components/ChatMarkdown';
import { playDispatchBlast, playKeystrokeChirp } from '../../utils/audio';

interface Props {
  messages: ChatMessage[];
  onSubmitOrder?: (text: string) => void;
  onSendMessage?: (text: string) => void;
  jobPhase?: JobPhase;
  activeJob?: SovereignJob | null;
  onOpenToolchain?: () => void;
  onOpenSkills?: () => void;
  onOpenIntegrations?: () => void;
  onAbortJob?: () => void;
  isAborting?: boolean;
  abortError?: string;
  onTypingStateChange?: (typing: boolean) => void;
  activeToolchainName?: string;
  activeSkillsCount?: number;
  activeIntegrationsCount?: number;
  agentMode?: AgentMode;
  onAgentModeChange?: (mode: AgentMode) => void;
  executionMode?: ExecutionMode;
  onExecutionModeChange?: (mode: ExecutionMode) => void;
  controlReadback?: ControlSurfaceReadback;
  controlReadbackError?: string;
  isReadingControl?: boolean;
  onRefreshControl?: () => void;
}

const ACTIVE_PHASES: JobPhase[] = ['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING'];

function MessageCard({ message }: { message: ChatMessage }) {
  const human = message.sender === 'HUMAN' || message.role === 'human';
  const system = message.sender === 'SYSTEM' || message.role === 'system';
  return (
    <motion.div initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-2.5 ${human ? 'justify-end' : 'justify-start'}`}>
      {!human && <div className={`w-7 h-7 rounded-md shrink-0 flex items-center justify-center border ${system ? 'bg-[var(--carbon-surface)] border-white/10 text-[var(--text-muted)]' : 'bg-[rgba(255,30,56,0.12)] border-[rgba(255,30,56,0.3)] text-[var(--red-laser)]'}`}>{system ? <Terminal size={13} /> : <Bot size={13} />}</div>}
      <div className={`max-w-[88%] sm:max-w-[82%] rounded-lg border px-3 py-2.5 ${human ? 'bg-[rgba(255,30,56,0.11)] border-[rgba(255,30,56,0.25)]' : 'bg-[var(--carbon-deep)] border-white/5'}`}>
        <div className="whitespace-pre-wrap break-words font-mono text-[10.5px] sm:text-[11px] leading-relaxed text-[var(--text-main)]"><ChatMarkdown content={message.content} /></div>
        <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[8.5px] text-[var(--text-dim)]"><span>{human ? 'OWNER' : system ? 'CONTROL SURFACE' : 'SOVEREIGN READBACK'}</span>{message.evidenceBadge && <span className="text-[var(--emerald-seal)] font-bold">{message.evidenceBadge}</span>}</div>
      </div>
      {human && <div className="w-7 h-7 rounded-md shrink-0 flex items-center justify-center bg-[var(--carbon-surface)] border border-white/10 text-white"><User size={13} /></div>}
    </motion.div>
  );
}

export function ChatSurface({ messages, onSubmitOrder, onSendMessage, jobPhase = 'IDLE', activeJob, onOpenToolchain, onOpenSkills, onOpenIntegrations, onAbortJob, isAborting = false, abortError, onTypingStateChange, activeToolchainName, activeSkillsCount = 0, activeIntegrationsCount = 0, executionMode = 'free', onExecutionModeChange, controlReadback, controlReadbackError, isReadingControl, onRefreshControl }: Props) {
  const [text, setText] = useState('');
  const readbackUnavailable = activeJob?.workspaceState.readbackState === 'unavailable';
  const executing = ACTIVE_PHASES.includes(jobPhase) && !readbackUnavailable;
  const selectedMode = executing ? controlReadback?.jobExecutionMode ?? executionMode : executionMode;
  const free = controlReadback?.routing.modes.find(route => route.mode === 'free');
  const paid = controlReadback?.routing.modes.find(route => route.mode === 'paid');
  const selectedRoute = selectedMode === 'paid' ? paid : free;
  const credit = controlReadback?.credits;
  const paidAvailability = paid?.executionBlocker === 'provider_funded_credits_required'
    ? 'Provider-funded balance required; account credits remain a separate verified balance.'
    : paid?.executionBlocker || paid?.blocker;
  const [, refreshAge] = useState(0);
  React.useEffect(() => {
    const timer = setInterval(() => refreshAge(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const fresh = Boolean(controlReadback && !controlReadbackError && performance.now() - controlReadback.receivedMonotonicMs < 30_000);
  const canSend = text.trim().length > 0 && !executing && fresh && selectedRoute?.available === true;
  const phaseTone = jobPhase === 'FAILED' || jobPhase === 'BLOCKED' ? 'text-[var(--red-alert)]' : jobPhase === 'COMPLETED' ? 'text-[var(--emerald-seal)]' : 'text-white';
  const latestRun = useMemo(() => activeJob?.runId || activeJob?.id, [activeJob?.runId, activeJob?.id]);

  const submit = () => {
    const mission = text.trim();
    if (!mission || !canSend) return;
    playDispatchBlast();
    (onSendMessage ?? onSubmitOrder)?.(mission);
    setText('');
    onTypingStateChange?.(false);
  };

  return (
    <section className="flex flex-col h-full min-h-0 bg-[var(--carbon-base)] border-r border-[rgba(255,30,56,0.18)] relative overflow-hidden" data-testid="vnext-command-surface">
      <div className="px-3 sm:px-4 py-2.5 border-b border-white/5 bg-[var(--carbon-deep)] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 min-w-0"><Terminal size={14} className="text-[var(--red-laser)] shrink-0" /><span className="font-mono text-[10px] sm:text-[11px] font-black tracking-widest text-white truncate">SOVEREIGN MISSION CONSOLE</span>{latestRun && <span className="hidden lg:inline font-mono text-[8.5px] text-[var(--text-dim)] truncate">RUN // {latestRun}</span>}</div>
        <div className="flex items-center gap-2"><span className={`font-mono text-[9px] font-black ${phaseTone}`}>{readbackUnavailable ? 'READBACK UNAVAILABLE' : jobPhase}</span>{executing && onAbortJob && <button type="button" onClick={onAbortJob} disabled={isAborting} aria-busy={isAborting} title={isAborting ? "Abort request in progress..." : "Abort current mission"} className="min-h-12 min-w-12 px-2 rounded border border-[rgba(255,30,56,0.35)] bg-[rgba(255,30,56,0.08)] text-[var(--red-laser)] hover:bg-[var(--red-laser)] hover:text-white disabled:opacity-50 font-mono text-[9px] font-bold flex items-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--red-laser)]">{isAborting ? <Loader2 size={10} className="animate-spin" /> : <Square size={10} />} {isAborting ? 'REQUESTING…' : 'ABORT'}</button>}</div>
      </div>
      {abortError && <div role="alert" className="shrink-0 px-3 py-2 text-[11px] text-[var(--red-alert)] break-words">Abort was not confirmed: {abortError}</div>}

      <div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 space-y-3" data-testid="vnext-message-stream" role="log" aria-live="polite">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-[var(--text-dim)]">
            <Bot size={24} className="mb-2 opacity-50" />
            <p className="text-[11px] font-mono">No missions logged.</p>
            <p className="text-[9px] font-mono mt-1 opacity-75">Dispatch a mission to begin.</p>
          </div>
        ) : (
          messages.map((message) => <MessageCard key={message.id} message={message} />)
        )}
      </div>

      <div data-testid="vnext-mission-dock" className="shrink-0 min-h-0 max-h-[50%] overflow-y-auto overscroll-contain px-3 sm:px-4 pb-3 sm:pb-4 pt-2 bg-[var(--carbon-base)]">
        <details className="mb-2" data-testid="vnext-mission-controls">
          <summary className="min-h-11 cursor-pointer rounded-md border border-white/10 px-2 py-3 font-mono text-[10px] text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20">
            Mission controls · {selectedMode.toUpperCase()} · {!fresh ? 'READBACK UNAVAILABLE' : selectedRoute?.available ? 'ROUTE AVAILABLE' : 'ROUTE BLOCKED'}
          </summary>
        <div className="mt-2 mb-2 grid grid-cols-3 gap-1.5">
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenToolchain?.(); }} title={`Active Toolchain: ${activeToolchainName || 'UNVERIFIED'}`} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] text-left px-2 font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><Wrench size={10} /> TOOLCHAIN</span><span className="block truncate text-[9px] text-white mt-0.5">{activeToolchainName || 'UNVERIFIED'}</span></button>
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenSkills?.(); }} title={`Agents: ${activeSkillsCount} persisted tasks`} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] text-left px-2 font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><BrainCircuit size={10} /> AGENTS</span><span className="block text-[9px] text-white mt-0.5">{activeSkillsCount} PERSISTED TASKS</span></button>
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenIntegrations?.(); }} title={`Backend integrations: ${activeIntegrationsCount} observed`} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] text-left px-2 font-mono focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><Blocks size={10} /> ATTACHMENTS</span><span className="block text-[9px] text-white mt-0.5">{activeIntegrationsCount} OBSERVED</span></button>
        </div>

        <div data-testid="agent-mode-selector" className="mb-2 rounded-lg border border-white/5 bg-[var(--carbon-deep)] p-1.5 font-mono">
          <div className="flex items-center gap-2">
            <span data-testid="agent-mode-single" className="shrink-0 rounded border border-[rgba(16,185,129,0.3)] px-1.5 py-1 text-[7px] font-bold text-[var(--emerald-seal)]">1 AGENT · {selectedMode === 'paid' ? 'OPENROUTER' : 'FREELLM'}</span>
            <label htmlFor="mission-route" className="text-[8px] text-[var(--text-dim)]">ROUTE</label>
            <select id="mission-route" title={executing ? 'Route locked while executing' : !fresh ? 'Route locked while readback is unavailable' : 'Select mission route'} aria-describedby="mission-route-availability" value={selectedMode} disabled={executing || !fresh} onChange={event => onExecutionModeChange?.(event.target.value as ExecutionMode)} className="min-h-11 min-w-0 flex-1 rounded border border-white/10 bg-[var(--carbon-surface)] px-2 text-[10px] text-white disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20 disabled:cursor-not-allowed">
              <option value="free" disabled={!fresh || free?.available !== true}>Sovereign · Free{free?.model ? ` · ${free.model}` : ''}</option>
              <option value="paid" disabled={!fresh || paid?.available !== true}>Sovereign · Paid{paid?.model ? ` · ${paid.model}` : ''}</option>
            </select>
          </div>
          {paidAvailability && <p className="mt-1 text-[9px] text-[var(--text-muted)]">Paid availability: {paidAvailability}</p>}
          <div className="mt-2 text-[9px] text-[var(--text-main)]" data-testid="vnext-account-credits">
            {credit?.readbackState === 'live' && credit.creditStateVerified ? <>{credit.credits?.toLocaleString('en-US')} ACCOUNT CREDITS · {credit.providerFundedCredits?.toLocaleString('en-US')} PROVIDER-FUNDED</> : <>CREDITS UNAVAILABLE: {credit?.blocker || 'Awaiting authenticated ledger readback'}</>}
          </div>
          <RegistryReadbackStatus observedAt={controlReadback?.observedAt} receivedMonotonicMs={controlReadback?.receivedMonotonicMs} isLoading={isReadingControl} readbackError={controlReadbackError} onRefresh={onRefreshControl} />
        </div>

        </details>
          <p id="mission-route-availability" className="mt-1 text-[8px] text-[var(--text-dim)]">{selectedMode === 'paid' ? 'Paid · direct OpenRouter. Dispatch authorizes a credit reservation; actual provider usage is settled and unused reserved credits are refunded.' : 'Free · direct FreeLLM. No credit deduction and no automatic switch to Paid.'}</p>
          {!selectedRoute?.available && <p className="mt-1 text-[9px] text-[var(--red-alert)]">Selected route unavailable: {selectedRoute?.executionBlocker || selectedRoute?.blocker || 'route_readback_unavailable'}</p>}

        <div className="theme-diamond-cut rounded-xl border border-[rgba(255,30,56,0.28)] bg-[var(--carbon-deep)] p-2 shadow-[0_0_24px_rgba(255,30,56,0.08)]">
          <textarea
            data-testid="mission__textarea"
            aria-label="Mission to Sovereign"
            value={text}
            onChange={(event) => { setText(event.target.value); onTypingStateChange?.(event.target.value.length > 0); }}
            onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }}
            onFocus={() => onTypingStateChange?.(text.length > 0)}
            onBlur={() => onTypingStateChange?.(false)}
            disabled={executing}
            title={executing ? 'Mission locked while the persisted run is executing…' : readbackUnavailable ? 'Readback unavailable — retry the persisted run before dispatching again.' : 'Enter your mission'}
            placeholder={executing ? 'Mission locked while the persisted run is executing…' : readbackUnavailable ? 'Readback unavailable — retry the persisted run before dispatching again.' : 'Describe the mission. Runtime truth begins only after backend acceptance.'}
            rows={2}
            className="w-full min-h-[48px] sm:min-h-[72px] max-h-36 resize-none bg-transparent outline-none px-2 py-1.5 font-mono text-[11px] text-white placeholder:text-[var(--text-dim)] disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[var(--red-pulse)] focus-visible:rounded-md disabled:cursor-not-allowed"
          />
          <div className="flex items-center justify-between gap-2 px-1 pt-1 border-t border-white/5"><div className="flex items-center gap-1 font-mono text-[8.5px] text-[var(--text-dim)]"><Cpu size={10} className="text-[var(--red-laser)]" /> ENTER dispatches · SHIFT+ENTER newline</div><motion.button whileTap={{ scale: 0.96 }} type="button" data-testid="builder__start-task" onClick={submit} disabled={!canSend} title={executing ? 'Mission locked while executing' : canSend ? 'Dispatch mission' : 'Enter a mission to dispatch'} className="min-h-9 px-3 rounded-md bg-[var(--red-pulse)] text-white font-mono text-[10px] font-black flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed shadow-[0_0_12px_rgba(255,30,56,0.25)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">{executing ? <Loader2 size={11} className="animate-spin" /> : <Send size={11} />} DISPATCH</motion.button></div>
        </div>
      </div>
    </section>
  );
}
