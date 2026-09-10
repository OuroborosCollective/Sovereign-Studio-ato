import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Blocks, Bot, BrainCircuit, Cpu, Send, Square, Terminal, User, Wrench } from 'lucide-react';
import type { AgentMode, ChatMessage, JobPhase, SovereignJob } from '../../types/domain';
import { playDispatchBlast, playKeystrokeChirp } from '../../utils/audio';

interface Props {
  messages: ChatMessage[];
  onSubmitOrder?: (text: string) => void;
  onSendMessage?: (text: string) => void;
  jobPhase?: JobPhase;
  activeJob?: SovereignJob | null;
  onOpenToolchain: () => void;
  onOpenSkills: () => void;
  onOpenIntegrations: () => void;
  onAbortJob?: () => void;
  onTypingStateChange?: (typing: boolean) => void;
  activeToolchainName?: string;
  activeSkillsCount?: number;
  activeIntegrationsCount?: number;
  agentMode?: AgentMode;
  onAgentModeChange?: (mode: AgentMode) => void;
}

const ACTIVE_PHASES: JobPhase[] = ['DISPATCHING', 'PROVISIONING', 'EXECUTING', 'FINALIZING'];

function MessageCard({ message }: { message: ChatMessage }) {
  const human = message.sender === 'HUMAN' || message.role === 'human';
  const system = message.sender === 'SYSTEM' || message.role === 'system';
  return (
    <motion.div initial={{ opacity: 0, y: 7 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-2.5 ${human ? 'justify-end' : 'justify-start'}`}>
      {!human && <div className={`w-7 h-7 rounded-md shrink-0 flex items-center justify-center border ${system ? 'bg-[var(--carbon-surface)] border-white/10 text-[var(--text-muted)]' : 'bg-[rgba(255,30,56,0.12)] border-[rgba(255,30,56,0.3)] text-[var(--red-laser)]'}`}>{system ? <Terminal size={13} /> : <Bot size={13} />}</div>}
      <div className={`max-w-[88%] sm:max-w-[82%] rounded-lg border px-3 py-2.5 ${human ? 'bg-[rgba(255,30,56,0.11)] border-[rgba(255,30,56,0.25)]' : 'bg-[var(--carbon-deep)] border-white/5'}`}>
        <div className="whitespace-pre-wrap break-words font-mono text-[10.5px] sm:text-[11px] leading-relaxed text-[var(--text-main)]">{message.content}</div>
        <div className="mt-2 flex items-center justify-between gap-3 font-mono text-[8.5px] text-[var(--text-dim)]"><span>{human ? 'OWNER' : system ? 'CONTROL SURFACE' : 'SOVEREIGN READBACK'}</span>{message.evidenceBadge && <span className="text-[var(--emerald-seal)] font-bold">{message.evidenceBadge}</span>}</div>
      </div>
      {human && <div className="w-7 h-7 rounded-md shrink-0 flex items-center justify-center bg-[var(--carbon-surface)] border border-white/10 text-white"><User size={13} /></div>}
    </motion.div>
  );
}

export function ChatSurface({ messages, onSubmitOrder, onSendMessage, jobPhase = 'IDLE', activeJob, onOpenToolchain, onOpenSkills, onOpenIntegrations, onAbortJob, onTypingStateChange, activeToolchainName, activeSkillsCount = 0, activeIntegrationsCount = 0, agentMode = 'single', onAgentModeChange }: Props) {
  const [text, setText] = useState('');
  const executing = ACTIVE_PHASES.includes(jobPhase);
  const canSend = text.trim().length > 0 && !executing;
  const phaseTone = jobPhase === 'FAILED' || jobPhase === 'BLOCKED' ? 'text-[var(--red-alert)]' : jobPhase === 'COMPLETED' ? 'text-[var(--emerald-seal)]' : 'text-white';
  const latestRun = useMemo(() => activeJob?.runId || activeJob?.id, [activeJob?.runId, activeJob?.id]);

  const submit = () => {
    const mission = text.trim();
    if (!mission || executing) return;
    playDispatchBlast();
    (onSendMessage ?? onSubmitOrder)?.(mission);
    setText('');
    onTypingStateChange?.(false);
  };

  return (
    <section className="flex flex-col h-full bg-[var(--carbon-base)] border-r border-[rgba(255,30,56,0.18)] relative overflow-hidden" data-testid="vnext-command-surface">
      <div className="px-3 sm:px-4 py-2.5 border-b border-white/5 bg-[var(--carbon-deep)] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 min-w-0"><Terminal size={14} className="text-[var(--red-laser)] shrink-0" /><span className="font-mono text-[10px] sm:text-[11px] font-black tracking-widest text-white truncate">SOVEREIGN MISSION CONSOLE</span>{latestRun && <span className="hidden lg:inline font-mono text-[8.5px] text-[var(--text-dim)] truncate">RUN // {latestRun}</span>}</div>
        <div className="flex items-center gap-2"><span className={`font-mono text-[9px] font-black ${phaseTone}`}>{jobPhase}</span>{executing && onAbortJob && <button type="button" onClick={onAbortJob} className="min-h-8 px-2 rounded border border-[rgba(255,30,56,0.35)] bg-[rgba(255,30,56,0.08)] text-[var(--red-laser)] hover:bg-[var(--red-laser)] hover:text-white font-mono text-[9px] font-bold flex items-center gap-1"><Square size={10} /> ABORT</button>}</div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 space-y-3" data-testid="vnext-message-stream">{messages.map((message) => <MessageCard key={message.id} message={message} />)}</div>

      <div className="shrink-0 px-3 sm:px-4 pb-3 sm:pb-4 pt-2 bg-gradient-to-t from-[var(--carbon-base)] via-[var(--carbon-base)] to-transparent">
        <div className="mb-2 grid grid-cols-3 gap-1.5">
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenToolchain(); }} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] text-left px-2 font-mono"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><Wrench size={10} /> TOOLCHAIN</span><span className="block truncate text-[9px] text-white mt-0.5">{activeToolchainName || 'UNVERIFIED'}</span></button>
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenSkills(); }} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] px-2 font-mono"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><BrainCircuit size={10} /> AGENTS</span><span className="block text-[9px] text-white mt-0.5">{activeSkillsCount} MANIFEST NODES</span></button>
          <button type="button" onClick={() => { playKeystrokeChirp(); onOpenIntegrations(); }} className="min-h-9 rounded-md bg-[var(--carbon-surface)] border border-white/5 hover:border-[rgba(255,30,56,0.3)] px-2 font-mono"><span className="flex items-center gap-1 text-[8.5px] text-[var(--text-dim)]"><Blocks size={10} /> ATTACHMENTS</span><span className="block text-[9px] text-white mt-0.5">{activeIntegrationsCount} OBSERVED</span></button>
        </div>

        <div data-testid="agent-mode-selector" className="mb-2 flex items-center gap-1.5 rounded-lg border border-white/5 bg-[var(--carbon-deep)] p-1.5 font-mono">
          <span className="px-1 text-[8px] text-[var(--text-dim)]">EXECUTION</span>
          <button type="button" data-testid="agent-mode-single" aria-pressed={agentMode === 'single'} disabled={executing} onClick={() => { playKeystrokeChirp(); onAgentModeChange?.('single'); }} className={`min-h-8 flex-1 rounded border px-2 text-[8.5px] font-black ${agentMode === 'single' ? 'border-[var(--emerald-seal)] bg-[rgba(16,185,129,0.12)] text-[var(--emerald-seal)]' : 'border-white/5 bg-[var(--carbon-surface)] text-[var(--text-muted)]'} disabled:opacity-50`}>1 AGENT · FREELLM</button>
          <button type="button" data-testid="agent-mode-swarm" aria-pressed={agentMode === 'swarm'} disabled={executing} onClick={() => { playKeystrokeChirp(); onAgentModeChange?.('swarm'); }} className={`min-h-8 flex-1 rounded border px-2 text-[8.5px] font-black ${agentMode === 'swarm' ? 'border-[var(--red-laser)] bg-[rgba(255,30,56,0.12)] text-[var(--red-laser)]' : 'border-white/5 bg-[var(--carbon-surface)] text-[var(--text-muted)]'} disabled:opacity-50`}>SWARM · OPT-IN</button>
          <span className="hidden sm:inline px-1 text-[8px] text-[var(--text-dim)]">SERVER-GATED</span>
        </div>

        <div className="theme-diamond-cut rounded-xl border border-[rgba(255,30,56,0.28)] bg-[var(--carbon-deep)] p-2 shadow-[0_0_24px_rgba(255,30,56,0.08)]">
          <textarea
            data-testid="mission__textarea"
            aria-label="Mission an Sovereign"
            value={text}
            onChange={(event) => { setText(event.target.value); onTypingStateChange?.(event.target.value.length > 0); }}
            onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(); } }}
            onFocus={() => onTypingStateChange?.(text.length > 0)}
            onBlur={() => onTypingStateChange?.(false)}
            disabled={executing}
            placeholder={executing ? 'Mission locked while the persisted run is executing…' : 'Describe the mission. Runtime truth begins only after backend acceptance.'}
            className="w-full min-h-[72px] max-h-36 resize-none bg-transparent outline-none px-2 py-1.5 font-mono text-[11px] text-white placeholder:text-[var(--text-dim)] disabled:opacity-50"
          />
          <div className="flex items-center justify-between gap-2 px-1 pt-1 border-t border-white/5"><div className="flex items-center gap-1 font-mono text-[8.5px] text-[var(--text-dim)]"><Cpu size={10} className="text-[var(--red-laser)]" /> ENTER dispatches · SHIFT+ENTER newline</div><motion.button whileTap={{ scale: 0.96 }} type="button" data-testid="builder__start-task" onClick={submit} disabled={!canSend} className="min-h-9 px-3 rounded-md bg-[var(--red-pulse)] text-white font-mono text-[10px] font-black flex items-center gap-1.5 disabled:opacity-30 disabled:cursor-not-allowed shadow-[0_0_12px_rgba(255,30,56,0.25)]"><Send size={11} /> DISPATCH</motion.button></div>
        </div>
      </div>
    </section>
  );
}
