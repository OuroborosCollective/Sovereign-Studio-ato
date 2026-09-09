import React from 'react';
import { BrainCircuit, Check, Sparkles, Zap } from 'lucide-react';
import { Modal } from '../Modal';
import type { Skill } from '../../types/domain';
import { cx } from '../../utils/cx';

interface Props { isOpen: boolean; onClose: () => void; skills: Skill[]; activeSkillIds?: string[]; }

export function SkillRegistryDrawer({ isOpen, onClose, skills, activeSkillIds = [] }: Props) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="SWARM REGISTRY // BIOMODULAR NODES">
      <div className="space-y-3 font-mono">
        <div className="text-[11px] text-[var(--text-muted)] mb-2">Read-only live swarm registry. Core roles are projected from the server manifest; this panel does not locally enable or disable execution capabilities.</div>
        {skills.map((skill) => {
          const learned = skill.source === 'learned';
          const active = activeSkillIds.includes(skill.id);
          return <div key={skill.id} className={cx('p-3 border rounded-lg transition-all flex items-start gap-3 relative theme-diamond-cut', active ? learned ? 'border-emerald-500 bg-[rgba(16,185,129,0.08)]' : 'border-[var(--red-laser)] bg-[rgba(255,30,56,0.08)]' : 'border-white/5 bg-[var(--carbon-deep)] opacity-75')}>
            <div className={cx('w-8 h-8 rounded flex items-center justify-center shrink-0 mt-0.5', learned ? 'bg-[rgba(16,185,129,0.15)] text-[var(--emerald-seal)] border border-emerald-500/30' : 'bg-[rgba(255,30,56,0.15)] text-[var(--red-laser)] border border-[rgba(255,30,56,0.3)]')}>{learned ? <BrainCircuit size={16} /> : <Zap size={16} />}</div>
            <div className="flex-1 min-w-0"><div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2 min-w-0"><div className="text-sm font-bold text-white truncate">{skill.name}</div><span className={cx('text-[9px] uppercase px-1.5 py-0.2 rounded font-bold flex items-center gap-1', learned ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-[var(--carbon-surface)] text-[var(--text-muted)] border border-white/5')}>{learned && <Sparkles size={8} />}{learned ? 'LEARNED' : 'CORE'}</span></div>{active && <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded bg-[var(--carbon-surface)] text-white border border-white/10"><Check size={10} className="text-[var(--red-laser)]" /> REGISTERED</span>}</div><div className="text-[11.5px] text-[var(--text-muted)] font-sans mt-1 leading-normal">{skill.description}</div>{skill.tier && <div className="mt-2 text-[9px] text-[var(--text-dim)]">TIER: {skill.tier}</div>}</div>
          </div>;
        })}
        {skills.length === 0 && <div className="text-[var(--text-dim)] text-xs text-center py-6">No swarm manifest has been read back.</div>}
      </div>
    </Modal>
  );
}
